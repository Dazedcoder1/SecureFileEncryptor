"""Unit tests for the config layer (constants + SettingsManager).

Run from the project root:
    python -m pytest tests/test_config.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config import constants
from config.settings import AppSettings, SettingsManager


# --------------------------------------------------------------------------
# Constants: security parameters must never silently regress
# --------------------------------------------------------------------------
class TestConstants:
    def test_aes_key_is_256_bit(self) -> None:
        assert constants.KEY_SIZE == 32

    def test_gcm_nonce_is_96_bit(self) -> None:
        assert constants.NONCE_SIZE == 12

    def test_salt_is_at_least_128_bit(self) -> None:
        assert constants.SALT_SIZE >= 16

    def test_pbkdf2_iterations_meet_minimum(self) -> None:
        assert constants.PBKDF2_ITERATIONS >= 100_000

    def test_magic_header_is_four_bytes(self) -> None:
        assert isinstance(constants.MAGIC_HEADER, bytes)
        assert len(constants.MAGIC_HEADER) == 4

    def test_encrypted_extension_format(self) -> None:
        assert constants.ENCRYPTED_EXTENSION.startswith(".")


# --------------------------------------------------------------------------
# SettingsManager behaviour
# --------------------------------------------------------------------------
class TestSettingsManager:
    def test_creates_file_with_defaults(self, tmp_path: Path) -> None:
        manager = SettingsManager(config_dir=tmp_path)
        assert manager.path.exists()
        data = json.loads(manager.path.read_text(encoding="utf-8"))
        assert data["dark_mode"] is True
        assert data["overwrite_existing_files"] is False

    def test_set_persists_and_reloads(self, tmp_path: Path) -> None:
        SettingsManager(config_dir=tmp_path).set("dark_mode", False)
        reloaded = SettingsManager(config_dir=tmp_path)
        assert reloaded.get("dark_mode") is False

    def test_unknown_key_raises_keyerror(self, tmp_path: Path) -> None:
        manager = SettingsManager(config_dir=tmp_path)
        with pytest.raises(KeyError):
            manager.get("no_such_setting")
        with pytest.raises(KeyError):
            manager.set("no_such_setting", 1)

    def test_wrong_type_raises_typeerror(self, tmp_path: Path) -> None:
        manager = SettingsManager(config_dir=tmp_path)
        with pytest.raises(TypeError):
            manager.set("dark_mode", "yes")          # str -> bool field
        with pytest.raises(TypeError):
            manager.set("recent_history_size", True)  # bool -> int field

    def test_corrupt_file_falls_back_to_defaults(self, tmp_path: Path) -> None:
        (tmp_path / "settings.json").write_text("{not valid json", encoding="utf-8")
        manager = SettingsManager(config_dir=tmp_path)
        assert manager.settings == AppSettings()

    def test_unknown_and_badly_typed_keys_ignored_on_load(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "settings.json").write_text(
            json.dumps({"dark_mode": "not-a-bool", "evil_key": 1, "language": "de"}),
            encoding="utf-8",
        )
        manager = SettingsManager(config_dir=tmp_path)
        assert manager.get("dark_mode") is True      # bad type ignored
        assert manager.get("language") == "de"       # valid value applied

    def test_reset_to_defaults(self, tmp_path: Path) -> None:
        manager = SettingsManager(config_dir=tmp_path)
        manager.set("recent_history_size", 42)
        manager.reset_to_defaults()
        assert manager.get("recent_history_size") == AppSettings().recent_history_size
