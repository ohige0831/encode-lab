"""Source-file compatibility analysis — pure logic, no Qt.

Inspects a ``MediaInfo`` snapshot and returns a list of
``CompatibilityWarning`` objects.  The UI surfaces these in the log panel
immediately after ffprobe finishes, before the user starts a conversion.
"""

from __future__ import annotations

from dataclasses import dataclass

from logic.ffprobe_reader import MediaInfo


@dataclass(frozen=True)
class CompatibilityWarning:
    message:  str
    severity: str       # "warn" | "error"
    category: str = ""  # "codec" | "pixel_format" | "resolution" — for future filtering


# Codecs that are unplayable in Discord / PowerPoint / QuickTime without
# conversion.  rawvideo is the most common culprit for scientific/industrial
# cameras (e.g. AVI captures from frame grabbers).
_RISKY_CODECS: frozenset[str] = frozenset({
    "rawvideo",  # uncompressed frames — not embeddable in MP4; no OS decoder
    "huffyuv",   # lossless compression — no hardware decoder on most systems
    "ffv1",      # archival codec — no browser / OS decoder
    "ljpeg",     # lossless JPEG — not a playback codec
    "vp8", "vp9",  # no QuickTime / PowerPoint support without a codec pack
    "av1",         # PowerPoint unsupported; limited QuickTime support
})

# Pixel formats that cause silent failures in QuickTime or PowerPoint.
# yuv420p is the one safe target for H.264 in these environments.
_RISKY_PIX_FMTS: frozenset[str] = frozenset({
    # 10-bit / 12-bit — stripped or misrendered by PowerPoint & older QuickTime
    "yuv420p10le", "yuv420p10be",
    "yuv420p12le", "yuv420p12be",
    "yuv422p10le", "yuv422p10be",
    "yuv444p10le", "yuv444p10be",
    # 4:2:2 / 4:4:4 — H.264 High profile supports these but PowerPoint does not
    "yuv444p", "yuv422p",
    # RGB / BGR variants from industrial cameras and screen captures
    "rgb24", "bgr24", "rgba", "bgra",
    "gbrp", "gbrp10le",
})


def check_compatibility(info: MediaInfo) -> list[CompatibilityWarning]:
    """Return compatibility warnings for *info*.

    Returns an empty list when no issues are detected.  The caller is
    responsible for displaying or logging the results; this function has
    no side effects.
    """
    warnings: list[CompatibilityWarning] = []

    # --- codec ----------------------------------------------------------
    if info.video_codec and info.video_codec.lower() in _RISKY_CODECS:
        warnings.append(CompatibilityWarning(
            message=(
                f"Codec '{info.video_codec}' cannot be played by Discord, "
                f"PowerPoint, or QuickTime without conversion — "
                f"use the Compatible preset"
            ),
            severity="warn",
            category="codec",
        ))

    # --- pixel format ---------------------------------------------------
    if info.pix_fmt and info.pix_fmt.lower() in _RISKY_PIX_FMTS:
        warnings.append(CompatibilityWarning(
            message=(
                f"Pixel format '{info.pix_fmt}' may not render correctly in "
                f"QuickTime or PowerPoint — "
                f"the Compatible preset will convert it to yuv420p"
            ),
            severity="warn",
            category="pixel_format",
        ))

    # --- odd resolution -------------------------------------------------
    if info.width is not None and info.width % 2 != 0:
        warnings.append(CompatibilityWarning(
            message=(
                f"Width {info.width} px is odd — "
                f"yuv420p encoding requires even dimensions; "
                f"the Compatible preset pads automatically"
            ),
            severity="warn",
            category="resolution",
        ))
    if info.height is not None and info.height % 2 != 0:
        warnings.append(CompatibilityWarning(
            message=(
                f"Height {info.height} px is odd — "
                f"yuv420p encoding requires even dimensions; "
                f"the Compatible preset pads automatically"
            ),
            severity="warn",
            category="resolution",
        ))

    return warnings
