"""
widgets.py — Reusable custom widgets.

DropZone            drag & drop for files/folders with visual feedback
StrengthMeter       live password strength bar (validator-driven)
PasswordField       password input with show/hide + optional meter
ProgressPanel       current file / overall % / speed / elapsed / remaining
NotificationBanner  inline auto-hiding info/success/error messages

All widgets are style-agnostic: colors come from the QSS themes via
object names and dynamic properties, so dark/light switching is free.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from models.records import ProgressUpdate
from ui.theme import repolish
from utils.helpers import format_duration, format_speed, truncate_middle
from utils.validator import PasswordStrength, password_strength

_STRENGTH_LABELS = {
    PasswordStrength.VERY_WEAK: "Very weak",
    PasswordStrength.WEAK: "Weak",
    PasswordStrength.FAIR: "Fair",
    PasswordStrength.GOOD: "Good",
    PasswordStrength.STRONG: "Strong",
}
_STRENGTH_COLORS = {
    PasswordStrength.VERY_WEAK: "#e05252",
    PasswordStrength.WEAK: "#e08952",
    PasswordStrength.FAIR: "#e0c352",
    PasswordStrength.GOOD: "#7fbf5a",
    PasswordStrength.STRONG: "#4caf50",
}


# ==========================================================================
class DropZone(QFrame):
    """Drag & drop target accepting single/multiple files and folders.

    Signals:
        paths_dropped(list): existing Path objects the user dropped.
        rejected(str): reason why a drop was refused (non-local items).
        clicked(): user clicked the zone (parent opens a browse dialog).
    """

    paths_dropped = pyqtSignal(list)
    rejected = pyqtSignal(str)
    clicked = pyqtSignal()

    def __init__(
        self,
        title: str = "Drag & drop files or folders here",
        subtitle: str = "or click to browse",
        icon: str = "\U0001f512",  # 🔒
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        # Tall enough for icon + title + subtitle at any DPI scale —
        # a smaller zone clips its own labels on high-DPI displays.
        self.setMinimumHeight(170)
        self.setProperty("dragActive", False)

        icon_label = QLabel(icon)
        icon_label.setObjectName("DropZoneIcon")
        icon_label.setAlignment(Qt.AlignCenter)
        title_label = QLabel(title)
        title_label.setObjectName("DropZoneTitle")
        title_label.setAlignment(Qt.AlignCenter)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("DropZoneSubtitle")
        subtitle_label.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(4)
        # Stretches keep the labels vertically centered as ONE group
        # instead of Qt spreading them across the full zone height.
        layout.addStretch(1)
        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addStretch(1)

    # ---------------------------------------------------------- drag events
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_drag_active(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._set_drag_active(False)
        urls = event.mimeData().urls()
        paths: list[Path] = []
        foreign = 0
        for url in urls:
            if not url.isLocalFile():
                foreign += 1
                continue
            path = Path(url.toLocalFile())
            if path.exists():
                paths.append(path)
            else:
                foreign += 1
        if paths:
            event.acceptProposedAction()
            self.paths_dropped.emit(paths)
        if foreign:
            self.rejected.emit(
                f"{foreign} dropped item(s) were not usable files or folders."
            )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _set_drag_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        repolish(self)


# ==========================================================================
class StrengthMeter(QWidget):
    """Password strength bar + label, driven by utils.validator."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._label = QLabel("")
        self._label.setObjectName("StrengthLabel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._bar, stretch=1)
        layout.addWidget(self._label)
        self.update_password("")

    def update_password(self, password: str) -> None:
        bucket, score = password_strength(password)
        self._bar.setValue(score)
        self._label.setText(_STRENGTH_LABELS[bucket] if password else "")
        color = _STRENGTH_COLORS[bucket]
        self._bar.setStyleSheet(
            "QProgressBar { background-color: rgba(127,127,127,60);"
            " border-radius: 3px; }"
            f"QProgressBar::chunk {{ background-color: {color};"
            " border-radius: 3px; }}"
        )

    @property
    def score(self) -> int:
        return self._bar.value()

    @property
    def label_text(self) -> str:
        return self._label.text()


# ==========================================================================
class PasswordField(QWidget):
    """Password entry with show/hide toggle and optional strength meter."""

    text_changed = pyqtSignal(str)

    def __init__(
        self,
        placeholder: str = "Enter password",
        with_meter: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._edit = QLineEdit()
        self._edit.setEchoMode(QLineEdit.Password)
        self._edit.setPlaceholderText(placeholder)
        self._edit.textChanged.connect(self._on_text_changed)

        self._toggle = QToolButton()
        self._toggle.setText("\U0001f441")  # 👁
        self._toggle.setCheckable(True)
        self._toggle.setToolTip("Show/hide password")
        self._toggle.setCursor(Qt.PointingHandCursor)
        self._toggle.toggled.connect(self._on_toggle)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._edit, stretch=1)
        row.addWidget(self._toggle)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)

        self._meter: StrengthMeter | None = None
        if with_meter:
            self._meter = StrengthMeter()
            layout.addWidget(self._meter)

    # -------------------------------------------------------------- public
    def password(self) -> str:
        return self._edit.text()

    def clear(self) -> None:
        self._edit.clear()

    def set_focus(self) -> None:
        self._edit.setFocus()

    @property
    def is_revealed(self) -> bool:
        return self._edit.echoMode() == QLineEdit.Normal

    @property
    def meter(self) -> StrengthMeter | None:
        return self._meter

    # ------------------------------------------------------------- private
    def _on_text_changed(self, text: str) -> None:
        if self._meter is not None:
            self._meter.update_password(text)
        self.text_changed.emit(text)

    def _on_toggle(self, checked: bool) -> None:
        self._edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)


# ==========================================================================
class ProgressPanel(QWidget):
    """Live progress display fed by worker ProgressUpdate signals."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._file_label = QLabel("")
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._stats_label = QLabel("")
        self._stats_label.setObjectName("ProgressStats")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._file_label)
        layout.addWidget(self._bar)
        layout.addWidget(self._stats_label)
        self.reset()

    def update_progress(self, update: ProgressUpdate) -> None:
        """Slot for BaseCryptoWorker.progress_updated."""
        name = truncate_middle(update.current_file, 48)
        self._file_label.setText(
            f"{name}  ({update.file_index}/{update.file_count})"
        )
        self._bar.setValue(update.percent)
        self._stats_label.setText(
            f"{format_speed(update.speed_bps)}   •   "
            f"elapsed {format_duration(update.elapsed_seconds)}   •   "
            f"remaining {format_duration(update.remaining_seconds)}"
        )

    def reset(self) -> None:
        self._file_label.setText("Ready.")
        self._bar.setValue(0)
        self._stats_label.setText("")

    # Exposed for tests and the main window.
    @property
    def percent(self) -> int:
        return self._bar.value()

    @property
    def file_text(self) -> str:
        return self._file_label.text()

    @property
    def stats_text(self) -> str:
        return self._stats_label.text()


# ==========================================================================
class NotificationBanner(QFrame):
    """Inline auto-hiding banner: info / success / error."""

    def __init__(
        self, timeout_ms: int = 5000, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NotificationBanner")
        self._label = QLabel("")
        self._label.setWordWrap(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.addWidget(self._label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(timeout_ms)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, text: str, level: str = "info") -> None:
        """Display a message; level is one of 'info', 'success', 'error'."""
        if level not in ("info", "success", "error"):
            level = "info"
        self.setProperty("level", level)
        repolish(self)
        self._label.setText(text)
        self.show()
        self._timer.start()

    @property
    def message(self) -> str:
        return self._label.text()

    @property
    def level(self) -> str:
        return self.property("level") or ""
