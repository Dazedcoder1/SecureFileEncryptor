"""
main_window.py — Application shell and single controller.

Owns the toolbar, status bar, dashboard, dialogs, theme toggle, and the
lifecycle of exactly one background worker at a time. All routing
decisions (encrypt vs decrypt vs mixed drops) happen here; views only
render and emit.
"""

from __future__ import annotations

from itertools import islice
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QToolBar,
    QWidget,
)

from config.constants import (
    APP_NAME,
    ENCRYPTED_EXTENSION,
    STATUS_MESSAGE_TIMEOUT_MS,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
)
from config.settings import SettingsManager
from database.database import DatabaseError, HistoryDatabase
from models.records import CryptoResult
from ui.about_window import AboutWindow
from ui.dashboard import Dashboard
from ui.decrypt_dialog import DecryptDialog
from ui.encrypt_dialog import CryptoJobOptions, EncryptDialog
from ui.history_window import HistoryWindow
from ui.settings_window import SettingsWindow
from ui.theme import apply_theme
from utils.logger import get_logger
from utils.validator import is_encrypted_file
from workers.base_worker import BaseCryptoWorker
from workers.decrypt_worker import DecryptWorker, build_decrypt_jobs
from workers.encrypt_worker import EncryptWorker, build_encrypt_jobs

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """Top-level window; composition root for the UI layer."""

    def __init__(
        self,
        settings: SettingsManager,
        database: HistoryDatabase,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._db = database
        self._worker: BaseCryptoWorker | None = None
        self._integrity_failures: list[str] = []

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        self.dashboard = Dashboard(self)
        self.setCentralWidget(self.dashboard)
        self.dashboard.encrypt_clicked.connect(self._pick_files_to_encrypt)
        self.dashboard.decrypt_clicked.connect(self._pick_files_to_decrypt)
        self.dashboard.browse_requested.connect(self._pick_files_to_encrypt)
        self.dashboard.paths_dropped.connect(self._route_dropped_paths)
        self.dashboard.cancel_clicked.connect(self._cancel_current)

        self._build_toolbar()
        self.statusBar().showMessage("Ready.")
        self._refresh_recent()

    # ------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(toolbar)

        def add(text: str, slot, tooltip: str) -> QAction:
            action = QAction(text, self)
            action.setToolTip(tooltip)
            action.triggered.connect(slot)
            toolbar.addAction(action)
            return action

        add("Encrypt", self._pick_files_to_encrypt, "Encrypt files")
        add("Encrypt Folder", self._pick_folder_to_encrypt, "Encrypt a folder")
        add("Decrypt", self._pick_files_to_decrypt, "Decrypt files")
        toolbar.addSeparator()
        add("History", self._show_history, "View encryption history")
        add("Settings", self._show_settings, "Preferences")
        add("About", self._show_about, "About this application")

        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().Expanding,
                             spacer.sizePolicy().Preferred)
        toolbar.addWidget(spacer)
        self.theme_action = add(
            "\U0001f313", self._toggle_theme, "Toggle dark/light theme"
        )

    # ----------------------------------------------------------- selection
    def _pick_files_to_encrypt(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select files to encrypt")
        if files:
            self.start_encryption([Path(f) for f in files])

    def _pick_folder_to_encrypt(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder to encrypt")
        if folder:
            self.start_encryption([Path(folder)])

    def _pick_files_to_decrypt(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select files to decrypt",
            filter=f"Encrypted files (*{ENCRYPTED_EXTENSION});;All files (*)",
        )
        if files:
            self.start_decryption([Path(f) for f in files])

    def _route_dropped_paths(self, paths: list[Path]) -> None:
        """Auto-detect what the user dropped and route accordingly."""
        kind = self.classify_paths(paths)
        if kind == "mixed":
            self.dashboard.banner.show_message(
                "Mix of encrypted and plain items dropped — please drop "
                "one kind at a time.", "error",
            )
            return
        if kind == "decrypt":
            self.start_decryption(paths)
        else:
            self.start_encryption(paths)

    #: Max files sampled per dropped folder — classification runs on the
    #: GUI thread, so a 100k-file tree must not freeze the drop gesture.
    _CLASSIFY_SCAN_LIMIT = 256

    @classmethod
    def classify_paths(cls, paths: list[Path]) -> str:
        """'encrypt', 'decrypt', or 'mixed' for a dropped selection.

        A folder counts as encrypted when it contains SFEP files and
        nothing else; anything else is treated as plaintext input.
        Folders are sampled (first N files) — this is only a routing
        heuristic; workers still validate every file properly.
        """
        encrypted = plain = 0
        for path in paths:
            if path.is_file():
                if is_encrypted_file(path):
                    encrypted += 1
                else:
                    plain += 1
            elif path.is_dir():
                sample = list(islice(
                    (f for f in path.rglob("*") if f.is_file()),
                    cls._CLASSIFY_SCAN_LIMIT,
                ))
                sfep = [f for f in sample
                        if f.suffix == ENCRYPTED_EXTENSION]
                if sample and len(sfep) == len(sample):
                    encrypted += 1
                else:
                    plain += 1
        if encrypted and plain:
            return "mixed"
        return "decrypt" if encrypted else "encrypt"

    # ------------------------------------------------------------ workers
    def start_encryption(self, paths: list[Path]) -> None:
        if self._busy():
            return
        dialog = EncryptDialog(len(paths), self._settings, self)
        if dialog.exec_() != EncryptDialog.Accepted or dialog.options is None:
            return
        options = dialog.options
        jobs = build_encrypt_jobs(paths, options.output_dir)
        if not jobs:
            self.dashboard.banner.show_message(
                "Nothing to encrypt in the selection.", "error"
            )
            options.password.wipe()
            return
        worker = EncryptWorker(
            jobs, options.password, database=self._db,
            overwrite=options.overwrite,
        )
        self._launch(worker, f"Encrypting {len(jobs)} file(s)…")

    def start_decryption(self, paths: list[Path]) -> None:
        if self._busy():
            return
        dialog = DecryptDialog(len(paths), self._settings, self)
        if dialog.exec_() != DecryptDialog.Accepted or dialog.options is None:
            return
        options = dialog.options
        jobs = build_decrypt_jobs(paths, options.output_dir)
        if not jobs:
            self.dashboard.banner.show_message(
                "No encrypted files found in the selection.", "error"
            )
            options.password.wipe()
            return
        worker = DecryptWorker(
            jobs, options.password, database=self._db,
            overwrite=options.overwrite,
        )
        self._launch(worker, f"Decrypting {len(jobs)} file(s)…")

    def _launch(self, worker: BaseCryptoWorker, status: str) -> None:
        self._integrity_failures.clear()
        self._worker = worker
        worker.progress_updated.connect(self.dashboard.progress.update_progress)
        worker.file_completed.connect(self._on_file_completed)
        worker.file_failed.connect(self._on_file_failed)
        worker.batch_finished.connect(self._on_batch_finished)
        worker.finished.connect(worker.deleteLater)
        self.dashboard.set_busy(True)
        self.statusBar().showMessage(status)
        worker.start()

    def _busy(self) -> bool:
        if self._worker is not None and self._worker.isRunning():
            self.dashboard.banner.show_message(
                "Another operation is already running.", "info"
            )
            return True
        return False

    def _cancel_current(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_cancel()
            self.statusBar().showMessage("Cancelling…")

    # ------------------------------------------------------ worker slots
    def _on_file_completed(self, result: CryptoResult) -> None:
        if (
            result.integrity_ok is False
            and self._settings.get("auto_verify_integrity")
        ):
            self._integrity_failures.append(result.source.name)

    def _on_file_failed(self, filename: str, message: str) -> None:
        self.dashboard.banner.show_message(f"{filename}: {message}", "error")

    def _on_batch_finished(
        self, succeeded: int, failed: int, cancelled: bool
    ) -> None:
        self.dashboard.set_busy(False)
        self._worker = None
        self._refresh_recent()

        if cancelled:
            self.dashboard.banner.show_message("Operation cancelled.", "info")
            self.statusBar().showMessage("Cancelled.", STATUS_MESSAGE_TIMEOUT_MS)
            return
        if self._integrity_failures:
            names = ", ".join(self._integrity_failures)
            self.dashboard.banner.show_message(
                f"Integrity FAILED for: {names}", "error"
            )
        elif failed:
            self.dashboard.banner.show_message(
                f"Done with errors — {succeeded} succeeded, {failed} failed.",
                "error",
            )
        else:
            suffix = " Integrity verified." if (
                self._settings.get("auto_verify_integrity")
            ) else ""
            self.dashboard.banner.show_message(
                f"{succeeded} file(s) processed successfully.{suffix}",
                "success",
            )
        self.statusBar().showMessage("Ready.", STATUS_MESSAGE_TIMEOUT_MS)

    # ------------------------------------------------------------ dialogs
    def _show_history(self) -> None:
        HistoryWindow(self._db, self).exec_()
        self._refresh_recent()

    def _show_settings(self) -> None:
        dialog = SettingsWindow(self._settings, self)
        dialog.settings_changed.connect(self._apply_settings)
        dialog.exec_()

    def _show_about(self) -> None:
        AboutWindow(self).exec_()

    # ------------------------------------------------------------- helpers
    def _apply_settings(self) -> None:
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, dark=bool(self._settings.get("dark_mode")))
        self._refresh_recent()

    def _toggle_theme(self) -> None:
        dark = not bool(self._settings.get("dark_mode"))
        self._settings.set("dark_mode", dark)
        self._apply_settings()

    def _refresh_recent(self) -> None:
        try:
            records = self._db.get_records(
                limit=int(self._settings.get("recent_history_size"))
            )
        except DatabaseError as exc:
            logger.error("Could not load recent history: %s", exc)
            return
        self.dashboard.set_recent(records)

    # --------------------------------------------------------------- exit
    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker is not None and self._worker.isRunning():
            answer = QMessageBox.question(
                self, "Operation in progress",
                "An operation is still running. Cancel it and exit?",
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._worker.request_cancel()
            self._worker.wait(5000)
        event.accept()
