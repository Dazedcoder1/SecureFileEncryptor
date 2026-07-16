"""
history_window.py — Searchable, sortable encryption history viewer.

Filters re-query SQLite (search + operation + status); column sorting is
client-side via a numeric-aware QTableWidgetItem so '9 KB' sorts before
'1 MB'. Export writes exactly what the current filters show.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database.database import DatabaseError, HistoryDatabase
from models.records import OperationStatus, OperationType
from utils.file_utils import human_readable_size
from utils.helpers import format_duration
from utils.logger import get_logger

logger = get_logger(__name__)

_COLUMNS = ("Date/Time", "Operation", "Filename", "Location",
            "Size", "Duration", "Status", "SHA-256")


class _NumericItem(QTableWidgetItem):
    """Table item that sorts by a raw numeric value, not display text."""

    def __init__(self, text: str, raw: float) -> None:
        super().__init__(text)
        self._raw = raw

    def __lt__(self, other: "QTableWidgetItem") -> bool:  # type: ignore[override]
        if isinstance(other, _NumericItem):
            return self._raw < other._raw
        return super().__lt__(other)


class HistoryWindow(QDialog):
    """Modal window listing all recorded operations."""

    def __init__(
        self, database: HistoryDatabase, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Encryption History")
        self.resize(860, 480)
        self._db = database

        # ------------------------------------------------------- filters
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search filename or location…")
        self.search_edit.textChanged.connect(self.refresh)

        self.operation_combo = QComboBox()
        self.operation_combo.addItems(["All operations", "Encrypt", "Decrypt"])
        self.operation_combo.currentIndexChanged.connect(self.refresh)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["All statuses", "Success", "Failed", "Cancelled"])
        self.status_combo.currentIndexChanged.connect(self.refresh)

        filters = QHBoxLayout()
        filters.addWidget(self.search_edit, stretch=1)
        filters.addWidget(self.operation_combo)
        filters.addWidget(self.status_combo)

        # --------------------------------------------------------- table
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)

        # ------------------------------------------------------- buttons
        export_button = QPushButton("Export CSV…")
        export_button.clicked.connect(self._export_csv)
        delete_button = QPushButton("Delete Selected")
        delete_button.clicked.connect(self._delete_selected)
        clear_button = QPushButton("Clear All")
        clear_button.setProperty("class", "danger")
        clear_button.clicked.connect(self._clear_all)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        self.count_label = QLabel("")
        buttons = QHBoxLayout()
        buttons.addWidget(self.count_label, stretch=1)
        buttons.addWidget(export_button)
        buttons.addWidget(delete_button)
        buttons.addWidget(clear_button)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(buttons)

        self.refresh()

    # ------------------------------------------------------------- public
    def refresh(self) -> None:
        """Re-query the database with the current filters and repopulate."""
        try:
            records = self._db.get_records(**self._current_filters())
        except DatabaseError as exc:
            QMessageBox.critical(self, "History", str(exc))
            return

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(records))
        for row, r in enumerate(records):
            date_item = QTableWidgetItem(r.timestamp)
            date_item.setData(Qt.UserRole, r.record_id)
            self.table.setItem(row, 0, date_item)
            self.table.setItem(row, 1, QTableWidgetItem(r.operation.value))
            self.table.setItem(row, 2, QTableWidgetItem(r.filename))
            self.table.setItem(row, 3, QTableWidgetItem(r.location))
            self.table.setItem(
                row, 4,
                _NumericItem(human_readable_size(r.size_bytes), r.size_bytes),
            )
            self.table.setItem(
                row, 5,
                _NumericItem(format_duration(r.duration_seconds),
                             r.duration_seconds),
            )
            status_item = QTableWidgetItem(r.status.value)
            self.table.setItem(row, 6, status_item)
            hash_item = QTableWidgetItem(
                r.sha256_hex[:16] + "…" if r.sha256_hex else ""
            )
            hash_item.setToolTip(r.sha256_hex)
            self.table.setItem(row, 7, hash_item)
            if r.error_message:
                status_item.setToolTip(r.error_message)
        self.table.setSortingEnabled(True)
        self.count_label.setText(f"{len(records)} record(s)")

    # ------------------------------------------------------------ private
    def _current_filters(self) -> dict:
        operation = {1: OperationType.ENCRYPT, 2: OperationType.DECRYPT}.get(
            self.operation_combo.currentIndex()
        )
        status = {
            1: OperationStatus.SUCCESS,
            2: OperationStatus.FAILED,
            3: OperationStatus.CANCELLED,
        }.get(self.status_combo.currentIndex())
        return {
            "search": self.search_edit.text().strip() or None,
            "operation": operation,
            "status": status,
        }

    def _selected_record_ids(self) -> list[int]:
        ids: list[int] = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item is not None:
                ids.append(int(item.data(Qt.UserRole)))
        return ids

    def _delete_selected(self) -> None:
        ids = self._selected_record_ids()
        if not ids:
            return
        try:
            for record_id in ids:
                self._db.delete_record(record_id)
        except DatabaseError as exc:
            QMessageBox.critical(self, "History", str(exc))
        self.refresh()

    def _clear_all(self) -> None:
        answer = QMessageBox.question(
            self, "Clear history",
            "Delete ALL history records? This cannot be undone.",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self._db.clear_history()
        except DatabaseError as exc:
            QMessageBox.critical(self, "History", str(exc))
        self.refresh()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export history", "history.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            from pathlib import Path

            count = self._db.export_csv(Path(path), **self._current_filters())
        except DatabaseError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(
            self, "Export complete", f"Exported {count} record(s)."
        )
