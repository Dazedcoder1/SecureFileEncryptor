"""
records.py — Core domain models shared across layers.

Innermost Clean Architecture ring: depends on nothing but the standard
library. Crypto, database, workers, and UI all speak these types.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class OperationType(str, Enum):
    """What was done to a file."""

    ENCRYPT = "encrypt"
    DECRYPT = "decrypt"


class OperationStatus(str, Enum):
    """How an operation ended."""

    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class CryptoResult:
    """Outcome of a single file encryption/decryption.

    Attributes:
        source: Input file path.
        destination: Output file path.
        size_bytes: Plaintext size processed.
        sha256_hex: SHA-256 of the plaintext (hex).
        duration_seconds: Wall-clock time for the operation.
        integrity_ok: Decryption only — True if the plaintext hash matched
            the hash recorded at encryption time. None for encryption.
    """

    source: Path
    destination: Path
    size_bytes: int
    sha256_hex: str
    duration_seconds: float
    integrity_ok: bool | None = None


@dataclass(frozen=True)
class ProgressUpdate:
    """Snapshot emitted by workers for the progress panel.

    Carries everything the UI displays: current file, overall progress,
    percentage, speed, elapsed, and remaining time — computed once in
    the worker so the GUI thread does zero math.
    """

    current_file: str
    file_index: int          # 1-based
    file_count: int
    done_bytes: int
    total_bytes: int
    percent: int             # 0-100
    speed_bps: float
    elapsed_seconds: float
    remaining_seconds: float


@dataclass
class HistoryRecord:
    """One row of the encryption history table (SQLite).

    ``record_id`` is None until the database assigns it.
    """

    record_id: int | None
    timestamp: str                 # "YYYY-MM-DD HH:MM:SS"
    operation: OperationType
    filename: str
    location: str                  # parent directory of the source
    size_bytes: int
    duration_seconds: float
    status: OperationStatus
    sha256_hex: str
    error_message: str = ""
