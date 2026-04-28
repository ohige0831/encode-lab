"""Drag-and-drop file intake widget."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from logic.presets import SUPPORTED_EXTENSIONS


class DropZone(QWidget):
    """A bordered area that accepts dragged video/audio files.

    Emits :attr:`files_dropped` with a list of resolved ``Path`` objects
    whenever the user drops files onto the widget.
    """

    files_dropped: Signal = Signal(list)  # list[Path]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setMinimumHeight(120)
        self.setObjectName("DropZone")
        self.setStyleSheet(
            "#DropZone {"
            "  border: 2px dashed #666;"
            "  border-radius: 8px;"
            "  background: #1e1e1e;"
            "}"
            "#DropZone[dragActive=true] {"
            "  border-color: #0af;"
            "  background: #162030;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._label = QLabel("Drop files here\nor click to browse")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("color: #888; font-size: 14px;")
        layout.addWidget(self._label)

    # ------------------------------------------------------------------
    # Drag-and-drop event handlers
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragActive", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)

        paths: list[Path] = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local:
                paths.append(Path(local))

        accepted = _filter_supported(paths)
        rejected_count = len(paths) - len(accepted)
        if rejected_count:
            # TODO: surface rejected filenames in a tooltip or status bar message
            pass
        if accepted:
            self.files_dropped.emit(accepted)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        # TODO: open QFileDialog for users who prefer clicking over dragging
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Module-level helpers (pure functions, no Qt dependency — easy to unit-test)
# ---------------------------------------------------------------------------

def _filter_supported(paths: list[Path]) -> list[Path]:
    """Return only the paths whose extension is in SUPPORTED_EXTENSIONS.

    Comparison is case-insensitive so ``.MP4`` and ``.mp4`` both pass.
    """
    return [p for p in paths if p.suffix.lower() in SUPPORTED_EXTENSIONS]
