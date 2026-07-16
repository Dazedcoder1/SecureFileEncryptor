"""
database.py — SQLite-backed encryption/decryption history.

Design decisions
----------------
* Connection-per-operation: every public method opens a short-lived
  connection, so the manager is safe to call from QThread workers and
  the GUI thread simultaneously without shared-state locking.
* Parameterized queries everywhere; sort columns are validated against
  a whitelist because column names cannot be parameterized — this keeps
  the search/sort/filter API immune to SQL injection.
* SHA-256 hashes are stored as hex; passwords and keys are NEVER stored.
* All sqlite3 errors are wrapped in :class:`DatabaseError` so upper
  layers catch one exception type and show one friendly message.
"""

from __future__ import annotations

import csv
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config.constants import DB_FILENAME, DEFAULT_HISTORY_LIMIT
from config.settings import get_app_data_dir
from models.records import HistoryRecord, OperationStatus, OperationType
from utils.logger import get_logger

logger = get_logger(__name__)

_SORTABLE_COLUMNS: frozenset[str] = frozenset(
    {"id", "timestamp", "filename", "size_bytes", "duration_seconds", "status"}
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT    NOT NULL,
    operation        TEXT    NOT NULL CHECK (operation IN ('encrypt', 'decrypt')),
    filename         TEXT    NOT NULL,
    location         TEXT    NOT NULL,
    size_bytes       INTEGER NOT NULL,
    duration_seconds REAL    NOT NULL,
    status           TEXT    NOT NULL
                     CHECK (status IN ('success', 'failed', 'cancelled')),
    sha256_hex       TEXT    NOT NULL,
    error_message    TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_history_timestamp ON history (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_history_status    ON history (status);
"""

_CSV_HEADER = [
    "id",
    "timestamp",
    "operation",
    "filename",
    "location",
    "size_bytes",
    "duration_seconds",
    "status",
    "sha256_hex",
    "error_message",
]


class DatabaseError(Exception):
    """Any persistence failure; message is safe to show to the user."""


class HistoryDatabase:
    """Persistence gateway for :class:`models.records.HistoryRecord`."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Create/open the database and ensure the schema exists.

        Args:
            db_path: Override for tests; defaults to
                ``<app data dir>/history.db``.
        """
        self._path = db_path if db_path is not None else (
            get_app_data_dir() / DB_FILENAME
        )
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @property
    def path(self) -> Path:
        return self._path

    # --------------------------------------------------------------- write
    def add_record(self, record: HistoryRecord) -> int:
        """Insert a record and return its assigned id."""
        query = """
            INSERT INTO history (timestamp, operation, filename, location,
                                 size_bytes, duration_seconds, status,
                                 sha256_hex, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            record.timestamp,
            record.operation.value,
            record.filename,
            record.location,
            record.size_bytes,
            record.duration_seconds,
            record.status.value,
            record.sha256_hex,
            record.error_message,
        )
        with self._connect() as conn:
            cursor = conn.execute(query, params)
            record_id = int(cursor.lastrowid)
        logger.info(
            "History: %s %s -> %s",
            record.operation.value,
            record.filename,
            record.status.value,
        )
        return record_id

    def delete_record(self, record_id: int) -> bool:
        """Delete one record; True if a row was actually removed."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM history WHERE id = ?", (record_id,))
            return cursor.rowcount > 0

    def clear_history(self) -> int:
        """Delete every record; returns number of rows removed."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM history")
            return cursor.rowcount

    def prune(self, max_rows: int = DEFAULT_HISTORY_LIMIT) -> int:
        """Keep only the newest ``max_rows`` records (Settings: history size)."""
        if max_rows < 0:
            raise ValueError("max_rows must be non-negative")
        query = """
            DELETE FROM history WHERE id NOT IN
                (SELECT id FROM history ORDER BY id DESC LIMIT ?)
        """
        with self._connect() as conn:
            cursor = conn.execute(query, (max_rows,))
            return cursor.rowcount

    # ---------------------------------------------------------------- read
    def get_records(
        self,
        limit: int | None = None,
        offset: int = 0,
        operation: OperationType | None = None,
        status: OperationStatus | None = None,
        search: str | None = None,
        sort_by: str = "timestamp",
        descending: bool = True,
    ) -> list[HistoryRecord]:
        """Query history with optional filter/search/sort/pagination.

        Args:
            search: Case-insensitive substring match on filename/location.
            sort_by: Whitelisted column name (raises ValueError otherwise).
        """
        if sort_by not in _SORTABLE_COLUMNS:
            raise ValueError(f"Cannot sort by {sort_by!r}")

        clauses: list[str] = []
        params: list[object] = []
        if operation is not None:
            clauses.append("operation = ?")
            params.append(operation.value)
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if search:
            clauses.append("(filename LIKE ? OR location LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])

        query = "SELECT * FROM history"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += f" ORDER BY {sort_by} {'DESC' if descending else 'ASC'}, id DESC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def count_records(self) -> int:
        with self._connect() as conn:
            (count,) = conn.execute("SELECT COUNT(*) FROM history").fetchone()
            return int(count)

    # -------------------------------------------------------------- export
    def export_csv(self, destination: Path, **query_kwargs: object) -> int:
        """Export (optionally filtered) history to CSV; returns row count.

        Accepts the same keyword arguments as :meth:`get_records`.
        """
        records = self.get_records(**query_kwargs)  # type: ignore[arg-type]
        try:
            with destination.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(_CSV_HEADER)
                for r in records:
                    writer.writerow(
                        [
                            r.record_id,
                            r.timestamp,
                            r.operation.value,
                            r.filename,
                            r.location,
                            r.size_bytes,
                            f"{r.duration_seconds:.2f}",
                            r.status.value,
                            r.sha256_hex,
                            r.error_message,
                        ]
                    )
        except OSError as exc:
            raise DatabaseError(f"Could not write CSV: {exc}") from exc
        logger.info("Exported %d history rows to %s", len(records), destination)
        return len(records)

    # ------------------------------------------------------------- helpers
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Short-lived connection with commit/rollback and error wrapping."""
        try:
            conn = sqlite3.connect(self._path, timeout=10.0)
        except sqlite3.Error as exc:
            raise DatabaseError(f"Could not open history database: {exc}") from exc
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"History database error: {exc}") from exc
        finally:
            conn.close()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> HistoryRecord:
        return HistoryRecord(
            record_id=row["id"],
            timestamp=row["timestamp"],
            operation=OperationType(row["operation"]),
            filename=row["filename"],
            location=row["location"],
            size_bytes=row["size_bytes"],
            duration_seconds=row["duration_seconds"],
            status=OperationStatus(row["status"]),
            sha256_hex=row["sha256_hex"],
            error_message=row["error_message"],
        )
