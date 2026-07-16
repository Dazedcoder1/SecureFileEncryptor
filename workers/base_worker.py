"""
base_worker.py — Shared QThread worker for batch crypto operations.

Template Method pattern: this class owns the batch loop, progress math,
cancellation, error mapping, history recording, and guaranteed password
wiping. EncryptWorker/DecryptWorker override only two hooks
(_validate_source, _run_engine).

Threading model
---------------
The GUI constructs a worker with a prepared job list, connects signals,
and calls start(). Everything in run() executes off the GUI thread, so
the interface never freezes. Cancellation is cooperative: the GUI calls
request_cancel(), the engine polls between 4 MiB chunks and aborts
cleanly (partial output removed by the engine).
"""

from __future__ import annotations

import errno
import time
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from crypto.aes_engine import AESGCMFileEngine
from crypto.password_manager import SecurePassword
from crypto.utils import CryptoError, OperationCancelledError
from database.database import DatabaseError, HistoryDatabase
from models.records import (
    CryptoResult,
    HistoryRecord,
    OperationStatus,
    OperationType,
    ProgressUpdate,
)
from utils import file_utils
from utils.helpers import estimate_remaining, now_timestamp
from utils.logger import get_logger
from utils.validator import ValidationError, validate_output_location

logger = get_logger(__name__)

Job = tuple[Path, Path]  # (source, destination)


class BaseCryptoWorker(QThread):
    """Processes a list of (source, destination) jobs in the background.

    Signals:
        progress_updated(ProgressUpdate): fired per chunk (~4 MiB).
        file_completed(CryptoResult): one file finished successfully.
        file_failed(str, str): (filename, user-friendly reason);
            the batch continues with the next file.
        batch_finished(int, int, bool): (succeeded, failed, was_cancelled) —
            always emitted exactly once, even on cancellation.
    """

    progress_updated = pyqtSignal(object)
    file_completed = pyqtSignal(object)
    file_failed = pyqtSignal(str, str)
    batch_finished = pyqtSignal(int, int, bool)

    #: Subclasses set the operation they perform (used for history rows).
    operation: OperationType

    def __init__(
        self,
        jobs: list[Job],
        password: SecurePassword,
        database: HistoryDatabase | None = None,
        overwrite: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._jobs = list(jobs)
        self._password = password
        self._database = database
        self._overwrite = overwrite
        self._cancel_requested = False
        self._engine = AESGCMFileEngine()

    # ------------------------------------------------------------- control
    def request_cancel(self) -> None:
        """Ask the worker to stop (thread-safe: a bool write is atomic)."""
        self._cancel_requested = True

    def _is_cancelled(self) -> bool:
        return self._cancel_requested

    # ---------------------------------------------------------------- main
    def run(self) -> None:  # executes on the worker thread
        succeeded = failed = 0
        was_cancelled = False
        total_bytes = file_utils.total_size(src for src, _ in self._jobs)
        completed_bytes = 0
        started = time.monotonic()

        try:
            for index, (source, destination) in enumerate(self._jobs):
                if self._is_cancelled():
                    was_cancelled = True
                    self._record(source, 0, 0.0, OperationStatus.CANCELLED,
                                 "", "Cancelled by user.")
                    break

                src_size = source.stat().st_size if source.exists() else 0
                progress_cb = self._make_progress_callback(
                    source, index, completed_bytes, src_size,
                    total_bytes, started,
                )
                try:
                    result = self._process_one(source, destination, progress_cb)
                except OperationCancelledError:
                    was_cancelled = True
                    self._record(source, src_size, 0.0,
                                 OperationStatus.CANCELLED, "",
                                 "Cancelled by user.")
                    break
                except (CryptoError, ValidationError, DatabaseError,
                        OSError) as exc:
                    failed += 1
                    message = self._user_message(exc)
                    logger.error("%s failed for %s: %s",
                                 self.operation.value, source.name, message)
                    self._record(source, src_size, 0.0,
                                 OperationStatus.FAILED, "", message)
                    self.file_failed.emit(source.name, message)
                    continue

                succeeded += 1
                completed_bytes += src_size
                self._record(source, result.size_bytes,
                             result.duration_seconds,
                             OperationStatus.SUCCESS, result.sha256_hex, "")
                self.file_completed.emit(result)
        finally:
            # The password must not outlive the batch, no matter what.
            self._password.wipe()

        self.batch_finished.emit(succeeded, failed, was_cancelled)

    # ------------------------------------------------------------ per-file
    def _process_one(
        self, source: Path, destination: Path, progress_cb
    ) -> CryptoResult:
        """Validate, resolve collisions, pre-check disk, run the engine."""
        self._validate_source(source)

        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not self._overwrite:
            destination = file_utils.ensure_unique_path(destination)
        validate_output_location(destination, overwrite=self._overwrite)

        required = source.stat().st_size
        if not file_utils.has_enough_disk_space(destination.parent, required):
            raise ValidationError(
                "Not enough free disk space for the output file."
            )
        return self._run_engine(source, destination, progress_cb)

    # ----------------------------------------------------- subclass hooks
    def _validate_source(self, source: Path) -> None:
        raise NotImplementedError

    def _run_engine(self, source: Path, destination: Path,
                    progress_cb) -> CryptoResult:
        raise NotImplementedError

    # -------------------------------------------------------------helpers
    def _make_progress_callback(
        self,
        source: Path,
        index: int,
        completed_bytes: int,
        src_size: int,
        total_bytes: int,
        started: float,
    ):
        """Build a per-file callback that reports batch-wide progress."""

        def on_progress(done: int, total: int) -> None:
            fraction = (done / total) if total else 1.0
            overall = completed_bytes + int(fraction * src_size)
            elapsed = time.monotonic() - started
            speed = overall / elapsed if elapsed > 0 else 0.0
            self.progress_updated.emit(
                ProgressUpdate(
                    current_file=source.name,
                    file_index=index + 1,
                    file_count=len(self._jobs),
                    done_bytes=overall,
                    total_bytes=total_bytes,
                    percent=(overall * 100 // total_bytes) if total_bytes else 100,
                    speed_bps=speed,
                    elapsed_seconds=elapsed,
                    remaining_seconds=estimate_remaining(
                        overall, total_bytes, elapsed
                    ),
                )
            )

        return on_progress

    def _record(
        self,
        source: Path,
        size_bytes: int,
        duration: float,
        status: OperationStatus,
        sha256_hex: str,
        error_message: str,
    ) -> None:
        """Write a history row; a DB hiccup must never abort the batch."""
        if self._database is None:
            return
        try:
            self._database.add_record(
                HistoryRecord(
                    record_id=None,
                    timestamp=now_timestamp(),
                    operation=self.operation,
                    filename=source.name,
                    location=str(source.parent),
                    size_bytes=size_bytes,
                    duration_seconds=duration,
                    status=status,
                    sha256_hex=sha256_hex,
                    error_message=error_message,
                )
            )
        except DatabaseError as exc:
            logger.error("Could not write history record: %s", exc)

    @staticmethod
    def _user_message(exc: Exception) -> str:
        """Map any expected exception to a safe, friendly message."""
        if isinstance(exc, (CryptoError, ValidationError, DatabaseError)):
            return str(exc)
        if isinstance(exc, PermissionError):
            return "Permission denied — check file/folder access rights."
        if isinstance(exc, FileNotFoundError):
            return "File not found — it may have been moved or deleted."
        if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
            return "Disk is full — free some space and try again."
        return "An unexpected file system error occurred."
