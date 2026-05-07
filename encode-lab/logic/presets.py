"""Preset registry and quality-tier constants.

This is the single source of truth for:
- Which video/audio codecs each preset uses.
- Default CRF values for the three quality tiers.
- The set of file extensions the app accepts.
- Human-readable descriptions and quality-mode summaries shown in the UI.

Neither the UI nor the converter should hard-code these values; they read
them from here so adding a new preset only requires one edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


# ---------------------------------------------------------------------------
# Accepted input extensions
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS: Final[frozenset[str]] = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
    ".webm", ".m4v", ".ts", ".mts", ".m2ts", ".3gp", ".ogv", ".vob",
})


# ---------------------------------------------------------------------------
# Quality tier CRF defaults
# ---------------------------------------------------------------------------

QUALITY_CRF: Final[dict[str, int]] = {
    "high_quality": 18,   # visually lossless for most content
    "standard":     23,   # ffmpeg's own default; good balance
    "lightweight":  32,   # noticeably smaller file, some quality loss
}


# ---------------------------------------------------------------------------
# PresetConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PresetConfig:
    """All codec-level parameters for one named preset.

    Fields
    ------
    name
        Display name shown in the combo box.  Must match the registry key.
    description
        One-sentence summary of the preset shown in the UI beneath the combo.
        Should cover use-case and trade-offs at a glance.
    quality_mode
        Short label describing how quality is controlled, e.g.
        ``"CRF 23 — standard quality"`` or ``"CQ 23 (VBR, NVENC)"``.
        Displayed alongside the description.
    video_codec
        Value passed to ffmpeg ``-vcodec``.
    audio_codec
        Value passed to ffmpeg ``-acodec``.  Empty string means no audio
        track is possible for this format (e.g. GIF).
    crf
        Default Constant Rate Factor.  ``0`` means CRF is not applicable —
        the quality flags are either baked into ``extra_video_flags`` (NVENC)
        or simply not needed (ProRes, GIF).
    encoder_preset
        Value passed to ffmpeg ``-preset`` (speed/quality tradeoff).
        Empty string means the flag is omitted entirely.
    container
        Output file extension including the leading dot, e.g. ``".mp4"``.
    uses_gpu
        ``True`` when this preset targets a GPU encoder (e.g. NVENC).
        The UI uses this flag to show a GPU badge and to adjust the CRF
        tooltip in the advanced panel.
    extra_video_flags
        Additional flags inserted into the command between ``-vcodec`` and
        the quality block.  Use a tuple so the dataclass stays hashable.
        For GPU presets this carries the full quality-mode arguments
        (e.g. ``"-rc", "vbr", "-cq", "23", "-b:v", "0"``).
    """

    name:              str
    description:       str
    quality_mode:      str
    video_codec:       str
    audio_codec:       str
    crf:               int
    encoder_preset:    str
    container:         str
    uses_gpu:          bool            = False
    is_recommended:    bool            = False            # marks the primary safe preset for UI hints
    extra_video_flags: tuple[str, ...] = field(default_factory=tuple)
    video_profile:     str             = ""               # -profile:v; empty = omit (e.g. "high", "main")
    video_level:       str             = ""               # -level; empty = omit (e.g. "4.1", "3.1")
    pix_fmt:           str             = ""               # -pix_fmt; empty = omit
    video_filter:      str             = ""               # -vf; overridden by user resolution
    audio_bitrate:     str             = ""               # -b:a; empty = omit
    output_flags:      tuple[str, ...] = field(default_factory=tuple)  # e.g. -movflags +faststart
    force_cfr:         bool            = False            # add -fps_mode cfr to ensure constant frame rate


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PRESETS: Final[dict[str, PresetConfig]] = {

    # ── Compatibility preset ─────────────────────────────────────────────────

    "H.264 — Compatible (Discord / PowerPoint)": PresetConfig(
        name="H.264 — Compatible (Discord / PowerPoint)",
        description=(
            "[Recommended] MP4 · H.264 High 4.1 · yuv420p · CFR · faststart — "
            "safest preset for Discord, PowerPoint, QuickTime, Windows, and browsers"
        ),
        quality_mode=f"CRF {QUALITY_CRF['standard']} — standard quality",
        video_codec="libx264",
        audio_codec="aac",
        crf=QUALITY_CRF["standard"],
        encoder_preset="medium",
        container=".mp4",
        is_recommended=True,
        force_cfr=True,
        video_profile="high",
        video_level="4.1",
        pix_fmt="yuv420p",
        # Rounds odd source dimensions to even — required by yuv420p / H.264
        video_filter="scale=trunc(iw/2)*2:trunc(ih/2)*2",
        audio_bitrate="192k",
        output_flags=("-movflags", "+faststart"),
    ),

    # ── CPU presets ──────────────────────────────────────────────────────────

    "H.264 — Fast (web)": PresetConfig(
        name="H.264 — Fast (web)",
        description="MP4 / H.264 · fast encode, ideal for web upload and streaming",
        quality_mode=f"CRF {QUALITY_CRF['standard']} — standard quality",
        video_codec="libx264",
        audio_codec="aac",
        crf=QUALITY_CRF["standard"],
        encoder_preset="fast",
        container=".mp4",
        video_profile="high",
        video_level="4.1",
    ),

    "H.264 — High quality": PresetConfig(
        name="H.264 — High quality",
        description="MP4 / H.264 · slow encode, highest CPU-based quality",
        quality_mode=f"CRF {QUALITY_CRF['high_quality']} — high quality",
        video_codec="libx264",
        audio_codec="aac",
        crf=QUALITY_CRF["high_quality"],
        encoder_preset="slow",
        container=".mp4",
        video_profile="high",
        video_level="4.1",
    ),

    "H.265 / HEVC — Balanced": PresetConfig(
        name="H.265 / HEVC — Balanced",
        description="MP4 / HEVC · roughly half the size of H.264 at similar quality",
        quality_mode=f"CRF {QUALITY_CRF['standard']} — standard quality",
        video_codec="libx265",
        audio_codec="aac",
        crf=QUALITY_CRF["standard"],
        encoder_preset="medium",
        container=".mp4",
    ),

    "H.265 / HEVC — Small file": PresetConfig(
        name="H.265 / HEVC — Small file",
        description="MP4 / HEVC · slow encode, smallest file at acceptable quality",
        quality_mode=f"CRF {QUALITY_CRF['lightweight']} — lightweight",
        video_codec="libx265",
        audio_codec="aac",
        crf=QUALITY_CRF["lightweight"],
        encoder_preset="slow",
        container=".mp4",
    ),

    "AV1 — High efficiency": PresetConfig(
        name="AV1 — High efficiency",
        description="MP4 / AV1 (SVT) · best compression ratio, very slow CPU encode",
        quality_mode=f"CRF {QUALITY_CRF['lightweight']} — lightweight",
        video_codec="libsvtav1",
        audio_codec="libopus",
        crf=QUALITY_CRF["lightweight"],
        # SVT-AV1 uses -preset 0–13 (speed); leave blank, user can override
        # via the Extra flags field if needed.
        encoder_preset="",
        container=".mp4",
    ),

    "ProRes 422 — Editing": PresetConfig(
        name="ProRes 422 — Editing",
        description="MOV / ProRes 422 · editing master, large file, no quality loss",
        quality_mode="Fixed quality — no CRF",
        video_codec="prores_ks",
        audio_codec="pcm_s16le",
        crf=0,
        encoder_preset="",
        container=".mov",
        extra_video_flags=("-profile:v", "2"),   # 422 profile
    ),

    "GIF — Animated": PresetConfig(
        name="GIF — Animated",
        description="Animated GIF · no audio, 256-colour palette, short clips only",
        quality_mode="Palette-based — no CRF",
        video_codec="gif",
        audio_codec="",
        crf=0,
        encoder_preset="",
        container=".gif",
    ),

    # ── NVENC (GPU) presets ──────────────────────────────────────────────────
    #
    # NVENC does not use -crf.  Quality is controlled by -cq (Constant Quality)
    # in VBR mode.  The full quality block is embedded in extra_video_flags so
    # build_ffmpeg_command needs no changes — crf=0 already skips the quality
    # section, and extra_video_flags are inserted right after -vcodec.
    #
    # Recommended VBR-CQ invocation:
    #   ffmpeg -vcodec h264_nvenc -rc vbr -cq 23 -b:v 0 -preset fast ...
    #
    # Users who want a different CQ value should use the Extra flags field,
    # e.g. "-cq 18" to override quality.

    "H.264 NVENC — Fast web": PresetConfig(
        name="H.264 NVENC — Fast web",
        description="MP4 / H.264 · NVIDIA GPU encoder, fast hardware-accelerated encode",
        quality_mode="CQ 23 — VBR (NVENC)",
        video_codec="h264_nvenc",
        audio_codec="aac",
        crf=0,           # CRF not used; quality baked into extra_video_flags
        encoder_preset="fast",
        container=".mp4",
        uses_gpu=True,
        extra_video_flags=("-rc", "vbr", "-cq", "23", "-b:v", "0"),
    ),

    "HEVC NVENC — Compact": PresetConfig(
        name="HEVC NVENC — Compact",
        description="MP4 / HEVC · NVIDIA GPU encoder, compact file with GPU speed",
        quality_mode="CQ 23 — VBR (NVENC)",
        video_codec="hevc_nvenc",
        audio_codec="aac",
        crf=0,
        encoder_preset="medium",
        container=".mp4",
        uses_gpu=True,
        extra_video_flags=("-rc", "vbr", "-cq", "23", "-b:v", "0"),
    ),
}


def get_preset_names() -> list[str]:
    """Return preset names in insertion order (matches the combo box)."""
    return list(PRESETS.keys())
