"""EncodeLab — entry point."""

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def _prepend_bundled_ffmpeg() -> None:
    """When frozen as a .exe, prepend the bundled ffmpeg/ dir to PATH.

    Expected layout: dist/EncodeLab/ffmpeg/ffmpeg.exe
                                           ffprobe.exe
    Falls back to system PATH if the folder is absent.
    """
    if not getattr(sys, "frozen", False):
        return
    ffmpeg_dir = Path(sys.executable).parent / "ffmpeg"
    if ffmpeg_dir.is_dir():
        os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")


def main() -> None:
    _prepend_bundled_ffmpeg()
    app = QApplication(sys.argv)
    app.setApplicationName("EncodeLab")
    app.setApplicationVersion("0.1.0")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
