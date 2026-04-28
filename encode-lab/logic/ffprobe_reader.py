"""ffprobe-based media information reader.

Public surface
--------------
MediaInfo   — frozen dataclass carrying the fields we care about
probe       — run ffprobe on one file and return a ``MediaInfo``

Design principles
-----------------
- ``probe()`` never raises.  Any subprocess, JSON, or parse error yields a
  ``MediaInfo`` with every field set to ``None``.  The UI treats ``None`` as
  "unavailable" and displays a dash.
- No Qt imports.  This module is pure logic and can be unit-tested by
  patching ``subprocess.run``.
- Fields added to ``MediaInfo`` in the future should default to ``None`` so
  existing callers do not break.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Suppress the black CMD flash on Windows --windowed builds.
_CREATION_FLAGS: int = 0
if sys.platform == "win32":
    _CREATION_FLAGS = subprocess.CREATE_NO_WINDOW


# Seconds before we give up waiting for ffprobe on a single file.
# Corrupt or network-mounted files can hang indefinitely without a cap.
_PROBE_TIMEOUT: int = 10


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MediaInfo:
    """Media metadata extracted from a single file by ffprobe.

    All fields are ``None`` when the corresponding data could not be read —
    either because the file has no video stream, the field is absent from the
    ffprobe output, or the probe itself failed.
    """

    duration_sec:  float | None = None
    width:         int   | None = None
    height:        int   | None = None
    video_codec:   str   | None = None

    # ------------------------------------------------------------------
    # Formatted string properties (safe to call even when fields are None)
    # ------------------------------------------------------------------

    @property
    def duration_str(self) -> str:
        """Human-readable duration, e.g. ``"1:23:45"`` or ``"4:07"``."""
        if self.duration_sec is None:
            return "\u2014"
        total = int(self.duration_sec)
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @property
    def resolution_str(self) -> str:
        """Resolution as ``"1920\xd71080"`` or ``"\u2014"``."""
        if self.width is None or self.height is None:
            return "\u2014"
        return f"{self.width}\xd7{self.height}"

    @property
    def codec_str(self) -> str:
        """Codec name or ``"\u2014"``."""
        return self.video_codec or "\u2014"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def probe(path: Path) -> MediaInfo:
    """Run ffprobe on *path* and return a ``MediaInfo``.

    Returns a ``MediaInfo()`` with all fields ``None`` when:
    - ffprobe is not on PATH
    - ffprobe exits with a non-zero code (corrupt / unsupported file)
    - the output is not valid JSON
    - the probe times out (> ``_PROBE_TIMEOUT`` seconds)
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT,
            creationflags=_CREATION_FLAGS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return MediaInfo()

    if result.returncode != 0:
        return MediaInfo()

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return MediaInfo()

    return _parse(data)


# ---------------------------------------------------------------------------
# Internal parsing helpers
# ---------------------------------------------------------------------------

def _parse(data: dict) -> MediaInfo:
    """Build a ``MediaInfo`` from a parsed ffprobe JSON dict."""
    duration_sec = _parse_duration(data.get("format") or {})
    video        = _first_video_stream(data.get("streams") or [])

    width = height = video_codec = None
    if video:
        width       = _to_int(video.get("width"))
        height      = _to_int(video.get("height"))
        raw_codec   = video.get("codec_name")
        video_codec = str(raw_codec) if raw_codec else None

    return MediaInfo(
        duration_sec=duration_sec,
        width=width,
        height=height,
        video_codec=video_codec,
    )


def _parse_duration(fmt: dict) -> float | None:
    """Extract ``format.duration`` as a positive float, or ``None``."""
    raw = fmt.get("duration")
    if raw is None:
        return None
    try:
        val = float(raw)
        return val if val > 0 else None
    except (ValueError, TypeError):
        return None


def _first_video_stream(streams: list) -> dict | None:
    """Return the first stream whose ``codec_type`` is ``"video"``."""
    for stream in streams:
        if isinstance(stream, dict) and stream.get("codec_type") == "video":
            return stream
    return None


def _to_int(val: object) -> int | None:
    """Convert *val* to ``int``, returning ``None`` on failure."""
    try:
        return int(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
