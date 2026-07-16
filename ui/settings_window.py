"""
settings_window.py — User preferences dialog bound to SettingsManager.

Widgets are populated from current settings on open and written back
atomically on Save. Emits settings_changed so the main window can
re-apply the theme immediately.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config.settings import SettingsManager


class SettingsWindow(QDialog):
    """Modal preferences dialog."""

    settings_changed = pyqtSignal()

    def __init__(
        self, settings: SettingsManager, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(440)
        self._settings = settings

        self.dark_mode_box = QCheckBox("Dark mode")
        self.verify_box = QCheckBox("Verify integrity after decryption")
        self.clear_temp_box = QCheckBox("Auto-clear temporary files")
        self.overwrite_box = QCheckBox("Overwrite existing files by default")

        self.save_location_edit = QLineEdit()
        self.save_location_edit.setPlaceholderText("Same folder as source files")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_save_location)
        location_row = QHBoxLayout()
        location_row.addWidget(self.save_location_edit, stretch=1)
        location_row.addWidget(browse)

        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")  # i18n-ready

        self.recent_spin = QSpinBox()
        self.recent_spin.setRange(1, 50)

        form = QFormLayout()
        form.addRow(self.dark_mode_box)
        form.addRow(self.verify_box)
        form.addRow(self.clear_temp_box)
        form.addRow(self.overwrite_box)
        form.addRow("Default save location:", location_row)
        form.addRow("Language:", self.language_combo)
        form.addRow("Recent items shown:", self.recent_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save
            | QDialogButtonBox.Cancel
            | QDialogButtonBox.RestoreDefaults
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(
            self._on_restore_defaults
        )

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._load_from_settings()

    # ------------------------------------------------------------ private
    def _load_from_settings(self) -> None:
        s = self._settings
        self.dark_mode_box.setChecked(bool(s.get("dark_mode")))
        self.verify_box.setChecked(bool(s.get("auto_verify_integrity")))
        self.clear_temp_box.setChecked(bool(s.get("auto_clear_temp_files")))
        self.overwrite_box.setChecked(bool(s.get("overwrite_existing_files")))
        self.save_location_edit.setText(str(s.get("default_save_location")))
        index = self.language_combo.findData(s.get("language"))
        self.language_combo.setCurrentIndex(max(index, 0))
        self.recent_spin.setValue(int(s.get("recent_history_size")))

    def _browse_save_location(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Default save location")
        if chosen:
            self.save_location_edit.setText(chosen)

    def _on_save(self) -> None:
        s = self._settings
        s.set("dark_mode", self.dark_mode_box.isChecked(), persist=False)
        s.set("auto_verify_integrity", self.verify_box.isChecked(), persist=False)
        s.set("auto_clear_temp_files", self.clear_temp_box.isChecked(),
              persist=False)
        s.set("overwrite_existing_files", self.overwrite_box.isChecked(),
              persist=False)
        s.set("default_save_location",
              self.save_location_edit.text().strip(), persist=False)
        s.set("language", str(self.language_combo.currentData()), persist=False)
        s.set("recent_history_size", int(self.recent_spin.value()), persist=False)
        s.save()
        self.settings_changed.emit()
        self.accept()

    def _on_restore_defaults(self) -> None:
        self._settings.reset_to_defaults()
        self._load_from_settings()
        self.settings_changed.emit()
