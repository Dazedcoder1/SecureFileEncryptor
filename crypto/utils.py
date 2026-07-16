"""
utils.py — Crypto-layer primitives and exception hierarchy.

Secure randomness, best-effort buffer wiping, constant-time comparison,
and the exceptions the rest of the application catches. UI code maps
these to user-friendly messages — exception messages here never leak
secrets or internal paths.
"""

from __future__ import annotations

import hmac
import os


# --------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------
class CryptoError(Exception):
    """Base class for every crypto-layer failure."""


class InvalidFileFormatError(CryptoError):
    """File is not a Secure File Encryptor Pro container (bad magic/header)."""


class UnsupportedVersionError(CryptoError):
    """File was written by a newer, unknown format version."""


class WrongPasswordError(CryptoError):
    """Key check value mismatch — the supplied password is incorrect."""


class CorruptedFileError(CryptoError):
    """Authentication tag or size check failed — file is damaged/tampered."""


class OperationCancelledError(CryptoError):
    """User cancelled; partial output has been removed."""


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------
def secure_random_bytes(length: int) -> bytes:
    """Cryptographically secure random bytes (os.urandom / CSPRNG)."""
    if length <= 0:
        raise ValueError("length must be positive")
    return os.urandom(length)


def wipe(buffer: bytearray) -> None:
    """Overwrite a mutable buffer with zeros, in place.

    Best-effort memory hygiene: Python cannot guarantee that no copy
    exists elsewhere (interned strings, GC), but zeroing the working
    buffer shrinks the window in which secrets sit in RAM.
    """
    for i in range(len(buffer)):
        buffer[i] = 0


def constant_time_equal(a: bytes, b: bytes) -> bool:
    """Timing-attack-safe equality (wraps hmac.compare_digest)."""
    return hmac.compare_digest(a, b)
