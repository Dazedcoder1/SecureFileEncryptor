"""
encrypt_dialog.py — Password + options dialog for encryption.

Collects and validates everything a worker needs, then hands back an
immutable CryptoJobOptions. The password leaves this dialog only inside
a SecurePassword (never as a loose string attribute).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.settings import SettingsManager
from crypto.password_manager import SecurePassword
from ui.widgets import PasswordField
from utils.validator import password_issues


@dataclass(frozen=True)
class CryptoJobOptions:
    """Everything the main window needs to launch a worker."""

    password: SecurePassword
    output_dir: Path | None       # None => next to each source file
    overwrite: bool


class EncryptDialog(QDialog):
    """Modal dialog shown before encryption starts."""

    def __init__(
        self,
        item_count: int,
        settings: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Encrypt")
        self.setMinimumWidth(420)
        self._settings = settings
        self._options: CryptoJobOptions | None = None

        summary = QLabel(
            f"Encrypting <b>{item_count}</b> selected item(s) with AES-256-GCM."
        )
        summary.setWordWrap(True)

        self.password_field = PasswordField("Password", with_meter=True)
        self.confirm_field = PasswordField("Confirm password")

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e05252;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        # Output location -------------------------------------------------
        self.output_edit = QLineEdit(str(settings.get("default_save_location")))
        self.output_edit.setPlaceholderText("Same folder as each source file")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_output)
        out_row = QHBoxLayout()
        out_row.addWidget(self.output_edit, stretch=1)
        out_row.addWidget(browse)

        self.overwrite_box = QCheckBox("Overwrite existing files")
        self.overwrite_box.setChecked(bool(settings.get("overwrite_existing_files")))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Encrypt")
        buttons.button(QDialogButtonBox.Ok).setProperty("class", "accent")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(summary)
        layout.addWidget(self.password_field)
        layout.addWidget(self.confirm_field)
        layout.addWidget(self.error_label)
        layout.addWidget(QLabel("Output folder (optional):"))
        layout.addLayout(out_row)
        layout.addWidget(self.overwrite_box)
        layout.addWidget(buttons)
        self.password_field.set_focus()

    # ------------------------------------------------------------- public
    @property
    def options(self) -> CryptoJobOptions | None:
        """Populated only after the dialog was accepted with valid input."""
        return self._options

    # ------------------------------------------------------------ private
    def _browse_output(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if chosen:
            self.output_edit.setText(chosen)

    def _on_accept(self) -> None:
        password = self.password_field.password()
        issues = password_issues(password, self.confirm_field.password())
        output_text = self.output_edit.text().strip()
        output_dir: Path | None = Path(output_text) if output_text else None
        if output_dir is not None and not output_dir.is_dir():
            issues.append("Output folder does not exist.")
        if issues:
            self.error_label.setText(" ".join(issues))
            self.error_label.show()
            return

        self._options = CryptoJobOptions(
            password=SecurePassword(password, self.confirm_field.password()),
            output_dir=output_dir,
            overwrite=self.overwrite_box.isChecked(),
        )
        self.accept()
