"""End-to-end integration test: real QThreads, queued signals, full stack.

Unlike test_workers.py (which calls run() synchronously), this test
starts actual worker threads through MainWindow._launch and pumps the
Qt event loop until queued signals land — proving the GUI wiring works
with genuine cross-thread delivery.

Run from the project root:
    python -m pytest tests/test_app.py -v
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("PyQt5", reason="PyQt5 required for integration tests")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from config.constants import ENCRYPTED_EXTENSION  # noqa: E402
from config.settings import SettingsManager  # noqa: E402
from crypto.password_manager import SecurePassword  # noqa: E402
from database.database import HistoryDatabase  # noqa: E402
from models.records import OperationStatus  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from workers.decrypt_worker import DecryptWorker, build_decrypt_jobs  # noqa: E402
from workers.encrypt_worker import EncryptWorker, build_encrypt_jobs  # noqa: E402

ITER = 2048
PASSWORD = "CorrectHorse7!battery"
TIMEOUT_S = 30.0


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


@pytest.fixture()
def window(tmp_path: Path) -> MainWindow:
    settings = SettingsManager(config_dir=tmp_path / "cfg")
    database = HistoryDatabase(db_path=tmp_path / "history.db")
    return MainWindow(settings, database)


def pump_until_idle(qapp: QApplication, window: MainWindow) -> None:
    """Process events until the window's worker fully finishes."""
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        qapp.processEvents()
        if window._worker is None:
            qapp.processEvents()  # flush deleteLater and trailing signals
            return
        time.sleep(0.01)
    pytest.fail("Worker did not finish within the timeout")


class TestEndToEnd:
    def test_threaded_encrypt_then_decrypt(
        self, qapp: QApplication, window: MainWindow, tmp_path: Path
    ) -> None:
        # ----------------------------------------------------- fixture data
        originals: dict[str, bytes] = {}
        for name in ("report.pdf", "photo.jpg"):
            content = os.urandom(64_000) + name.encode()
            (tmp_path / name).write_bytes(content)
            originals[name] = content
        sources = [tmp_path / n for n in originals]

        # --------------------------------------------------------- encrypt
        worker = EncryptWorker(
            build_encrypt_jobs(sources),
            SecurePassword(PASSWORD),
            database=window._db,
            iterations=ITER,
        )
        window._launch(worker, "Encrypting…")
        assert not window.dashboard.encrypt_button.isEnabled()  # busy state
        pump_until_idle(qapp, window)

        assert window.dashboard.encrypt_button.isEnabled()
        assert window.dashboard.banner.level == "success"
        assert "2 file(s) processed successfully" in window.dashboard.banner.message
        encrypted = [
            tmp_path / (n + ENCRYPTED_EXTENSION) for n in originals
        ]
        assert all(p.exists() for p in encrypted)
        assert window.dashboard.recent_list.count() == 2

        # --------------------------------------------------------- decrypt
        out_dir = tmp_path / "restored"
        out_dir.mkdir()
        worker = DecryptWorker(
            build_decrypt_jobs(encrypted, output_dir=out_dir),
            SecurePassword(PASSWORD, enforce_policy=False),
            database=window._db,
        )
        window._launch(worker, "Decrypting…")
        pump_until_idle(qapp, window)

        assert window.dashboard.banner.level == "success"
        assert "Integrity verified" in window.dashboard.banner.message
        for name, content in originals.items():
            assert (out_dir / name).read_bytes() == content

        # --------------------------------------------------------- history
        records = window._db.get_records()
        assert len(records) == 4
        assert all(r.status is OperationStatus.SUCCESS for r in records)

    def test_threaded_wrong_password_shows_error(
        self, qapp: QApplication, window: MainWindow, tmp_path: Path
    ) -> None:
        source = tmp_path / "secret.txt"
        source.write_bytes(b"classified" * 100)

        worker = EncryptWorker(
            build_encrypt_jobs([source]),
            SecurePassword(PASSWORD),
            database=window._db,
            iterations=ITER,
        )
        window._launch(worker, "Encrypting…")
        pump_until_idle(qapp, window)

        encrypted = tmp_path / ("secret.txt" + ENCRYPTED_EXTENSION)
        worker = DecryptWorker(
            build_decrypt_jobs([encrypted]),
            SecurePassword("WrongPassword1!", enforce_policy=False),
            database=window._db,
        )
        window._launch(worker, "Decrypting…")
        pump_until_idle(qapp, window)

        assert window.dashboard.banner.level == "error"
        failed = window._db.get_records(status=OperationStatus.FAILED)
        assert len(failed) == 1
        assert "password" in failed[0].error_message.lower()
