"""
settings.py — Persistent user settings for Secure File Encryptor Pro.

Settings are stored as JSON in the per-user application data directory
(e.g. %APPDATA%\\SecureFileEncryptorPro on Windows). This module is
deliberately Qt-free: in Clean Architecture the configuration layer must
have zero UI dependencies, so it can be unit-tested headlessly and reused
by a future CLI front-end.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from config.constants import DEFAULT_HISTORY_LIMIT

logger = logging.getLogger(__name__)

_SETTINGS_FILENAME = "settings.json"
_APP_DIR_NAME = "SecureFileEncryptorPro"


def get_app_data_dir() -> Path:
    """Return (and create if needed) the per-user data directory.

    Windows:  %APPDATA%\\SecureFileEncryptorPro
    macOS:    ~/Library/Application Support/SecureFileEncryptorPro
    Linux:    $XDG_CONFIG_HOME/SecureFileEncryptorPro (or ~/.config/...)
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    app_dir = base / _APP_DIR_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


@dataclass
class AppSettings:
    """User-configurable options with safe defaults.

    Adding a new setting = add one field here. Load/save/validation
    pick it up automatically via dataclass introspection.
    """

    dark_mode: bool = True
    default_save_location: str = ""          # "" => same folder as source file
    auto_verify_integrity: bool = True
    auto_clear_temp_files: bool = True
    overwrite_existing_files: bool = False
    language: str = "en"                     # i18n-ready
    recent_history_size: int = 10
    history_limit: int = DEFAULT_HISTORY_LIMIT


class SettingsManager:
    """Thread-safe load/save wrapper around :class:`AppSettings`.

    Example:
        >>> manager = SettingsManager()
        >>> manager.get("dark_mode")
        True
        >>> manager.set("dark_mode", False)   # persists immediately

    ``config_dir`` is injectable so tests can point it at a temp folder
    (Dependency Inversion — no hidden global paths).
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._dir: Path = config_dir if config_dir is not None else get_app_data_dir()
        self._path: Path = self._dir / _SETTINGS_FILENAME
        self._settings = AppSettings()
        self.load()

    # ------------------------------------------------------------------ api
    @property
    def path(self) -> Path:
        """Full path of the settings JSON file."""
        return self._path

    @property
    def settings(self) -> AppSettings:
        """Direct (read-mostly) access to the settings dataclass."""
        return self._settings

    def get(self, key: str) -> Any:
        """Return the value of a setting.

        Raises:
            KeyError: if ``key`` is not a known setting.
        """
        with self._lock:
            if not hasattr(self._settings, key):
                raise KeyError(f"Unknown setting: {key!r}")
            return getattr(self._settings, key)

    def set(self, key: str, value: Any, persist: bool = True) -> None:
        """Update a setting, with type validation, and persist by default.

        Raises:
            KeyError:  if ``key`` is not a known setting.
            TypeError: if ``value`` has the wrong type for that setting.
        """
        with self._lock:
            if not hasattr(self._settings, key):
                raise KeyError(f"Unknown setting: {key!r}")
            expected = type(getattr(self._settings, key))
            if not isinstance(value, expected) or (
                expected is int and isinstance(value, bool)
            ):
                raise TypeError(
                    f"Setting {key!r} expects {expected.__name__}, "
                    f"got {type(value).__name__}"
                )
            setattr(self._settings, key, value)
            if persist:
                self.save()

    def reset_to_defaults(self) -> None:
        """Restore every setting to its default and persist."""
        with self._lock:
            self._settings = AppSettings()
            self.save()

    # ------------------------------------------------------------ load/save
    def load(self) -> None:
        """Load settings from disk; unknown/invalid entries are ignored.

        A missing file is created with defaults. A corrupted file is
        logged and replaced by defaults — the app must always start.
        """
        with self._lock:
            if not self._path.exists():
                self.save()
                return
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("settings root must be a JSON object")
            except (OSError, ValueError) as exc:
                logger.warning("Unreadable settings file (%s); using defaults.", exc)
                self._settings = AppSettings()
                return

            defaults = AppSettings()
            known = {f.name for f in fields(AppSettings)}
            for key, value in data.items():
                if key not in known:
                    logger.warning("Ignoring unknown setting %r", key)
                    continue
                expected = type(getattr(defaults, key))
                if isinstance(value, expected) and not (
                    expected is int and isinstance(value, bool)
                ):
                    setattr(self._settings, key, value)
                else:
                    logger.warning("Ignoring badly typed setting %r=%r", key, value)

    def save(self) -> None:
        """Write current settings to disk as pretty-printed JSON."""
        with self._lock:
            try:
                self._dir.mkdir(parents=True, exist_ok=True)
                self._path.write_text(
                    json.dumps(asdict(self._settings), indent=2, sort_keys=True),
                    encoding="utf-8",
                )
            except OSError as exc:
                logger.error("Failed to save settings: %s", exc)
