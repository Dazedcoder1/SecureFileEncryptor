"""Crypto engine tests: roundtrips, attacks, cancellation, integrity.

Run from the project root:
    python -m pytest tests/test_crypto.py -v

Tests use a low PBKDF2 iteration count (2048) for speed; the production
default (600k) is asserted separately in test_config.py.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from config.constants import CHUNK_SIZE, MAGIC_HEADER
from crypto.aes_engine import HEADER_SIZE, AESGCMFileEngine
from crypto.integrity import hash_file, verify_file
from crypto.key_derivation import derive_key_material
from crypto.password_manager import SecurePassword
from crypto.utils import (
    CorruptedFileError,
    InvalidFileFormatError,
    OperationCancelledError,
    UnsupportedVersionError,
    WrongPasswordError,
    secure_random_bytes,
    wipe,
)
from utils.validator import ValidationError

ITER = 2048  # fast test-only KDF rounds
PASSWORD = b"CorrectHorse7!battery"


@pytest.fixture()
def engine() -> AESGCMFileEngine:
    return AESGCMFileEngine()


@pytest.fixture()
def small_file(tmp_path: Path) -> Path:
    f = tmp_path / "note.txt"
    f.write_bytes(b"attack at dawn \xf0\x9f\x94\x92" * 100)
    return f


@pytest.fixture()
def multi_chunk_file(tmp_path: Path) -> Path:
    """2.5 chunks of random binary data -> exercises the chunk loop."""
    f = tmp_path / "video.bin"
    f.write_bytes(os.urandom(int(CHUNK_SIZE * 2.5)))
    return f


def _roundtrip(engine: AESGCMFileEngine, src: Path, tmp_path: Path) -> Path:
    enc = tmp_path / (src.name + ".sfep")
    dec = tmp_path / ("restored_" + src.name)
    engine.encrypt_file(src, enc, PASSWORD, iterations=ITER)
    result = engine.decrypt_file(enc, dec, PASSWORD)
    assert result.integrity_ok is True
    return dec


# --------------------------------------------------------------------------
# Roundtrips
# --------------------------------------------------------------------------
class TestRoundtrip:
    def test_small_file(self, engine, small_file, tmp_path) -> None:
        restored = _roundtrip(engine, small_file, tmp_path)
        assert restored.read_bytes() == small_file.read_bytes()

    def test_multi_chunk_binary_file(
        self, engine, multi_chunk_file, tmp_path
    ) -> None:
        restored = _roundtrip(engine, multi_chunk_file, tmp_path)
        assert (
            hashlib.sha256(restored.read_bytes()).digest()
            == hashlib.sha256(multi_chunk_file.read_bytes()).digest()
        )

    def test_exact_chunk_boundary(self, engine, tmp_path) -> None:
        src = tmp_path / "exact.bin"
        src.write_bytes(os.urandom(CHUNK_SIZE))  # exactly one chunk
        restored = _roundtrip(engine, src, tmp_path)
        assert restored.read_bytes() == src.read_bytes()

    def test_ciphertext_is_not_plaintext(self, engine, small_file, tmp_path) -> None:
        enc = tmp_path / "out.sfep"
        engine.encrypt_file(small_file, enc, PASSWORD, iterations=ITER)
        assert b"attack at dawn" not in enc.read_bytes()

    def test_same_input_yields_different_ciphertext(
        self, engine, small_file, tmp_path
    ) -> None:
        """Random salt + nonce => no deterministic ciphertext."""
        enc1, enc2 = tmp_path / "a.sfep", tmp_path / "b.sfep"
        engine.encrypt_file(small_file, enc1, PASSWORD, iterations=ITER)
        engine.encrypt_file(small_file, enc2, PASSWORD, iterations=ITER)
        assert enc1.read_bytes() != enc2.read_bytes()

    def test_encrypted_file_starts_with_magic(
        self, engine, small_file, tmp_path
    ) -> None:
        enc = tmp_path / "out.sfep"
        engine.encrypt_file(small_file, enc, PASSWORD, iterations=ITER)
        assert enc.read_bytes()[:4] == MAGIC_HEADER

    def test_unicode_filename_roundtrip(self, engine, tmp_path) -> None:
        """Non-ASCII names and spaces must survive the full cycle."""
        src = tmp_path / "отчёт 数据 dosya (final).txt"
        src.write_bytes("café résumé naïve ✓".encode("utf-8") * 200)
        restored = _roundtrip(engine, src, tmp_path)
        assert restored.read_bytes() == src.read_bytes()


# --------------------------------------------------------------------------
# Attack / failure scenarios
# --------------------------------------------------------------------------
class TestFailures:
    def test_wrong_password_detected(self, engine, small_file, tmp_path) -> None:
        enc = tmp_path / "out.sfep"
        engine.encrypt_file(small_file, enc, PASSWORD, iterations=ITER)
        with pytest.raises(WrongPasswordError):
            engine.decrypt_file(enc, tmp_path / "dec", b"wrong-password!")
        assert not (tmp_path / "dec").exists()

    def test_tampered_ciphertext_detected(self, engine, small_file, tmp_path) -> None:
        enc = tmp_path / "out.sfep"
        engine.encrypt_file(small_file, enc, PASSWORD, iterations=ITER)
        raw = bytearray(enc.read_bytes())
        raw[HEADER_SIZE + 10] ^= 0xFF  # flip one ciphertext bit
        enc.write_bytes(bytes(raw))
        with pytest.raises(CorruptedFileError):
            engine.decrypt_file(enc, tmp_path / "dec", PASSWORD)

    def test_tampered_header_detected(self, engine, small_file, tmp_path) -> None:
        """Header is AAD: silently editing the stored hash must fail."""
        enc = tmp_path / "out.sfep"
        engine.encrypt_file(small_file, enc, PASSWORD, iterations=ITER)
        raw = bytearray(enc.read_bytes())
        raw[HEADER_SIZE - 1] ^= 0xFF  # last hash byte
        enc.write_bytes(bytes(raw))
        with pytest.raises(CorruptedFileError):
            engine.decrypt_file(enc, tmp_path / "dec", PASSWORD)

    def test_truncated_file_detected(self, engine, multi_chunk_file, tmp_path) -> None:
        enc = tmp_path / "out.sfep"
        engine.encrypt_file(multi_chunk_file, enc, PASSWORD, iterations=ITER)
        raw = enc.read_bytes()
        enc.write_bytes(raw[: len(raw) // 2])  # chop the file in half
        with pytest.raises(CorruptedFileError):
            engine.decrypt_file(enc, tmp_path / "dec", PASSWORD)

    def test_non_sfep_file_rejected(self, engine, tmp_path) -> None:
        fake = tmp_path / "fake.sfep"
        fake.write_bytes(b"X" * 200)
        with pytest.raises(InvalidFileFormatError):
            engine.decrypt_file(fake, tmp_path / "dec", PASSWORD)

    def test_tiny_file_rejected(self, engine, tmp_path) -> None:
        fake = tmp_path / "tiny.sfep"
        fake.write_bytes(MAGIC_HEADER)
        with pytest.raises(InvalidFileFormatError):
            engine.decrypt_file(fake, tmp_path / "dec", PASSWORD)

    def test_future_version_rejected(self, engine, small_file, tmp_path) -> None:
        enc = tmp_path / "out.sfep"
        engine.encrypt_file(small_file, enc, PASSWORD, iterations=ITER)
        raw = bytearray(enc.read_bytes())
        raw[4] = 99  # version byte
        enc.write_bytes(bytes(raw))
        with pytest.raises(UnsupportedVersionError):
            engine.decrypt_file(enc, tmp_path / "dec", PASSWORD)


# --------------------------------------------------------------------------
# Progress + cancellation
# --------------------------------------------------------------------------
class TestProgressAndCancel:
    def test_progress_reaches_total(self, engine, multi_chunk_file, tmp_path) -> None:
        calls: list[tuple[int, int]] = []
        enc = tmp_path / "out.sfep"
        engine.encrypt_file(
            multi_chunk_file,
            enc,
            PASSWORD,
            iterations=ITER,
            progress_callback=lambda done, total: calls.append((done, total)),
        )
        assert len(calls) >= 3  # one per chunk
        done, total = calls[-1]
        assert done == total == multi_chunk_file.stat().st_size
        assert [c[0] for c in calls] == sorted(c[0] for c in calls)

    def test_cancel_encrypt_removes_partial(
        self, engine, multi_chunk_file, tmp_path
    ) -> None:
        enc = tmp_path / "out.sfep"
        with pytest.raises(OperationCancelledError):
            engine.encrypt_file(
                multi_chunk_file,
                enc,
                PASSWORD,
                iterations=ITER,
                cancel_callback=lambda: True,
            )
        assert not enc.exists()
        assert not list(tmp_path.glob("*.part"))

    def test_cancel_decrypt_removes_partial(
        self, engine, multi_chunk_file, tmp_path
    ) -> None:
        enc = tmp_path / "out.sfep"
        engine.encrypt_file(multi_chunk_file, enc, PASSWORD, iterations=ITER)
        with pytest.raises(OperationCancelledError):
            engine.decrypt_file(
                enc, tmp_path / "dec", PASSWORD, cancel_callback=lambda: True
            )
        assert not (tmp_path / "dec").exists()
        assert not list(tmp_path.glob("*.part"))


# --------------------------------------------------------------------------
# Key derivation
# --------------------------------------------------------------------------
class TestKeyDerivation:
    def test_deterministic_for_same_inputs(self) -> None:
        salt = b"\x01" * 16
        assert derive_key_material(b"pw", salt, ITER) == derive_key_material(
            b"pw", salt, ITER
        )

    def test_key_and_kcv_sizes(self) -> None:
        key, kcv = derive_key_material(b"pw", b"\x01" * 16, ITER)
        assert len(key) == 32 and len(kcv) == 16

    def test_different_salt_different_key(self) -> None:
        key1, _ = derive_key_material(b"pw", b"\x01" * 16, ITER)
        key2, _ = derive_key_material(b"pw", b"\x02" * 16, ITER)
        assert key1 != key2

    def test_different_password_different_key(self) -> None:
        salt = b"\x01" * 16
        assert derive_key_material(b"pw1", salt, ITER)[0] != derive_key_material(
            b"pw2", salt, ITER
        )[0]

    def test_empty_inputs_rejected(self) -> None:
        with pytest.raises(ValueError):
            derive_key_material(b"", b"\x01" * 16, ITER)
        with pytest.raises(ValueError):
            derive_key_material(b"pw", b"", ITER)
        with pytest.raises(ValueError):
            derive_key_material(b"pw", b"\x01" * 16, 0)


# --------------------------------------------------------------------------
# Integrity + primitives + SecurePassword
# --------------------------------------------------------------------------
class TestIntegrityAndPrimitives:
    def test_hash_file_matches_hashlib(self, tmp_path: Path) -> None:
        f = tmp_path / "x.bin"
        f.write_bytes(os.urandom(100_000))
        assert hash_file(f) == hashlib.sha256(f.read_bytes()).digest()

    def test_verify_file(self, tmp_path: Path) -> None:
        f = tmp_path / "x.bin"
        f.write_bytes(b"payload")
        good = hashlib.sha256(b"payload").digest()
        assert verify_file(f, good) is True
        assert verify_file(f, b"\x00" * 32) is False

    def test_secure_random_uniqueness_and_length(self) -> None:
        a, b = secure_random_bytes(16), secure_random_bytes(16)
        assert len(a) == 16 and a != b
        with pytest.raises(ValueError):
            secure_random_bytes(0)

    def test_wipe_zeroes_buffer(self) -> None:
        buf = bytearray(b"secret")
        wipe(buf)
        assert buf == bytearray(len(b"secret"))


class TestSecurePassword:
    def test_value_then_wipe(self) -> None:
        with SecurePassword("ValidPass123!") as pw:
            assert pw.value == b"ValidPass123!"
        assert pw.is_wiped
        with pytest.raises(RuntimeError):
            _ = pw.value

    def test_wiped_even_on_exception(self) -> None:
        captured = None
        with pytest.raises(RuntimeError, match="boom"):
            with SecurePassword("ValidPass123!") as pw:
                captured = pw
                raise RuntimeError("boom")
        assert captured is not None and captured.is_wiped

    def test_policy_enforced_at_construction(self) -> None:
        with pytest.raises(ValidationError):
            SecurePassword("short")
        with pytest.raises(ValidationError):
            SecurePassword("ValidPass123!", "Mismatch123!")

    def test_repr_never_leaks(self) -> None:
        pw = SecurePassword("ValidPass123!")
        assert "ValidPass123!" not in repr(pw)
        pw.wipe()
