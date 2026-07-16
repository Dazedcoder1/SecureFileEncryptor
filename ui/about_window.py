"""
about_window.py — Application, environment, and license information.
"""

from __future__ import annotations

import platform

import cryptography
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

from config.constants import (
    APP_AUTHOR,
    APP_LICENSE,
    APP_NAME,
    APP_VERSION,
    GITHUB_URL,
)


class AboutWindow(QDialog):
    """Modal 'About' dialog."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setMinimumWidth(380)

        logo = QLabel("\U0001f6e1")
        logo.setObjectName("DropZoneIcon")
        logo.setAlignment(Qt.AlignCenter)

        self.info_label = QLabel(
            f"<h2 style='margin-bottom:2px'>{APP_NAME}</h2>"
            f"<p>Version {APP_VERSION}</p>"
            f"<p>Author: {APP_AUTHOR}<br>"
            f"License: {APP_LICENSE}</p>"
            f"<p>Python {platform.python_version()}<br>"
            f"cryptography {cryptography.__version__}<br>"
            f"PyQt {PYQT_VERSION_STR} (Qt {QT_VERSION_STR})</p>"
            f"<p><a href='{GITHUB_URL}'>{GITHUB_URL}</a></p>"
            "<p style='color:gray'>AES-256-GCM · PBKDF2-HMAC-SHA256 · "
            "SHA-256 integrity verification</p>"
        )
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setOpenExternalLinks(True)
        self.info_label.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(logo)
        layout.addWidget(self.info_label)
        layout.addWidget(buttons)
