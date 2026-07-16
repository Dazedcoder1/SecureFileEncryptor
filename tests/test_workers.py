"""Worker tests: batches, folder roundtrip, failures, cancellation, signals.

Workers are exercised synchronously by calling run() directly — the
threading behaviour belongs to Qt (QThread.start), while OUR logic is
everything inside run(), which is what these tests pin down.

Run from the project root:
    python -m pytest tests/test_workers.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt5", reason="PyQt5 required for worker tests")
from PyQt5.QtCore import QCoreApplication  # noqa: E402

from config.constants import ENCRYPTED_EXTENSION  # noqa: E402
from crypto.password_manager import SecurePassword  # noqa: E402
from database.database import HistoryDatabase  # noqa: E402
from models.records import (  # noqa: E402
    CryptoResult,
    OperationStatus,
    OperationType,
    ProgressUpdate,
)
from workers.decrypt_worker import DecryptWorker, build_decrypt_jobs  # noqa: E402
from workers.encrypt_worker import EncryptWorker, build_encrypt_jobs  # noqa: E402

ITER = 2048
PASSWORD = "CorrectHorse7!battery"


@pytest.fixture(scope="session")
def qapp() -> QCoreApplication:
    app = QCoreApplication.instance()
    return app if app is not None else QCoreApplication(sys.argv[:1])


@pytest.fixture()
def db(tmp_path: Path) -> HistoryDatabase:
    return HistoryDatabase(db_path=tmp_path / "history.db")


class Collector:
    """Captures every signal a worker emits."""

    def __init__(self, worker) -> None:
        self.progress: list[ProgressUpdate] = []
        self.completed: list[CryptoResult] = []
        self.failed: list[tuple[str, str]] = []
        self.finished: list[tuple[int, int, bool]] = []
        worker.progress_updated.connect(self.progress.append)
        worker.file_completed.connect(self.completed.append)
        worker.file_failed.connect(lambda n, m: self.failed.append((n, m)))
        worker.batch_finished.connect(
            lambda ok, bad, cancelled: self.finished.append((ok, bad, cancelled))
        )


def make_tree(root: Path) -> dict[str, bytes]:
    """Small folder with nested structure; returns {relative: content}."""
    files = {
        "a.txt": b"alpha" * 200,
        "nested/b.bin": bytes(range(256)) * 64,
        "nested/deep/c.dat": b"\x00\xffgamma" * 333,
    }
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return files


class TestJobBuilding:
    def test_file_jobs(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"x" * 10)
        jobs = build_encrypt_jobs([f])
        assert jobs == [(f, tmp_path / ("doc.pdf" + ENCRYPTED_EXTENSION))]

    def test_folder_jobs_preserve_structure(self, tmp_path: Path) -> None:
        src_root = tmp_path / "vault"
        make_tree(src_root)
        jobs = build_encrypt_jobs([src_root])
        destinations = {str(d.relative_to(tmp_path / "vault_encrypted")) for _, d in jobs}
        assert destinations == {
            "a.txt" + ENCRYPTED_EXTENSION,
            str(Path("nested") / ("b.bin" + ENCRYPTED_EXTENSION)),
            str(Path("nested") / "deep" / ("c.dat" + ENCRYPTED_EXTENSION)),
        }

    def test_decrypt_folder_jobs_skip_foreign_files(self, tmp_path: Path) -> None:
        folder = tmp_path / "mixed"
        folder.mkdir()
        (folder / "readme.txt").write_bytes(b"not encrypted")
        jobs = build_decrypt_jobs([folder])
        assert jobs == []


class TestEncryptWorker:
    def test_batch_success_signals_and_history(
        self, qapp, db, tmp_path: Path
    ) -> None:
        files = []
        for name in ("one.txt", "two.txt"):
            f = tmp_path / name
            f.write_bytes(name.encode() * 500)
            files.append(f)

        worker = EncryptWorker(
            build_encrypt_jobs(files),
            SecurePassword(PASSWORD),
            database=db,
            iterations=ITER,
        )
        signals = Collector(worker)
        worker.run()

        assert signals.finished == [(2, 0, False)]
        assert len(signals.completed) == 2
        assert signals.failed == []
        for f in files:
            assert (tmp_path / (f.name + ENCRYPTED_EXTENSION)).exists()
        records = db.get_records(operation=OperationType.ENCRYPT)
        assert len(records) == 2
        assert all(r.status is OperationStatus.SUCCESS for r in records)
        assert all(len(r.sha256_hex) == 64 for r in records)

    def test_progress_reports_batch_percent(self, qapp, tmp_path: Path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"z" * 200_000)
        worker = EncryptWorker(
            build_encrypt_jobs([f]), SecurePassword(PASSWORD), iterations=ITER
        )
        signals = Collector(worker)
        worker.run()
        assert signals.progress
        last = signals.progress[-1]
        assert last.percent == 100
        assert last.current_file == "data.bin"
        assert last.file_index == last.file_count == 1

    def test_missing_file_fails_batch_continues(
        self, qapp, db, tmp_path: Path
    ) -> None:
        good = tmp_path / "good.txt"
        good.write_bytes(b"fine" * 100)
        ghost = tmp_path / "ghost.txt"  # never created
        jobs = build_encrypt_jobs([good]) + [(ghost, tmp_path / "ghost.sfep")]

        worker = EncryptWorker(
            jobs, SecurePassword(PASSWORD), database=db, iterations=ITER
        )
        signals = Collector(worker)
        worker.run()

        assert signals.finished == [(1, 1, False)]
        assert signals.failed[0][0] == "ghost.txt"
        statuses = {r.filename: r.status for r in db.get_records()}
        assert statuses["good.txt"] is OperationStatus.SUCCESS
        assert statuses["ghost.txt"] is OperationStatus.FAILED

    def test_no_overwrite_creates_unique_name(self, qapp, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_bytes(b"data" * 100)
        existing = tmp_path / ("doc.txt" + ENCRYPTED_EXTENSION)
        existing.write_bytes(b"old file, do not touch")

        worker = EncryptWorker(
            build_encrypt_jobs([f]),
            SecurePassword(PASSWORD),
            overwrite=False,
            iterations=ITER,
        )
        Collector(worker)
        worker.run()

        assert existing.read_bytes() == b"old file, do not touch"
        assert (tmp_path / f"doc.txt (1){ENCRYPTED_EXTENSION}").exists()

    def test_cancel_before_start(self, qapp, db, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_bytes(b"data" * 100)
        worker = EncryptWorker(
            build_encrypt_jobs([f]),
            SecurePassword(PASSWORD),
            database=db,
            iterations=ITER,
        )
        signals = Collector(worker)
        worker.request_cancel()
        worker.run()

        assert signals.finished == [(0, 0, True)]
        assert db.get_records()[0].status is OperationStatus.CANCELLED
        assert not (tmp_path / ("doc.txt" + ENCRYPTED_EXTENSION)).exists()

    def test_password_wiped_after_run(self, qapp, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_bytes(b"data" * 100)
        password = SecurePassword(PASSWORD)
        worker = EncryptWorker(
            build_encrypt_jobs([f]), password, iterations=ITER
        )
        Collector(worker)
        worker.run()
        assert password.is_wiped


class TestDecryptWorker:
    def test_folder_roundtrip_preserves_tree_and_content(
        self, qapp, db, tmp_path: Path
    ) -> None:
        src_root = tmp_path / "vault"
        originals = make_tree(src_root)

        enc = EncryptWorker(
            build_encrypt_jobs([src_root]),
            SecurePassword(PASSWORD),
            database=db,
            iterations=ITER,
        )
        Collector(enc)
        enc.run()

        enc_root = tmp_path / "vault_encrypted"
        dec = DecryptWorker(
            build_decrypt_jobs([enc_root]),
            SecurePassword(PASSWORD),
            database=db,
        )
        dec_signals = Collector(dec)
        dec.run()

        assert dec_signals.finished == [(3, 0, False)]
        assert all(r.integrity_ok is True for r in dec_signals.completed)
        dec_root = tmp_path / "vault_encrypted_decrypted"
        for rel, content in originals.items():
            assert (dec_root / rel).read_bytes() == content

    def test_wrong_password_reported_per_file(
        self, qapp, db, tmp_path: Path
    ) -> None:
        f = tmp_path / "secret.txt"
        f.write_bytes(b"classified" * 50)
        enc = EncryptWorker(
            build_encrypt_jobs([f]), SecurePassword(PASSWORD), iterations=ITER
        )
        Collector(enc)
        enc.run()

        encrypted = tmp_path / ("secret.txt" + ENCRYPTED_EXTENSION)
        dec = DecryptWorker(
            build_decrypt_jobs([encrypted]),
            SecurePassword("TotallyWrong99!"),
            database=db,
        )
        signals = Collector(dec)
        dec.run()

        assert signals.finished == [(1 - 1, 1, False)]
        assert "password" in signals.failed[0][1].lower()
        record = db.get_records(operation=OperationType.DECRYPT)[0]
        assert record.status is OperationStatus.FAILED

    def test_plain_file_rejected(self, qapp, tmp_path: Path) -> None:
        plain = tmp_path / "plain.txt"
        plain.write_bytes(b"just text")
        dec = DecryptWorker(
            [(plain, tmp_path / "out.txt")], SecurePassword(PASSWORD)
        )
        signals = Collector(dec)
        dec.run()
        assert signals.finished == [(0, 1, False)]
        assert "not a secure file encryptor" in signals.failed[0][1].lower()
