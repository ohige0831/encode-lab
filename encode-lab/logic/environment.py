"""Runtime environment checks.

Provides a single public function ``check_environment()`` that tests whether
the external tools EncodeLab needs are reachable on the system PATH, and
whether any GPU (NVENC) encoders are available in the installed ffmpeg build.

Keeping this in its own module means:
- The UI can call it at startup and on demand without importing converter logic.
- Unit tests can patch ``shutil.which`` without touching the rest of the stack.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

# Suppress the black CMD flash on Windows --windowed builds.
_CREATION_FLAGS: int = 0
if sys.platform == "win32":
    _CREATION_FLAGS = subprocess.CREATE_NO_WINDOW


# Names of the binaries EncodeLab requires.
_FFMPEG_BIN  = "ffmpeg"
_FFPROBE_BIN = "ffprobe"

# GPU encoder names to detect.  These are the ``video_codec`` values used by
# the NVENC presets in ``logic/presets.py``.
_GPU_ENCODERS_TO_CHECK: frozenset[str] = frozenset({"h264_nvenc", "hevc_nvenc"})

# Regex that matches encoder lines in ``ffmpeg -encoders`` output.
# Example: " V..... h264_nvenc           NVIDIA NVENC H.264 encoder"
# We capture the encoder name (second whitespace-separated token on the line).
_ENCODER_LINE_RE = re.compile(r"^\s*V[A-Z.]{5}\s+(\S+)", re.MULTILINE)


# ---------------------------------------------------------------------------
# GPU encoder detection
# ---------------------------------------------------------------------------

def _query_available_encoders() -> frozenset[str]:
    """Run ``ffmpeg -encoders`` and return the set of available encoder names.

    Only the GPU encoders listed in ``_GPU_ENCODERS_TO_CHECK`` are returned;
    the full list would be large and is not needed elsewhere.

    Returns an empty frozenset if ffmpeg is not found or the subprocess fails.
    """
    if shutil.which(_FFMPEG_BIN) is None:
        return frozenset()

    try:
        result = subprocess.run(
            [_FFMPEG_BIN, "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            creationflags=_CREATION_FLAGS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()

    found: set[str] = set()
    for m in _ENCODER_LINE_RE.finditer(result.stdout):
        name = m.group(1)
        if name in _GPU_ENCODERS_TO_CHECK:
            found.add(name)
    return frozenset(found)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EnvironmentCheckResult:
    """Snapshot of tool availability at the time ``check_environment`` ran.

    Attributes
    ----------
    ffmpeg_path
        Absolute path to the ffmpeg binary, or ``None`` if not found.
    ffprobe_path
        Absolute path to the ffprobe binary, or ``None`` if not found.
    available_gpu_encoders
        Frozenset of GPU encoder names (e.g. ``"h264_nvenc"``) that are
        compiled into the installed ffmpeg build.  Empty when ffmpeg is
        absent or no GPU encoders are available.
    """

    ffmpeg_path:           str | None
    ffprobe_path:          str | None
    available_gpu_encoders: frozenset[str] = field(default_factory=frozenset)

    @property
    def ffmpeg_ok(self) -> bool:
        return self.ffmpeg_path is not None

    @property
    def ffprobe_ok(self) -> bool:
        return self.ffprobe_path is not None

    @property
    def all_ok(self) -> bool:
        """``True`` only when every required tool is present."""
        return self.ffmpeg_ok and self.ffprobe_ok

    def gpu_encoder_available(self, codec: str) -> bool:
        """Return ``True`` if *codec* is present in the available GPU encoders.

        Example::

            env.gpu_encoder_available("h264_nvenc")  # True on NVIDIA systems
        """
        return codec in self.available_gpu_encoders

    def missing(self) -> list[str]:
        """Return the names of tools that could not be found."""
        absent = []
        if not self.ffmpeg_ok:
            absent.append(_FFMPEG_BIN)
        if not self.ffprobe_ok:
            absent.append(_FFPROBE_BIN)
        return absent

    def user_message(self) -> str:
        """Return a plain-English sentence suitable for display in the log panel.

        Returns an empty string when everything is available.
        """
        absent = self.missing()
        if not absent:
            return ""
        tools = " and ".join(absent)
        return (
            f"{tools} could not be found on your system PATH.  "
            f"Install ffmpeg (https://ffmpeg.org/download.html) and make sure "
            f"the installation directory is listed in PATH, then restart EncodeLab."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_environment() -> EnvironmentCheckResult:
    """Probe the system PATH for ffmpeg and ffprobe, and detect GPU encoders.

    Uses ``shutil.which`` to locate the binaries and ``ffmpeg -encoders`` to
    discover which GPU encoders are compiled into the installed build.  The
    GPU encoder query is skipped when ffmpeg is not found.
    """
    ffmpeg_path  = shutil.which(_FFMPEG_BIN)
    ffprobe_path = shutil.which(_FFPROBE_BIN)
    gpu_encoders = _query_available_encoders() if ffmpeg_path else frozenset()

    return EnvironmentCheckResult(
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
        available_gpu_encoders=gpu_encoders,
    )
