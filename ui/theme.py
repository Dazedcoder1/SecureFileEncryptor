"""
theme.py — Theme loading and application (dark / light QSS).

Stylesheets live in assets/themes/*.qss and are resolved relative to the
project root — no hardcoded absolute paths, works from any install
location and inside a PyInstaller bundle (sys._MEIPASS aware).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from utils.logger import get_logger

logger = get_logger(__name__)

_DARK_FILE = "dark.qss"
_LIGHT_FILE = "light.qss"


def _themes_dir() -> Path:
    """Locate assets/themes both in source checkouts and frozen builds."""
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        root = Path(__file__).resolve().parents[1]
    return root / "assets" / "themes"


def load_stylesheet(dark: bool = True) -> str:
    """Return the QSS text for the requested theme ('' on failure).

    A missing stylesheet is logged, not fatal — the app degrades to the
    native platform look instead of crashing.
    """
    path = _themes_dir() / (_DARK_FILE if dark else _LIGHT_FILE)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not load theme %s: %s", path.name, exc)
        return ""


def apply_theme(app: QApplication, dark: bool = True) -> None:
    """Apply the theme to the whole application at runtime."""
    app.setStyleSheet(load_stylesheet(dark))
    logger.info("Applied %s theme.", "dark" if dark else "light")


def repolish(widget) -> None:
    """Force a widget to re-evaluate QSS after a dynamic property change."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
