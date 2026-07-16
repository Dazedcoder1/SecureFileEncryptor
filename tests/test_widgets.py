"""GUI widget tests (run headlessly via the offscreen Qt platform).

Run from the project root:
    python -m pytest tests/test_widgets.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt5", reason="PyQt5 required for widget tests")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PyQt5.QtGui import QDropEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from models.records import ProgressUpdate  # noqa: E402
from ui.theme import load_stylesheet  # noqa: E402
from ui.widgets import (  # noqa: E402
    DropZone,
    NotificationBanner,
    PasswordField,
    ProgressPanel,
    StrengthMeter,
)


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication(sys.argv[:1])
        except Exception as exc:  # pragma: no cover - env without GUI libs
            pytest.skip(f"Cannot create QApplication: {exc}")
    return app


def drop_event_for(paths: list[Path]) -> QDropEvent:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    event = QDropEvent(
        QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
    )
    # QDropEvent does NOT take ownership of the mime data; keep a Python
    # reference alive on the event or Qt reads freed memory (segfault).
    event._mime_keepalive = mime  # type: ignore[attr-defined]
    return event


class TestTheme:
    def test_both_stylesheets_load(self, qapp) -> None:
        dark, light = load_stylesheet(dark=True), load_stylesheet(dark=False)
        for sheet in (dark, light):
            assert "QPushButton" in sheet
            assert "DropZone" in sheet
        assert dark != light


class TestDropZone:
    def test_valid_drop_emits_paths(self, qapp, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("x")
        folder = tmp_path / "sub"
        folder.mkdir()

        zone = DropZone()
        received: list[list[Path]] = []
        zone.paths_dropped.connect(received.append)
        zone.dropEvent(drop_event_for([f, folder]))

        assert received == [[f, folder]]
        assert zone.property("dragActive") is False

    def test_missing_path_rejected(self, qapp, tmp_path: Path) -> None:
        zone = DropZone()
        drops: list[list[Path]] = []
        reasons: list[str] = []
        zone.paths_dropped.connect(drops.append)
        zone.rejected.connect(reasons.append)
        zone.dropEvent(drop_event_for([tmp_path / "ghost.txt"]))

        assert drops == []
        assert len(reasons) == 1

    def test_click_emits_signal(self, qapp) -> None:
        zone = DropZone()
        clicks: list[bool] = []
        zone.clicked.connect(lambda: clicks.append(True))

        from PyQt5.QtCore import QEvent, QPointF
        from PyQt5.QtGui import QMouseEvent

        event = QMouseEvent(
            QEvent.MouseButtonPress, QPointF(5, 5), Qt.LeftButton,
            Qt.LeftButton, Qt.NoModifier,
        )
        zone.mousePressEvent(event)
        assert clicks == [True]


class TestStrengthMeter:
    def test_empty_password(self, qapp) -> None:
        meter = StrengthMeter()
        meter.update_password("")
        assert meter.score == 0
        assert meter.label_text == ""

    def test_strong_password(self, qapp) -> None:
        meter = StrengthMeter()
        meter.update_password("Correct-Horse7-Battery!")
        assert meter.score >= 85
        assert meter.label_text == "Strong"

    def test_weak_password(self, qapp) -> None:
        meter = StrengthMeter()
        meter.update_password("abc")
        assert meter.label_text in ("Very weak", "Weak")


class TestPasswordField:
    def test_password_hidden_by_default_and_toggle(self, qapp) -> None:
        field = PasswordField()
        assert field.is_revealed is False
        field._toggle.setChecked(True)
        assert field.is_revealed is True
        field._toggle.setChecked(False)
        assert field.is_revealed is False

    def test_text_and_meter_update(self, qapp) -> None:
        field = PasswordField(with_meter=True)
        changes: list[str] = []
        field.text_changed.connect(changes.append)
        field._edit.setText("Correct-Horse7-Battery!")
        assert field.password() == "Correct-Horse7-Battery!"
        assert changes == ["Correct-Horse7-Battery!"]
        assert field.meter is not None and field.meter.score >= 85
        field.clear()
        assert field.password() == ""


class TestProgressPanel:
    def test_update_and_reset(self, qapp) -> None:
        panel = ProgressPanel()
        assert panel.percent == 0 and panel.file_text == "Ready."

        panel.update_progress(
            ProgressUpdate(
                current_file="video.mp4",
                file_index=2,
                file_count=5,
                done_bytes=50 * 1024**2,
                total_bytes=100 * 1024**2,
                percent=50,
                speed_bps=10 * 1024**2,
                elapsed_seconds=5.0,
                remaining_seconds=5.0,
            )
        )
        assert panel.percent == 50
        assert "video.mp4" in panel.file_text and "(2/5)" in panel.file_text
        assert "10.0 MB/s" in panel.stats_text
        assert "remaining 5s" in panel.stats_text

        panel.reset()
        assert panel.percent == 0


class TestNotificationBanner:
    def test_show_message_levels(self, qapp) -> None:
        banner = NotificationBanner(timeout_ms=60_000)
        assert banner.isHidden()
        banner.show_message("Saved!", "success")
        assert not banner.isHidden()
        assert banner.message == "Saved!"
        assert banner.level == "success"
        banner.show_message("Oops", "bogus-level")
        assert banner.level == "info"  # unknown levels fall back to info
