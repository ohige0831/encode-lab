"""Background media-probing worker.

``ProbeWorker`` runs ffprobe against a list of files on a dedicated thread,
emitting ``file_probed`` for each result as it arrives so the UI can update
incrementally rather than waiting for the whole batch.

The worker is fire-and-forget: create it, connect its signals, call
``start()``.  It emits ``all_probed`` when finished and cleans itself up.
No UI code lives here.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from logic.ffprobe_reader import MediaInfo, probe


class ProbeWorker(QThread):
    """Probes a list of files sequentially on a background thread.

    Signals
    -------
    file_probed(path, info)
        Emitted after each file is probed.  *info* is always a valid
        ``MediaInfo`` object — fields are ``None`` when data is unavailable.
    all_probed()
        Emitted once after every path in the queue has been attempted.
    """

    file_probed: Signal = Signal(object, object)  # Path, MediaInfo
    all_probed:  Signal = Signal()

    def __init__(self, paths: list[Path]) -> None:
        super().__init__()
        self._paths: list[Path] = list(paths)  # defensive copy

    def run(self) -> None:  # type: ignore[override]
        """Probe all files and emit results.  Called by Qt on the worker thread."""
        for path in self._paths:
            info = probe(path)
            self.file_probed.emit(path, info)
        self.all_probed.emit()
