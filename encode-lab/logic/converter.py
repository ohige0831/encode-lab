"""Conversion engine.

Public surface
--------------
ConversionSettings   — flat settings bag collected from the UI
ConversionJob        — one input file + settings; owns output-path derivation
build_ffmpeg_command — returns an argv list ready for subprocess, no side effects
stream_job           — run ffmpeg via Popen, yielding integer progress (0-100)
run_job              — thin blocking wrapper around stream_job (discards progress)
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Suppress the black CMD flash on Windows --windowed builds.
_CREATION_FLAGS: int = 0
if sys.platform == "win32":
    _CREATION_FLAGS = subprocess.CREATE_NO_WINDOW

from logic.presets import PRESETS, PresetConfig


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ConversionSettings:
    """Flat bag of settings collected from the UI before a job starts.

    The ``preset`` field must be a key present in ``logic.presets.PRESETS``.
    All other fields override the preset's defaults when non-empty / non-zero.
    """

    preset: str
    audio_enabled: bool = True
    crf: int = 23
    bitrate: str = ""       # e.g. "4000k"; non-empty overrides CRF
    resolution: str = ""    # e.g. "1920x1080"; empty keeps source dimensions
    extra_flags: str = ""   # raw ffmpeg flags appended verbatim
    output_dir: str = ""    # empty → place output beside the source file
    @classmethod
    def high_quality(cls, preset: str) -> "ConversionSettings":
        """Return settings pre-filled with high-quality CRF for *preset*."""
        from logic.presets import QUALITY_CRF
        return cls(preset=preset, crf=QUALITY_CRF["high_quality"])

    @classmethod
    def standard(cls, preset: str) -> "ConversionSettings":
        """Return settings pre-filled with standard CRF for *preset*."""
        from logic.presets import QUALITY_CRF
        return cls(preset=preset, crf=QUALITY_CRF["standard"])

    @classmethod
    def lightweight(cls, preset: str) -> "ConversionSettings":
        """Return settings pre-filled with lightweight CRF for *preset*."""
        from logic.presets import QUALITY_CRF
        return cls(preset=preset, crf=QUALITY_CRF["lightweight"])


@dataclass
class ConversionJob:
    """One input file paired with the settings that apply to it.

    ``output_path`` is derived automatically in ``__post_init__`` based on
    the preset's target container and any output directory override.

    ``duration_sec`` is optional media duration used by ``stream_job`` to
    compute progress percentages.  Populate it from ``MediaInfo.duration_sec``
    before passing the job to ``ConversionWorker``.
    """

    input_path:   Path
    settings:     ConversionSettings
    duration_sec: float | None = None   # from ffprobe; None → indeterminate bar
    output_path:  Path = field(init=False)

    def __post_init__(self) -> None:
        config = PRESETS[self.settings.preset]
        self.output_path = _make_unique_output_path(self.input_path, self.settings, config)


# ---------------------------------------------------------------------------
# Internal helpers — paths
# ---------------------------------------------------------------------------

def _make_unique_output_path(
    input_path: Path,
    settings: ConversionSettings,
    config: PresetConfig,
) -> Path:
    """Derive a collision-free output path.

    Naming strategy
    ---------------
    1. Try ``<stem>_converted<ext>`` first.
    2. If that file already exists, try ``<stem>_converted_01<ext>``,
       ``_converted_02``, … up to ``_converted_99``.
    3. If all 99 numbered slots are taken (extremely unlikely), fall back to
       the base name and let ffmpeg's ``-y`` flag overwrite it.
    """
    base_dir  = Path(settings.output_dir) if settings.output_dir else input_path.parent
    ext       = config.container
    stem_base = input_path.stem + "_converted"

    candidate = base_dir / (stem_base + ext)
    if not candidate.exists():
        return candidate

    for n in range(1, 100):
        candidate = base_dir / f"{stem_base}_{n:02d}{ext}"
        if not candidate.exists():
            return candidate

    return base_dir / (stem_base + ext)  # fallback; ffmpeg -y overwrites


def _parse_resolution(resolution: str) -> tuple[str, str]:
    """Split ``"1920x1080"`` into ``("1920", "1080")``.

    Raises ``ValueError`` if the string is not in ``WxH`` format.
    """
    parts = resolution.lower().split("x")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        raise ValueError(
            f"Resolution must be in WxH format (e.g. '1920x1080'), got {resolution!r}"
        )
    return parts[0].strip(), parts[1].strip()


# ---------------------------------------------------------------------------
# Internal helpers — progress parsing
# ---------------------------------------------------------------------------

# ffmpeg progress lines look like:
#   frame=  100 fps= 24 q=28.0 size=    512kB time=00:00:04.17 bitrate=...
# The timestamp uses HH:MM:SS.fractional format.
# ffmpeg also emits "time=N/A" and "time=-577014:32:22.77" before encoding
# starts; the regex below matches only non-negative HH:MM:SS.frac values.
_TIME_RE = re.compile(r"time=(\d+):(\d{2}):(\d{2})\.(\d+)")


def _parse_time_line(line: str) -> float | None:
    """Return elapsed seconds from an ffmpeg progress line, or ``None``.

    Returns ``None`` when the line contains no ``time=`` field, when the
    field value is ``N/A``, or when the timestamp is negative (ffmpeg
    emits large negative timestamps before encoding begins).
    """
    m = _TIME_RE.search(line)
    if m is None:
        return None
    h, mn, s, frac = m.groups()
    elapsed = int(h) * 3600 + int(mn) * 60 + int(s) + int(frac) / (10 ** len(frac))
    return elapsed if elapsed >= 0 else None


def _compute_percent(elapsed: float, total: float | None) -> int:
    """Convert elapsed seconds to an integer progress value in ``[0, 99]``.

    Returns ``0`` when *total* is unknown or zero.  The upper bound is 99
    rather than 100 so that the progress bar reaches 100 only when ffmpeg
    exits successfully — not one second before the end of the file.
    """
    if not total or total <= 0:
        return 0
    return min(99, int(elapsed / total * 100))


# ---------------------------------------------------------------------------
# Command builder
# ---------------------------------------------------------------------------

def build_ffmpeg_command(job: ConversionJob) -> list[str]:
    """Return the ffmpeg argv list for *job* without executing anything.

    The returned list is safe to pass directly to ``subprocess.Popen`` with
    ``shell=False``.  No shell escaping is needed because each element is a
    separate argument.

    Order of flags follows ffmpeg convention:
      ffmpeg -y -i <input> <video flags> <audio flags> [filters] [extra] <output>
    """
    config = PRESETS[job.settings.preset]

    cmd: list[str] = ["ffmpeg", "-y", "-i", str(job.input_path)]

    # --- video codec -------------------------------------------------------
    cmd += ["-vcodec", config.video_codec]
    cmd += list(config.extra_video_flags)   # e.g. ProRes profile, SVT-AV1 params

    # --- quality: bitrate overrides CRF when set ---------------------------
    if job.settings.bitrate:
        cmd += ["-b:v", job.settings.bitrate]
        # TODO: add -maxrate / -bufsize for CBR/VBR capping if needed
    elif config.crf > 0:
        cmd += ["-crf", str(job.settings.crf)]

    # --- encoder speed/quality preset --------------------------------------
    if config.encoder_preset:
        cmd += ["-preset", config.encoder_preset]

    # --- scale filter ------------------------------------------------------
    if job.settings.resolution:
        width, height = _parse_resolution(job.settings.resolution)
        cmd += ["-vf", f"scale={width}:{height}"]
        # TODO: add :flags=lanczos for high-quality downscaling

    # --- audio -------------------------------------------------------------
    if not config.audio_codec:
        cmd += ["-an"]
    elif not job.settings.audio_enabled:
        cmd += ["-an"]
    else:
        cmd += ["-acodec", config.audio_codec]
        # TODO: add -b:a / -ar flags for audio bitrate/sample-rate control

    # --- user extra flags --------------------------------------------------
    if job.settings.extra_flags:
        cmd += shlex.split(job.settings.extra_flags)

    cmd.append(str(job.output_path))
    return cmd


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

class ConversionError(Exception):
    """Raised when ffmpeg exits with a non-zero return code.

    The exception message contains the captured stderr so callers (e.g.
    ``ConversionWorker``) can surface a trimmed excerpt in the log panel.
    """


def stream_job(job: ConversionJob) -> Iterator[int]:
    """Run ffmpeg for *job* via ``Popen``, yielding integer progress values.

    Yield sequence
    --------------
    - ``0``         immediately when the process is spawned.
    - ``1``–``99``  as ffmpeg writes ``time=`` progress lines to stderr.
    - ``100``       once, after ffmpeg exits with return code 0.

    Raises
    ------
    ConversionError
        If ffmpeg exits with a non-zero return code.  The exception message
        contains the full captured stderr.

    Cancellation
    ------------
    The caller can break out of the ``for percent in stream_job(job)`` loop
    at any time.  Python will then call ``generator.close()``, which injects
    ``GeneratorExit`` into the generator.  The ``finally`` block terminates
    the ffmpeg process and reaps it so no zombie is left behind.

    To terminate ffmpeg *immediately* (rather than waiting for the current
    frame to finish), call ``proc.terminate()`` before ``proc.wait()`` in the
    ``finally`` block.  The ``ConversionWorker`` will need to expose a handle
    to the ``Popen`` object to support this — see the TODO in ``worker.py``.
    """
    cmd = build_ffmpeg_command(job)
    stderr_lines: list[str] = []

    proc = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,   # line-buffered so progress updates arrive promptly
        creationflags=_CREATION_FLAGS,
    )

    yield 0  # process is alive; bar starts moving

    try:
        assert proc.stderr is not None  # guaranteed by stderr=PIPE
        for line in proc.stderr:
            stderr_lines.append(line)
            elapsed = _parse_time_line(line)
            if elapsed is not None:
                yield _compute_percent(elapsed, job.duration_sec)
    finally:
        # Runs on normal exit AND on GeneratorExit (caller broke out of loop).
        # Terminate first so we don't block forever if the caller cancelled.
        # TODO: expose proc to ConversionWorker.request_cancel() so the UI
        #       Cancel button can call proc.terminate() for immediate stop.
        if proc.poll() is None:  # still running (only true after a break/close)
            proc.terminate()
        proc.wait()

    if proc.returncode != 0:
        output = "".join(stderr_lines)
        raise ConversionError(output or f"ffmpeg exited with code {proc.returncode}")

    yield 100


def run_job(job: ConversionJob) -> None:
    """Execute *job* synchronously, discarding progress updates.

    A convenience wrapper around ``stream_job`` for callers that only need
    success/failure and do not need incremental progress (e.g. unit tests).
    Raises ``ConversionError`` on failure.
    """
    for _ in stream_job(job):
        pass
