"""
logger.py — Central logging configuration for Secure File Encryptor Pro.

One rotating log file in the per-user app data directory plus an optional
console echo. Every module obtains its logger via :func:`get_logger` so
records carry the module name and share one configuration.

SECURITY NOTE: log messages must never contain passwords, derived keys,
or plaintext file contents — only paths, sizes, durations, and statuses.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.constants import LOG_BACKUP_COUNT, LOG_FILENAME, LOG_MAX_BYTES
from config.settings import get_app_data_dir

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    log_dir: Path | None = None,
    level: int = logging.INFO,
    console: bool = True,
) -> Path:
    """Configure the root logger. Safe to call more than once.

    Args:
        log_dir: Directory for the log file (defaults to the app data dir;
            injectable so tests can use a temp folder).
        level: Minimum level captured.
        console: Also echo records to stderr (useful during development).

    Returns:
        Full path of the active log file.
    """
    target_dir = log_dir if log_dir is not None else get_app_data_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    log_path = target_dir / LOG_FILENAME

    root = logging.getLogger()
    root.setLevel(level)

    # Remove previous handlers so repeated calls never duplicate output.
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler(stream=sys.stderr)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    return log_path


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (thin wrapper kept for a single import point)."""
    return logging.getLogger(name)


def log_app_start() -> None:
    """Record application startup (required by the logging spec)."""
    get_logger("app").info("Application started.")


def log_app_exit() -> None:
    """Record application shutdown (required by the logging spec)."""
    get_logger("app").info("Application exited.")
