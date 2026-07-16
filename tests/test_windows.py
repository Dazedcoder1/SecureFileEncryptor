"""Window/dialog tests (headless, offscreen platform).

Dialogs are tested by constructing them, setting fields, and invoking
their accept handlers directly — no exec_() event loops.

Run from the project root:
    python -m pytest tests/test_windows.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt5", reason="PyQt5 required for window tests")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from config.settings import SettingsManager  # noqa: E402
from database.database import HistoryDatabase  # noqa: E402
from models.records import (  # noqa: E402
    HistoryRecord,
    OperationStatus,
    OperationType,
)
from ui.about_window import AboutWindow  # noqa: E402
from ui.decrypt_dialog import DecryptDialog  # noqa: E402
from ui.encrypt_dialog import EncryptDialog  # noqa: E402
from ui.history_window import HistoryWindow  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.settings_window import SettingsWindow  # noqa: E402
from config.constants import APP_VERSION, MAGIC_HEADER  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


@pytest.fixture()
def settings(tmp_path: Path) -> SettingsManager:
    return SettingsManager(config_dir=tmp_path / "cfg")


@pytest.fixture()
def db(tmp_path: Path) -> HistoryDatabase:
    return HistoryDatabase(db_path=tmp_path / "history.db")


def add_history(db: HistoryDatabase, filename: str,
                status: OperationStatus = OperationStatus.SUCCESS) -> None:
    db.add_record(HistoryRecord(
        record_id=None, timestamp="2026-07-16 10:00:00",
        operation=OperationType.ENCRYPT, filename=filename,
        location="C:/demo", size_bytes=2048, duration_seconds=0.5,
        status=status, sha256_hex="cd" * 32,
    ))


class TestEncryptDialog:
    def test_rejects_weak_or_mismatched_password(self, qapp, settings) -> None:
        dialog = EncryptDialog(1, settings)
        dialog.password_field._edit.setText("short")
        dialog.confirm_field._edit.setText("short")
        dialog._on_accept()
        assert dialog.options is None
        assert not dialog.error_label.isHidden()

        dialog.password_field._edit.setText("ValidPass123!")
        dialog.confirm_field._edit.setText("Different123!")
        dialog._on_accept()
        assert dialog.options is None

    def test_rejects_missing_output_dir(self, qapp, settings, tmp_path) -> None:
        dialog = EncryptDialog(1, settings)
        dialog.password_field._edit.setText("ValidPass123!")
        dialog.confirm_field._edit.setText("ValidPass123!")
        dialog.output_edit.setText(str(tmp_path / "does-not-exist"))
        dialog._on_accept()
        assert dialog.options is None
        assert "does not exist" in dialog.error_label.text()

    def test_valid_input_produces_options(self, qapp, settings, tmp_path) -> None:
        dialog = EncryptDialog(2, settings)
        dialog.password_field._edit.setText("ValidPass123!")
        dialog.confirm_field._edit.setText("ValidPass123!")
        dialog.output_edit.setText(str(tmp_path))
        dialog.overwrite_box.setChecked(True)
        dialog._on_accept()

        options = dialog.options
        assert options is not None
        assert options.output_dir == tmp_path
        assert options.overwrite is True
        assert options.password.value == b"ValidPass123!"
        options.password.wipe()

    def test_defaults_come_from_settings(self, qapp, settings, tmp_path) -> None:
        settings.set("default_save_location", str(tmp_path))
        settings.set("overwrite_existing_files", True)
        dialog = EncryptDialog(1, settings)
        assert dialog.output_edit.text() == str(tmp_path)
        assert dialog.overwrite_box.isChecked() is True


class TestDecryptDialog:
    def test_empty_password_rejected(self, qapp, settings) -> None:
        dialog = DecryptDialog(1, settings)
        dialog._on_accept()
        assert dialog.options is None

    def test_weak_password_allowed_for_decrypt(self, qapp, settings) -> None:
        """Decryption must not enforce the creation-time policy."""
        dialog = DecryptDialog(1, settings)
        dialog.password_field._edit.setText("old")  # below policy length
        dialog._on_accept()
        assert dialog.options is not None
        assert dialog.options.password.value == b"old"
        dialog.options.password.wipe()


class TestSettingsWindow:
    def test_save_writes_settings_and_emits(self, qapp, settings) -> None:
        window = SettingsWindow(settings)
        emitted: list[bool] = []
        window.settings_changed.connect(lambda: emitted.append(True))

        window.dark_mode_box.setChecked(False)
        window.recent_spin.setValue(25)
        window.overwrite_box.setChecked(True)
        window._on_save()

        assert emitted == [True]
        assert settings.get("dark_mode") is False
        assert settings.get("recent_history_size") == 25
        assert settings.get("overwrite_existing_files") is True

    def test_restore_defaults(self, qapp, settings) -> None:
        settings.set("recent_history_size", 42)
        window = SettingsWindow(settings)
        window._on_restore_defaults()
        assert settings.get("recent_history_size") == 10
        assert window.recent_spin.value() == 10


class TestHistoryWindow:
    def test_populates_and_filters(self, qapp, db) -> None:
        add_history(db, "alpha.pdf")
        add_history(db, "beta.zip", OperationStatus.FAILED)
        window = HistoryWindow(db)
        assert window.table.rowCount() == 2

        window.search_edit.setText("alpha")
        assert window.table.rowCount() == 1
        assert window.table.item(0, 2).text() == "alpha.pdf"

        window.search_edit.setText("")
        window.status_combo.setCurrentIndex(2)  # Failed
        assert window.table.rowCount() == 1
        assert window.table.item(0, 2).text() == "beta.zip"

    def test_delete_selected(self, qapp, db) -> None:
        add_history(db, "alpha.pdf")
        add_history(db, "beta.zip")
        window = HistoryWindow(db)
        window.table.selectRow(0)
        window._delete_selected()
        assert window.table.rowCount() == 1
        assert db.count_records() == 1


class TestAboutWindow:
    def test_contains_versions_and_link(self, qapp) -> None:
        window = AboutWindow()
        text = window.info_label.text()
        assert APP_VERSION in text
        assert "cryptography" in text
        assert "github.com" in text


class TestMainWindow:
    def test_constructs_with_recent_history(self, qapp, settings, db) -> None:
        add_history(db, "alpha.pdf")
        window = MainWindow(settings, db)
        assert window.dashboard.recent_list.count() == 1
        assert window.windowTitle() == "Secure File Encryptor Pro"

    def test_progress_panel_only_visible_while_busy(
        self, qapp, settings, db
    ) -> None:
        """Regression: an idle 'Ready./0%' strip cluttered the dashboard."""
        window = MainWindow(settings, db)
        dash = window.dashboard
        assert dash.progress.isHidden() and dash.cancel_button.isHidden()
        dash.set_busy(True)
        assert not dash.progress.isHidden()
        assert not dash.cancel_button.isHidden()
        assert not dash.encrypt_button.isEnabled()
        dash.set_busy(False)
        assert dash.progress.isHidden() and dash.cancel_button.isHidden()
        assert dash.encrypt_button.isEnabled()

    def test_drop_zone_never_clips_its_labels(self, qapp, settings, db) -> None:
        """Regression: at high DPI the zone shrank below its content height."""
        window = MainWindow(settings, db)
        window.resize(980, 660)  # near-minimum window
        window.show()
        qapp.processEvents()
        zone = window.dashboard.drop_zone
        assert zone.height() >= 170  # enough for icon + title + subtitle
        window.close()

    def test_classify_paths(self, qapp, tmp_path: Path) -> None:
        plain = tmp_path / "plain.txt"
        plain.write_bytes(b"hello")
        encrypted = tmp_path / "secret.sfep"
        encrypted.write_bytes(MAGIC_HEADER + b"\x01rest-of-header")

        assert MainWindow.classify_paths([plain]) == "encrypt"
        assert MainWindow.classify_paths([encrypted]) == "decrypt"
        assert MainWindow.classify_paths([plain, encrypted]) == "mixed"

    def test_classify_folders(self, qapp, tmp_path: Path) -> None:
        enc_dir = tmp_path / "vault_encrypted"
        enc_dir.mkdir()
        (enc_dir / "a.txt.sfep").write_bytes(MAGIC_HEADER + b"\x01x")
        plain_dir = tmp_path / "docs"
        plain_dir.mkdir()
        (plain_dir / "a.txt").write_bytes(b"x")

        assert MainWindow.classify_paths([enc_dir]) == "decrypt"
        assert MainWindow.classify_paths([plain_dir]) == "encrypt"
