"""
app.py — Secure File Encryptor Pro entry point.

Boot order matters:
  1. logging (so every later failure is captured),
  2. Qt high-DPI attributes (must precede QApplication),
  3. QApplication + global exception hook,
  4. settings, database (pruned to the configured limit), theme,
  5. main window, event loop, exit logging.

Run:
    python app.py
"""

from __future__ import annotations

import sys
from types import TracebackType

from PyQt5.QtCore import Qt, QThread
from PyQt5.QtWidgets import QApplication, QMessageBox

from config.constants import APP_NAME, APP_VERSION, ORGANIZATION_NAME
from config.settings import SettingsManager
from database.database import DatabaseError, HistoryDatabase
from ui.main_window import MainWindow
from ui.theme import apply_theme
from utils.logger import get_logger, log_app_exit, log_app_start, setup_logging

logger = get_logger(__name__)


def _install_excepthook() -> None:
    """Log any unhandled exception and tell the user, instead of dying silently."""

    def handle(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        logger.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
        # Widgets may only be touched from the GUI thread; if the crash
        # happened on a worker thread, the log entry is the report.
        app = QApplication.instance()
        if app is not None and QThread.currentThread() is app.thread():
            QMessageBox.critical(
                None,
                APP_NAME,
                "An unexpected error occurred. Details were written to the "
                "application log.",
            )

    sys.excepthook = handle


def main(argv: list[str] | None = None) -> int:
    """Build and run the application; returns the process exit code."""
    argv = list(sys.argv if argv is None else argv)

    setup_logging()
    log_app_start()

    # High-DPI support must be configured before QApplication exists.
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORGANIZATION_NAME)
    _install_excepthook()

    settings = SettingsManager()
    try:
        database = HistoryDatabase()
        database.prune(int(settings.get("history_limit")))
    except DatabaseError as exc:
        logger.critical("Cannot open history database: %s", exc)
        QMessageBox.critical(None, APP_NAME, str(exc))
        return 1

    apply_theme(app, dark=bool(settings.get("dark_mode")))

    window = MainWindow(settings, database)
    window.show()

    exit_code = app.exec_()
    log_app_exit()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
