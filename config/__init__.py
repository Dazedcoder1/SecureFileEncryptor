"""Configuration layer: application constants and persistent user settings."""

from config.settings import AppSettings, SettingsManager, get_app_data_dir

__all__ = ["AppSettings", "SettingsManager", "get_app_data_dir"]
