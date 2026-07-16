"""History database tests: CRUD, filter/search/sort, CSV, pruning, threads.

Run from the project root:
    python -m pytest tests/test_database.py -v
"""

from __future__ import annotations

import csv
import threading
from pathlib import Path

import pytest

from database.database import DatabaseError, HistoryDatabase
from models.records import HistoryRecord, OperationStatus, OperationType


def make_record(
    filename: str = "doc.pdf",
    operation: OperationType = OperationType.ENCRYPT,
    status: OperationStatus = OperationStatus.SUCCESS,
    timestamp: str = "2026-07-16 10:00:00",
    size: int = 1024,
) -> HistoryRecord:
    return HistoryRecord(
        record_id=None,
        timestamp=timestamp,
        operation=operation,
        filename=filename,
        location="C:/Users/demo/Documents",
        size_bytes=size,
        duration_seconds=1.25,
        status=status,
        sha256_hex="ab" * 32,
        error_message="" if status is OperationStatus.SUCCESS else "boom",
    )


@pytest.fixture()
def db(tmp_path: Path) -> HistoryDatabase:
    return HistoryDatabase(db_path=tmp_path / "history.db")


class TestCrud:
    def test_add_and_get_roundtrip(self, db: HistoryDatabase) -> None:
        record_id = db.add_record(make_record())
        assert record_id >= 1
        records = db.get_records()
        assert len(records) == 1
        got = records[0]
        assert got.record_id == record_id
        assert got.filename == "doc.pdf"
        assert got.operation is OperationType.ENCRYPT
        assert got.status is OperationStatus.SUCCESS
        assert got.sha256_hex == "ab" * 32

    def test_delete_record(self, db: HistoryDatabase) -> None:
        record_id = db.add_record(make_record())
        assert db.delete_record(record_id) is True
        assert db.delete_record(record_id) is False  # already gone
        assert db.count_records() == 0

    def test_clear_history(self, db: HistoryDatabase) -> None:
        for _ in range(3):
            db.add_record(make_record())
        assert db.clear_history() == 3
        assert db.count_records() == 0

    def test_prune_keeps_newest(self, db: HistoryDatabase) -> None:
        for i in range(10):
            db.add_record(make_record(filename=f"f{i}.txt"))
        removed = db.prune(max_rows=4)
        assert removed == 6
        names = {r.filename for r in db.get_records()}
        assert names == {"f6.txt", "f7.txt", "f8.txt", "f9.txt"}


class TestQuerying:
    @pytest.fixture()
    def populated(self, db: HistoryDatabase) -> HistoryDatabase:
        db.add_record(
            make_record("alpha.pdf", OperationType.ENCRYPT,
                        OperationStatus.SUCCESS, "2026-07-14 09:00:00", 100)
        )
        db.add_record(
            make_record("beta.zip", OperationType.DECRYPT,
                        OperationStatus.FAILED, "2026-07-15 09:00:00", 300)
        )
        db.add_record(
            make_record("gamma.pdf", OperationType.ENCRYPT,
                        OperationStatus.CANCELLED, "2026-07-16 09:00:00", 200)
        )
        return db

    def test_filter_by_operation(self, populated: HistoryDatabase) -> None:
        records = populated.get_records(operation=OperationType.ENCRYPT)
        assert {r.filename for r in records} == {"alpha.pdf", "gamma.pdf"}

    def test_filter_by_status(self, populated: HistoryDatabase) -> None:
        records = populated.get_records(status=OperationStatus.FAILED)
        assert [r.filename for r in records] == ["beta.zip"]
        assert records[0].error_message == "boom"

    def test_search_is_case_insensitive_substring(
        self, populated: HistoryDatabase
    ) -> None:
        assert {r.filename for r in populated.get_records(search="PDF")} == {
            "alpha.pdf",
            "gamma.pdf",
        }

    def test_sort_by_size_ascending(self, populated: HistoryDatabase) -> None:
        records = populated.get_records(sort_by="size_bytes", descending=False)
        assert [r.size_bytes for r in records] == [100, 200, 300]

    def test_default_sort_newest_first(self, populated: HistoryDatabase) -> None:
        records = populated.get_records()
        assert records[0].filename == "gamma.pdf"

    def test_limit_and_offset(self, populated: HistoryDatabase) -> None:
        page = populated.get_records(limit=1, offset=1)
        assert len(page) == 1
        assert page[0].filename == "beta.zip"

    def test_injection_via_sort_column_rejected(
        self, populated: HistoryDatabase
    ) -> None:
        with pytest.raises(ValueError):
            populated.get_records(sort_by="timestamp; DROP TABLE history--")
        assert populated.count_records() == 3  # table intact

    def test_search_with_sql_metacharacters_is_safe(
        self, populated: HistoryDatabase
    ) -> None:
        assert populated.get_records(search="'; DROP TABLE history--") == []
        assert populated.count_records() == 3


class TestExportAndErrors:
    def test_export_csv(self, db: HistoryDatabase, tmp_path: Path) -> None:
        db.add_record(make_record("alpha.pdf"))
        db.add_record(make_record("beta.zip", status=OperationStatus.FAILED))
        out = tmp_path / "export.csv"
        assert db.export_csv(out) == 2
        with out.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        assert rows[0][:4] == ["id", "timestamp", "operation", "filename"]
        assert len(rows) == 3
        assert {rows[1][3], rows[2][3]} == {"alpha.pdf", "beta.zip"}

    def test_export_csv_respects_filters(
        self, db: HistoryDatabase, tmp_path: Path
    ) -> None:
        db.add_record(make_record("alpha.pdf"))
        db.add_record(make_record("beta.zip", status=OperationStatus.FAILED))
        out = tmp_path / "failed.csv"
        assert db.export_csv(out, status=OperationStatus.FAILED) == 1

    def test_export_to_unwritable_path_raises(self, db: HistoryDatabase) -> None:
        db.add_record(make_record())
        with pytest.raises(DatabaseError):
            db.export_csv(Path("/nonexistent-dir/export.csv"))

    def test_unopenable_database_raises(self, tmp_path: Path) -> None:
        with pytest.raises(DatabaseError):
            HistoryDatabase(db_path=tmp_path / "no_such_dir" / "history.db")


class TestConcurrency:
    def test_parallel_writes_from_threads(self, db: HistoryDatabase) -> None:
        """Workers and GUI thread hit the DB simultaneously in real usage."""
        errors: list[Exception] = []

        def writer(n: int) -> None:
            try:
                for i in range(10):
                    db.add_record(make_record(filename=f"t{n}-{i}.bin"))
            except Exception as exc:  # noqa: BLE001 — collected for assertion
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert db.count_records() == 40
