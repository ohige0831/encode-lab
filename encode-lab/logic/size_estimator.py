"""Output size estimator.

Pure logic module — no Qt imports.  Provides ``estimate_output_size``, which
converts encoding settings and total media duration into a display string.

Only explicit-bitrate mode allows a meaningful numeric estimate.  CRF and
quality-fixed codecs (GPU CQ, ProRes, GIF) return a descriptive message
instead, because file size depends on scene complexity in ways that cannot be
predicted from settings alone.
"""

from __future__ import annotations

import re

from logic.converter import ConversionSettings
from logic.presets import PresetConfig


# ---------------------------------------------------------------------------
# Audio bitrate estimates
# ---------------------------------------------------------------------------

# Uncompressed PCM: estimated at 44.1 kHz stereo (most common for editing).
# Lossy codecs (AAC, libopus) default to 128 kbps in ffmpeg.
_AUDIO_BITRATE_BPS: dict[str, int] = {
    "pcm_s16le": 1_411_200,   # 44.1 kHz, 16-bit, 2-channel
    "pcm_s24le": 2_116_800,   # 44.1 kHz, 24-bit, 2-channel
    "pcm_s32le": 2_822_400,   # 44.1 kHz, 32-bit, 2-channel
}
_DEFAULT_AUDIO_BPS: int = 128_000  # ffmpeg default for AAC / libopus


# ---------------------------------------------------------------------------
# Bitrate string parser
# ---------------------------------------------------------------------------

# Accepts: "4000k", "4.5M", "4000000", "1G" (SI multipliers, case-insensitive)
_BITRATE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kKmMgG]?)\s*$")

_SI_MULTIPLIERS: dict[str, int] = {
    "k": 1_000,
    "m": 1_000_000,
    "g": 1_000_000_000,
}


def parse_bitrate(s: str) -> int | None:
    """Parse an ffmpeg-style bitrate string to bits per second.

    Returns ``None`` when *s* cannot be parsed.

    Examples
    --------
    >>> parse_bitrate("4000k")
    4000000
    >>> parse_bitrate("4.5M")
    4500000
    >>> parse_bitrate("bad")
    None
    """
    m = _BITRATE_RE.match(s)
    if m is None:
        return None
    value = float(m.group(1))
    multiplier = _SI_MULTIPLIERS.get(m.group(2).lower(), 1)
    return int(value * multiplier)


# ---------------------------------------------------------------------------
# Byte formatter
# ---------------------------------------------------------------------------

def _format_bytes(n: int) -> str:
    """Return *n* bytes as a compact human-readable string."""
    if n < 1_000:
        return f"{n} B"
    if n < 1_000_000:
        return f"{n / 1_000:.1f} KB"
    if n < 1_000_000_000:
        return f"{n / 1_000_000:.1f} MB"
    return f"{n / 1_000_000_000:.2f} GB"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_output_size(
    settings: ConversionSettings,
    config: PresetConfig,
    total_duration_sec: float | None,
) -> str:
    """Return a human-readable estimated output size string.

    Parameters
    ----------
    settings:
        Current UI settings, including any explicit bitrate override.
    config:
        The resolved preset config (used for the audio codec lookup and to
        determine whether the encoder supports CRF).
    total_duration_sec:
        Sum of known durations for all queued files, or ``None`` when no
        file has been probed yet.

    Decision matrix
    ---------------
    - No explicit bitrate → ``"Estimated size: variable (CRF-based)"``
    - Explicit bitrate + duration unknown → ``"Estimated size: unavailable"``
    - Explicit bitrate + duration known   → ``"Estimated size: ~X MB (approx.)"``

    The audio track is included in the estimate when audio is enabled.
    """
    prefix = "Estimated size: "

    video_bps = parse_bitrate(settings.bitrate) if settings.bitrate else None

    if video_bps is None:
        # Quality is encoder-controlled (CRF, CQ, ProRes fixed quality, GIF).
        return f"{prefix}variable (CRF-based)"

    # Explicit bitrate mode — need duration for a meaningful number.
    if total_duration_sec is None or total_duration_sec <= 0:
        return f"{prefix}unavailable"

    audio_bps = 0
    if settings.audio_enabled and config.audio_codec:
        audio_bps = _AUDIO_BITRATE_BPS.get(config.audio_codec, _DEFAULT_AUDIO_BPS)

    total_bits  = (video_bps + audio_bps) * total_duration_sec
    total_bytes = int(total_bits / 8)

    return f"{prefix}~{_format_bytes(total_bytes)} (approx.)"
