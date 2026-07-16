"""
aes_engine.py — Streaming AES-256-GCM file encryption/decryption.

SFEP container format, version 1
================================

    HEADER (85 bytes, authenticated as AAD of every chunk):
        magic          4  b"SFEP"
        version        1  uint8
        iterations     4  uint32 BE   PBKDF2 rounds used for this file
        salt          16  random      per-file KDF salt
        nonce_prefix   4  random      per-file GCM nonce prefix
        total_size     8  uint64 BE   plaintext size (truncation detection)
        kcv           16              key check value (wrong-password check)
        sha256        32              plaintext hash (integrity verdict)

    BODY: repeated frames of
        length         4  uint32 BE   ciphertext length (plaintext + 16 tag)
        ciphertext     variable       AES-256-GCM output for one chunk

Design notes
------------
* Streaming: files are processed in 4 MiB chunks — a 20 GB video never
  sits in RAM, and progress callbacks fire per chunk.
* Per-chunk nonce = nonce_prefix (4B, random per file) || chunk index
  (8B, big-endian counter). Nonces are therefore unique per file & chunk,
  and a reordered/duplicated chunk fails its GCM tag automatically
  because the decryptor derives the nonce from its own counter.
* The full header is passed as AAD to every chunk, so tampering with any
  header field (salt, size, stored hash, ...) breaks authentication.
* total_size defeats truncation: chopping trailing frames off the file
  yields fewer plaintext bytes than promised -> CorruptedFileError.
* Atomic output: we write to '<name>.part' and os.replace() at the end,
  so a crash never leaves a half-written file that looks valid.
"""

from __future__ import annotations

import hashlib
import os
import struct
import time
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config.constants import (
    CHUNK_SIZE,
    FORMAT_VERSION,
    GCM_TAG_SIZE,
    MAGIC_HEADER,
    NONCE_SIZE,
    PBKDF2_ITERATIONS,
    SALT_SIZE,
)
from crypto import integrity
from crypto.integrity import CancelCallback, ProgressCallback
from crypto.key_derivation import KCV_SIZE, derive_key_material
from crypto.utils import (
    CorruptedFileError,
    InvalidFileFormatError,
    OperationCancelledError,
    UnsupportedVersionError,
    WrongPasswordError,
    constant_time_equal,
    secure_random_bytes,
)
from models.records import CryptoResult
from utils.logger import get_logger

logger = get_logger(__name__)

_NONCE_PREFIX_SIZE = 4
_HEADER_FORMAT = f">4sBI{SALT_SIZE}s{_NONCE_PREFIX_SIZE}sQ{KCV_SIZE}s32s"
HEADER_SIZE: int = struct.calcsize(_HEADER_FORMAT)  # 85

# Crafted files must not be able to stall the app with absurd KDF work
# or allocate huge buffers via a fake frame length.
_MAX_ITERATIONS = 10_000_000
_MAX_FRAME = CHUNK_SIZE + GCM_TAG_SIZE


class AESGCMFileEngine:
    """Encrypts and decrypts single files in the SFEP v1 container format.

    Stateless and thread-safe: safe to share one instance across workers.
    Folder encryption is composed on top of this class by the workers
    layer (one engine call per file, structure mirrored by file_utils).
    """

    # ------------------------------------------------------------- encrypt
    def encrypt_file(
        self,
        source: Path,
        destination: Path,
        password: bytes,
        iterations: int = PBKDF2_ITERATIONS,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
    ) -> CryptoResult:
        """Encrypt ``source`` into ``destination`` (SFEP v1).

        Args:
            source: Existing plaintext file.
            destination: Output path (parent must exist).
            password: UTF-8 password bytes (see SecurePassword).
            iterations: PBKDF2 rounds recorded in the header.
            progress_callback: called with (processed, total) plaintext bytes.
            cancel_callback: polled between chunks; True aborts cleanly.

        Returns:
            CryptoResult with the plaintext SHA-256 and timing.

        Raises:
            OperationCancelledError: user cancelled (partial output removed).
            OSError: filesystem failures (caller maps to UI message).
        """
        started = time.monotonic()
        total = source.stat().st_size

        # Pass 1 — plaintext hash (needed in the header before any chunk).
        sha256 = integrity.hash_file(source, cancel_callback=cancel_callback)

        salt = secure_random_bytes(SALT_SIZE)
        nonce_prefix = secure_random_bytes(_NONCE_PREFIX_SIZE)
        key, kcv = derive_key_material(password, salt, iterations)
        header = struct.pack(
            _HEADER_FORMAT,
            MAGIC_HEADER,
            FORMAT_VERSION,
            iterations,
            salt,
            nonce_prefix,
            total,
            kcv,
            sha256,
        )

        aesgcm = AESGCM(key)
        part = destination.with_name(destination.name + ".part")
        processed = 0
        try:
            with source.open("rb") as src, part.open("wb") as dst:
                dst.write(header)
                index = 0
                while chunk := src.read(CHUNK_SIZE):
                    if cancel_callback is not None and cancel_callback():
                        raise OperationCancelledError(
                            "Encryption cancelled by user."
                        )
                    nonce = nonce_prefix + index.to_bytes(8, "big")
                    ciphertext = aesgcm.encrypt(nonce, chunk, header)
                    dst.write(struct.pack(">I", len(ciphertext)))
                    dst.write(ciphertext)
                    processed += len(chunk)
                    index += 1
                    if progress_callback is not None:
                        progress_callback(processed, total)
            os.replace(part, destination)
        except BaseException:
            part.unlink(missing_ok=True)
            raise

        duration = time.monotonic() - started
        logger.info(
            "Encrypted %s (%d bytes) in %.2fs", source.name, total, duration
        )
        return CryptoResult(
            source=source,
            destination=destination,
            size_bytes=total,
            sha256_hex=sha256.hex(),
            duration_seconds=duration,
        )

    # ------------------------------------------------------------- decrypt
    def decrypt_file(
        self,
        source: Path,
        destination: Path,
        password: bytes,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
    ) -> CryptoResult:
        """Decrypt an SFEP v1 file and verify plaintext integrity.

        Returns:
            CryptoResult with ``integrity_ok`` set from the stored hash.

        Raises:
            InvalidFileFormatError: not an SFEP file / malformed header.
            UnsupportedVersionError: written by a newer format version.
            WrongPasswordError: KCV mismatch — password is incorrect.
            CorruptedFileError: GCM tag or size check failed.
            OperationCancelledError: user cancelled (partial removed).
        """
        started = time.monotonic()
        header, fields = self._read_header(source)
        (_, _, iterations, salt, nonce_prefix, total, stored_kcv, stored_hash) = (
            fields
        )

        key, kcv = derive_key_material(password, salt, iterations)
        if not constant_time_equal(kcv, stored_kcv):
            raise WrongPasswordError("Incorrect password for this file.")

        aesgcm = AESGCM(key)
        part = destination.with_name(destination.name + ".part")
        written = 0
        digest = hashlib.sha256()
        try:
            with source.open("rb") as src, part.open("wb") as dst:
                src.seek(HEADER_SIZE)
                index = 0
                while True:
                    if cancel_callback is not None and cancel_callback():
                        raise OperationCancelledError(
                            "Decryption cancelled by user."
                        )
                    length_raw = src.read(4)
                    if not length_raw:
                        break  # clean EOF
                    if len(length_raw) != 4:
                        raise CorruptedFileError("Truncated chunk header.")
                    (length,) = struct.unpack(">I", length_raw)
                    if not GCM_TAG_SIZE < length <= _MAX_FRAME:
                        raise CorruptedFileError("Invalid chunk length.")
                    ciphertext = src.read(length)
                    if len(ciphertext) != length:
                        raise CorruptedFileError("Truncated chunk data.")
                    nonce = nonce_prefix + index.to_bytes(8, "big")
                    try:
                        plaintext = aesgcm.decrypt(nonce, ciphertext, header)
                    except InvalidTag as exc:
                        raise CorruptedFileError(
                            "File is corrupted or has been tampered with."
                        ) from exc
                    dst.write(plaintext)
                    digest.update(plaintext)
                    written += len(plaintext)
                    index += 1
                    if progress_callback is not None:
                        progress_callback(min(written, total), total)
            if written != total:
                raise CorruptedFileError(
                    "Decrypted size mismatch — file is incomplete."
                )
            os.replace(part, destination)
        except BaseException:
            part.unlink(missing_ok=True)
            raise

        integrity_ok = constant_time_equal(digest.digest(), stored_hash)
        duration = time.monotonic() - started
        logger.info(
            "Decrypted %s (%d bytes) in %.2fs — integrity %s",
            source.name,
            written,
            duration,
            "PASSED" if integrity_ok else "FAILED",
        )
        return CryptoResult(
            source=source,
            destination=destination,
            size_bytes=written,
            sha256_hex=digest.hexdigest(),
            duration_seconds=duration,
            integrity_ok=integrity_ok,
        )

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _read_header(source: Path) -> tuple[bytes, tuple]:
        """Read and validate the 85-byte header; return (raw, fields)."""
        with source.open("rb") as fh:
            header = fh.read(HEADER_SIZE)
        if len(header) != HEADER_SIZE:
            raise InvalidFileFormatError("File is too small to be valid.")
        try:
            fields = struct.unpack(_HEADER_FORMAT, header)
        except struct.error as exc:
            raise InvalidFileFormatError("Malformed file header.") from exc

        magic, version, iterations = fields[0], fields[1], fields[2]
        if magic != MAGIC_HEADER:
            raise InvalidFileFormatError(
                "Not a Secure File Encryptor Pro file."
            )
        if version > FORMAT_VERSION:
            raise UnsupportedVersionError(
                f"File format v{version} requires a newer app version."
            )
        if not 1 <= iterations <= _MAX_ITERATIONS:
            raise InvalidFileFormatError("Unreasonable KDF iteration count.")
        return header, fields
