"""File queue list widget."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logic.ffprobe_reader import MediaInfo


# ---------------------------------------------------------------------------
# Column indices  (single source of truth — change here, nowhere else)
# ---------------------------------------------------------------------------
_COL_NAME       = 0
_COL_DURATION   = 1
_COL_RESOLUTION = 2
_COL_CODEC      = 3
_COL_STATUS     = 4

_HEADERS = ["File", "Duration", "Resolution", "Codec", "Status"]

# Placeholder shown while probe is still running
_PENDING = "\u2026"  # ellipsis


# ---------------------------------------------------------------------------
# Status model
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    """Lifecycle states displayed in the Status column."""

    QUEUED  = "queued"
    RUNNING = "running"
    DONE    = "done"
    FAILED  = "failed"


_STATUS_COLOR: dict[JobStatus, str] = {
    JobStatus.QUEUED:  "#aaaaaa",
    JobStatus.RUNNING: "#4499dd",
    JobStatus.DONE:    "#44bb44",
    JobStatus.FAILED:  "#ee4444",
}

_STATUS_LABEL: dict[JobStatus, str] = {
    JobStatus.QUEUED:  "queued",
    JobStatus.RUNNING: "running\u2026",
    JobStatus.DONE:    "done",
    JobStatus.FAILED:  "failed",
}


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class FileListWidget(QWidget):
    """Shows queued input files as a table with media-info columns.

    Columns
    -------
    File        — filename (stretches to fill available width)
    Duration    — HH:MM:SS or M:SS, populated after ffprobe finishes
    Resolution  — e.g. 1920×1080
    Codec       — e.g. h264
    Status      — queued / running… / done / failed

    Media info columns are filled in asynchronously via
    ``set_item_media_info`` once ``ProbeWorker`` emits results.  While
    probing is in progress each cell shows an ellipsis (…).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Queue"))
        header_row.addStretch()

        self._clear_btn = QPushButton("Clear all")
        self._clear_btn.setFixedWidth(70)
        self._clear_btn.clicked.connect(self.clear_files)
        header_row.addWidget(self._clear_btn)
        layout.addLayout(header_row)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(_HEADERS))
        self._tree.setHeaderLabels(_HEADERS)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(False)  # flat list, no expand arrows

        hdr = self._tree.header()
        hdr.setSectionResizeMode(_COL_NAME,       QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_DURATION,   QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_RESOLUTION, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_CODEC,      QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_STATUS,     QHeaderView.ResizeMode.Fixed)

        self._tree.setColumnWidth(_COL_DURATION,   70)
        self._tree.setColumnWidth(_COL_RESOLUTION, 100)
        self._tree.setColumnWidth(_COL_CODEC,       70)
        self._tree.setColumnWidth(_COL_STATUS,      80)

        layout.addWidget(self._tree)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_files(self, paths: list[Path]) -> None:
        """Append *paths* to the queue, skipping exact duplicates."""
        existing: set[str] = {
            self._tree.topLevelItem(i).data(_COL_NAME, Qt.ItemDataRole.UserRole)
            for i in range(self._tree.topLevelItemCount())
        }
        for path in paths:
            key = str(path)
            if key in existing:
                continue

            item = QTreeWidgetItem([
                path.name,   # _COL_NAME
                _PENDING,    # _COL_DURATION   — filled by ProbeWorker
                _PENDING,    # _COL_RESOLUTION — filled by ProbeWorker
                _PENDING,    # _COL_CODEC      — filled by ProbeWorker
                _STATUS_LABEL[JobStatus.QUEUED],
            ])
            item.setData(_COL_NAME, Qt.ItemDataRole.UserRole, key)
            # Status column inherits the queued colour; other columns default
            item.setForeground(_COL_STATUS, QColor(_STATUS_COLOR[JobStatus.QUEUED]))
            # TODO: replace text-based status with a custom QStyledItemDelegate
            #       that draws a pill-shaped badge aligned to the right edge
            self._tree.addTopLevelItem(item)
            existing.add(key)

    def clear_files(self) -> None:
        self._tree.clear()

    def file_count(self) -> int:
        """Return the number of files currently in the queue."""
        return self._tree.topLevelItemCount()

    def get_all_paths(self) -> list[Path]:
        """Return all queued file paths in display order."""
        return [
            Path(self._tree.topLevelItem(i).data(_COL_NAME, Qt.ItemDataRole.UserRole))
            for i in range(self._tree.topLevelItemCount())
        ]

    def set_item_status(self, path: Path, status: JobStatus) -> None:
        """Update the Status column for *path*."""
        item = self._find_item(path)
        if item is None:
            return
        item.setText(_COL_STATUS, _STATUS_LABEL[status])
        item.setForeground(_COL_STATUS, QColor(_STATUS_COLOR[status]))

    def set_item_media_info(self, path: Path, info: MediaInfo) -> None:
        """Fill in the Duration, Resolution, and Codec columns for *path*.

        Called from the UI thread when ``ProbeWorker.file_probed`` fires.
        Cells that could not be determined are shown as "—" (em dash).
        """
        item = self._find_item(path)
        if item is None:
            return
        item.setText(_COL_DURATION,   info.duration_str)
        item.setText(_COL_RESOLUTION, info.resolution_str)
        item.setText(_COL_CODEC,      info.codec_str)

    def reset_all_statuses(self) -> None:
        """Reset every Status cell back to QUEUED (called before a new run)."""
        label = _STATUS_LABEL[JobStatus.QUEUED]
        color = QColor(_STATUS_COLOR[JobStatus.QUEUED])
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            item.setText(_COL_STATUS, label)
            item.setForeground(_COL_STATUS, color)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_item(self, path: Path) -> QTreeWidgetItem | None:
        """Return the tree item whose UserRole matches *path*, or ``None``."""
        key = str(path)
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.data(_COL_NAME, Qt.ItemDataRole.UserRole) == key:
                return item
        return None
