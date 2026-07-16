"""
key_derivation.py — Password-based key derivation (PBKDF2-HMAC-SHA256).

Derives 48 bytes per file: a 256-bit AES key plus a 128-bit key check
value (KCV). The KCV is stored in the file header so decryption can
distinguish 'wrong password' from 'corrupted file' — two different
errors the UI must report differently. The password itself is never
stored anywhere.
"""

from __future__ import annotations

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from config.constants import KEY_SIZE, PBKDF2_ITERATIONS

KCV_SIZE: int = 16
_DERIVED_LENGTH: int = KEY_SIZE + KCV_SIZE  # 48 bytes


def derive_key_material(
    password: bytes,
    salt: bytes,
    iterations: int = PBKDF2_ITERATIONS,
) -> tuple[bytes, bytes]:
    """Derive (aes_key, key_check_value) from a password and salt.

    Args:
        password: UTF-8 password bytes (caller wipes its buffer after use).
        salt: Random per-file salt — same password yields a different key
            for every file, defeating rainbow tables.
        iterations: PBKDF2 rounds; stored in the file header so files
            remain decryptable if the app default changes later.

    Returns:
        (32-byte AES-256 key, 16-byte KCV).

    Raises:
        ValueError: on empty password/salt or non-positive iterations.
    """
    if not password:
        raise ValueError("password must not be empty")
    if not salt:
        raise ValueError("salt must not be empty")
    if iterations < 1:
        raise ValueError("iterations must be positive")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_DERIVED_LENGTH,
        salt=salt,
        iterations=iterations,
    )
    material = kdf.derive(password)
    return material[:KEY_SIZE], material[KEY_SIZE:]
