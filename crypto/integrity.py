"""
integrity.py — SHA-256 file integrity hashing and verification.

The plaintext hash is computed before encryption, stored in the
authenticated file header, and re-checked after decryption so the user
gets an explicit 'Integrity Passed / Failed' verdict.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from config.constants import CHUNK_SIZE, HASH_ALGORITHM
from crypto.utils import OperationCancelledError, constant_time_equal

ProgressCallback = Callable[[int, int], None]   # (processed_bytes, total_bytes)
CancelCallback = Callable[[], bool]             # True => abort now


def hash_file(
    path: Path,
    progress_callback: ProgressCallback | None = None,
    cancel_callback: CancelCallback | None = None,
) -> bytes:
    """Stream a file through SHA-256 without loading it into memory.

    Returns:
        32-byte digest.

    Raises:
        OperationCancelledError: if ``cancel_callback`` returns True.
        OSError: propagated on read failures (caller maps to UI error).
    """
    digest = hashlib.new(HASH_ALGORITHM)
    total = path.stat().st_size
    processed = 0
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK_SIZE):
            if cancel_callback is not None and cancel_callback():
                raise OperationCancelledError("Hashing cancelled by user.")
            digest.update(chunk)
            processed += len(chunk)
            if progress_callback is not None:
                progress_callback(processed, total)
    return digest.digest()


def verify_file(path: Path, expected_digest: bytes) -> bool:
    """True if the file's SHA-256 equals ``expected_digest`` (constant-time)."""
    return constant_time_equal(hash_file(path), expected_digest)
