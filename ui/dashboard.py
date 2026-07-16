"""
dashboard.py — Home screen: branding, actions, drop zone, progress, recent.

Pure view: the dashboard renders state and emits signals; ALL decisions
(routing drops, starting workers, querying the DB) belong to MainWindow.
That separation keeps this file trivially testable and the main window
the single controller.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.constants import APP_NAME
from models.records import HistoryRecord, OperationStatus
from ui.widgets import DropZone, NotificationBanner, ProgressPanel
from utils.file_utils import human_readable_size

_STATUS_ICONS = {
    OperationStatus.SUCCESS: "✅",    # ✅
    OperationStatus.FAILED: "❌",     # ❌
    OperationStatus.CANCELLED: "⚠",  # ⚠
}


class Dashboard(QWidget):
    """Central widget of the main window.

    Signals:
        encrypt_clicked / decrypt_clicked: action buttons pressed.
        paths_dropped(list): user dropped files/folders on the zone.
        browse_requested: drop zone clicked.
        cancel_clicked: cancel pressed during a running operation.
    """

    encrypt_clicked = pyqtSignal()
    decrypt_clicked = pyqtSignal()
    paths_dropped = pyqtSignal(list)
    browse_requested = pyqtSignal()
    cancel_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ------------------------------------------------------- branding
        logo = QLabel("\U0001f6e1")  # 🛡
        logo.setObjectName("DropZoneIcon")
        logo.setAlignment(Qt.AlignCenter)
        title = QLabel(APP_NAME)
        title.setProperty("class", "heading")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("AES-256 encryption for your files and folders")
        subtitle.setProperty("class", "subheading")
        subtitle.setAlignment(Qt.AlignCenter)

        # -------------------------------------------------------- actions
        self.encrypt_button = QPushButton("\U0001f512  Encrypt Files…")
        self.encrypt_button.setProperty("class", "accent")
        self.encrypt_button.clicked.connect(self.encrypt_clicked)
        self.decrypt_button = QPushButton("\U0001f513  Decrypt Files…")
        self.decrypt_button.clicked.connect(self.decrypt_clicked)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.encrypt_button)
        actions.addWidget(self.decrypt_button)
        actions.addStretch(1)

        # ------------------------------------------------ drop + feedback
        self.drop_zone = DropZone()
        self.drop_zone.paths_dropped.connect(self.paths_dropped)
        self.drop_zone.clicked.connect(self.browse_requested)

        self.banner = NotificationBanner()
        self.drop_zone.rejected.connect(
            lambda reason: self.banner.show_message(reason, "error")
        )

        # The progress area only exists while an operation runs — an idle
        # "Ready. / 0%" strip is visual noise and steals vertical space
        # from the drop zone on smaller/high-DPI screens.
        self.progress = ProgressPanel()
        self.progress.hide()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("class", "danger")
        self.cancel_button.clicked.connect(self.cancel_clicked)
        self.cancel_button.hide()
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress, stretch=1)
        progress_row.addWidget(self.cancel_button, alignment=Qt.AlignBottom)

        # --------------------------------------------------------- recent
        recent_heading = QLabel("Recent activity")
        recent_heading.setProperty("class", "subheading")
        self.recent_list = QListWidget()
        self.recent_list.setSelectionMode(QListWidget.NoSelection)
        self.recent_list.setFocusPolicy(Qt.NoFocus)
        self.recent_list.setMaximumHeight(150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)
        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(6)
        layout.addLayout(actions)
        layout.addWidget(self.drop_zone, stretch=1)
        layout.addWidget(self.banner)
        layout.addLayout(progress_row)
        layout.addWidget(recent_heading)
        layout.addWidget(self.recent_list)

    # ------------------------------------------------------------- public
    def set_busy(self, busy: bool) -> None:
        """Toggle between idle and operation-running states."""
        self.encrypt_button.setEnabled(not busy)
        self.decrypt_button.setEnabled(not busy)
        self.drop_zone.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.cancel_button.setVisible(busy)
        if not busy:
            self.progress.reset()

    def set_recent(self, records: list[HistoryRecord]) -> None:
        """Refresh the recent-activity panel from history rows."""
        self.recent_list.clear()
        for record in records:
            icon = _STATUS_ICONS.get(record.status, "")
            text = (
                f"{icon}  {record.filename}  —  "
                f"{record.operation.value} · "
                f"{human_readable_size(record.size_bytes)}"
            )
            item = QListWidgetItem(text)
            item.setToolTip(f"{record.timestamp}\n{record.location}")
            self.recent_list.addItem(item)
