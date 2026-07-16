"""
decrypt_dialog.py — Password + options dialog for decryption.

Unlike encryption, no strength meter and no policy enforcement: the
file may have been created under different rules, and the KCV inside
the file header is the real arbiter of password correctness.
"""

from __future__ import annotations

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
from ui.encrypt_dialog import CryptoJobOptions
from ui.widgets import PasswordField


class DecryptDialog(QDialog):
    """Modal dialog shown before decryption starts."""

    def __init__(
        self,
        item_count: int,
        settings: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Decrypt")
        self.setMinimumWidth(420)
        self._settings = settings
        self._options: CryptoJobOptions | None = None

        summary = QLabel(
            f"Decrypting <b>{item_count}</b> selected item(s). "
            "Integrity will be verified automatically."
        )
        summary.setWordWrap(True)

        self.password_field = PasswordField("Password")

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e05252;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        self.output_edit = QLineEdit(str(settings.get("default_save_location")))
        self.output_edit.setPlaceholderText("Same folder as each encrypted file")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_output)
        out_row = QHBoxLayout()
        out_row.addWidget(self.output_edit, stretch=1)
        out_row.addWidget(browse)

        self.overwrite_box = QCheckBox("Overwrite existing files")
        self.overwrite_box.setChecked(bool(settings.get("overwrite_existing_files")))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Decrypt")
        buttons.button(QDialogButtonBox.Ok).setProperty("class", "accent")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(summary)
        layout.addWidget(self.password_field)
        layout.addWidget(self.error_label)
        layout.addWidget(QLabel("Output folder (optional):"))
        layout.addLayout(out_row)
        layout.addWidget(self.overwrite_box)
        layout.addWidget(buttons)
        self.password_field.set_focus()

    # ------------------------------------------------------------- public
    @property
    def options(self) -> CryptoJobOptions | None:
        return self._options

    # ------------------------------------------------------------ private
    def _browse_output(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if chosen:
            self.output_edit.setText(chosen)

    def _on_accept(self) -> None:
        password = self.password_field.password()
        issues: list[str] = []
        if not password:
            issues.append("Please enter the password.")
        output_text = self.output_edit.text().strip()
        output_dir: Path | None = Path(output_text) if output_text else None
        if output_dir is not None and not output_dir.is_dir():
            issues.append("Output folder does not exist.")
        if issues:
            self.error_label.setText(" ".join(issues))
            self.error_label.show()
            return

        self._options = CryptoJobOptions(
            password=SecurePassword(password, enforce_policy=False),
            output_dir=output_dir,
            overwrite=self.overwrite_box.isChecked(),
        )
        self.accept()
