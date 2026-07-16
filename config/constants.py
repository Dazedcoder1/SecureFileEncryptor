"""
constants.py — Application-wide constants for Secure File Encryptor Pro.

Single source of truth for every fixed value in the application.
No other module may hardcode magic numbers, strings, or paths.

Security-relevant values (key sizes, nonce sizes, KDF iterations) follow
current NIST SP 800-38D and OWASP recommendations.
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------
# Application metadata
# --------------------------------------------------------------------------
APP_NAME: Final[str] = "Secure File Encryptor Pro"
APP_VERSION: Final[str] = "1.0.0"
APP_AUTHOR: Final[str] = "Dazedcoder"
APP_LICENSE: Final[str] = "MIT"
ORGANIZATION_NAME: Final[str] = "Dazedcoder"
GITHUB_URL: Final[str] = "https://github.com/dazedcoder/secure-file-encryptor-pro"

# --------------------------------------------------------------------------
# Cryptography (AES-256-GCM + PBKDF2-HMAC-SHA256)
# --------------------------------------------------------------------------
MAGIC_HEADER: Final[bytes] = b"SFEP"        # identifies a file as ours
FORMAT_VERSION: Final[int] = 1              # bump when file format changes
SALT_SIZE: Final[int] = 16                  # 128-bit random salt
NONCE_SIZE: Final[int] = 12                 # 96-bit GCM nonce (NIST rec.)
KEY_SIZE: Final[int] = 32                   # 256-bit AES key
GCM_TAG_SIZE: Final[int] = 16               # 128-bit authentication tag
PBKDF2_ITERATIONS: Final[int] = 600_000     # OWASP recommendation (>= 100k)
CHUNK_SIZE: Final[int] = 4 * 1024 * 1024    # 4 MiB streaming chunks
ENCRYPTED_EXTENSION: Final[str] = ".sfep"   # extension for encrypted output
HASH_ALGORITHM: Final[str] = "sha256"       # integrity hash
HASH_SIZE: Final[int] = 32                  # SHA-256 digest length in bytes

# --------------------------------------------------------------------------
# Password policy
# --------------------------------------------------------------------------
MIN_PASSWORD_LENGTH: Final[int] = 8
STRONG_PASSWORD_LENGTH: Final[int] = 12

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
DB_FILENAME: Final[str] = "history.db"
DEFAULT_HISTORY_LIMIT: Final[int] = 500     # max rows kept in history table

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
LOG_FILENAME: Final[str] = "secure_file_encryptor.log"
LOG_MAX_BYTES: Final[int] = 2 * 1024 * 1024  # rotate at 2 MiB
LOG_BACKUP_COUNT: Final[int] = 3

# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
WINDOW_MIN_WIDTH: Final[int] = 960
WINDOW_MIN_HEIGHT: Final[int] = 640
STATUS_MESSAGE_TIMEOUT_MS: Final[int] = 5000
RECENT_FILES_DISPLAY_COUNT: Final[int] = 8
