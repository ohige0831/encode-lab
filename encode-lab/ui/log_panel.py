"""Read-only log output panel."""

from __future__ import annotations

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Colour palette (dark-theme safe, readable on both light and dark backgrounds)
# ---------------------------------------------------------------------------
_COLOR_COMMAND = "#888888"
_COLOR_SUCCESS = "#44bb44"
_COLOR_ERROR   = "#ee4444"
_COLOR_INFO    = "#4499dd"
_COLOR_WARN    = "#ddaa33"

# ---------------------------------------------------------------------------
# Label tokens prepended to every log line for quick visual scanning
# ---------------------------------------------------------------------------
_LABEL_INFO    = "[INFO] "
_LABEL_OK      = "[OK]   "
_LABEL_ERROR   = "[ERROR]"
_LABEL_CMD     = "[CMD]  "
_LABEL_WARN    = "[WARN] "


class LogPanel(QWidget):
    """A scrolling, read-only log area for ffmpeg command previews and results.

    Every ``append_*`` method prepends a bold, fixed-width label token so the
    log is scannable at a glance::

        [INFO]  Starting 3 job(s) — preset: H.264 — Fast (web)
        [CMD]   $ ffmpeg -y -i in.mp4 -vcodec libx264 ...
        [INFO]  → clip.mp4
        [OK]    ✓ clip_converted.mp4
        [ERROR] ✗ broken.mp4
        [ERROR] No such file or directory

    All ``append_*`` methods must be called from the UI thread only.
    Cross-thread logging must go through a Qt signal connected to one of them.
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
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.addWidget(QLabel("Log"))
        header.addStretch()

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedWidth(50)
        self._clear_btn.clicked.connect(self.clear)
        header.addWidget(self._clear_btn)
        layout.addLayout(header)

        self._edit = QTextEdit()
        self._edit.setReadOnly(True)
        self._edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._edit.setMinimumHeight(100)
        self._edit.setStyleSheet(
            "QTextEdit {"
            "  font-family: 'Consolas', 'Courier New', monospace;"
            "  font-size: 12px;"
            "  background: #111;"
            "  color: #ddd;"
            "  border: 1px solid #333;"
            "  border-radius: 4px;"
            "}"
        )
        layout.addWidget(self._edit)

    # ------------------------------------------------------------------
    # Public append API
    # ------------------------------------------------------------------

    def append_command(self, cmd: list[str]) -> None:
        """Log a planned ffmpeg command prefixed with ``[CMD]``."""
        text = " ".join(cmd)
        self._append_line(_LABEL_CMD, f"$ {text}", _COLOR_COMMAND)

    def append_info(self, message: str) -> None:
        """Log a neutral informational line prefixed with ``[INFO]``."""
        self._append_line(_LABEL_INFO, message, _COLOR_INFO)

    def append_success(self, message: str) -> None:
        """Log a success line prefixed with ``[OK]``."""
        self._append_line(_LABEL_OK, message, _COLOR_SUCCESS)

    def append_error(self, message: str) -> None:
        """Log one or more error lines, each prefixed with ``[ERROR]``.

        Multi-line stderr excerpts are split so every line gets its own label,
        keeping the log scannable without needing horizontal scrolling.
        """
        for line in message.splitlines():
            self._append_line(_LABEL_ERROR, line, _COLOR_ERROR)

    def append_warning(self, message: str) -> None:
        """Log a warning line prefixed with ``[WARN]``."""
        self._append_line(_LABEL_WARN, message, _COLOR_WARN)

    def append_plain(self, message: str) -> None:
        """Log an unstyled line with no label (for raw output or spacers)."""
        self._append_html(_escape(message))

    def clear(self) -> None:
        """Erase all log content."""
        self._edit.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _append_line(self, label: str, message: str, color: str) -> None:
        """Render one labelled log line.

        The label is bold; the message text is normal weight.  Both share the
        same colour so the line reads as a single unit.
        """
        esc_msg = _escape(message)
        esc_lbl = _escape(label)
        html = (
            f"<span style='color:{color}'>"
            f"<b>{esc_lbl}</b> {esc_msg}"
            f"</span>"
        )
        self._append_html(html)

    def _append_html(self, html: str) -> None:
        """Append one HTML fragment and auto-scroll to the bottom."""
        cursor = self._edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html + "<br>")
        self._edit.setTextCursor(cursor)
        self._edit.ensureCursorVisible()


def _escape(text: str) -> str:
    """Minimal HTML escaping so angle brackets and ampersands render safely."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
