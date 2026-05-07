"""Tests for build_ffmpeg_command() — pure command construction, no subprocess."""
from pathlib import Path

import pytest

from logic.converter import ConversionJob, ConversionSettings, build_ffmpeg_command
from logic.presets import PRESETS

_SRC = Path("input.avi")


def _job(preset: str, has_audio: bool | None = None, crf: int = 23) -> ConversionJob:
    settings = ConversionSettings(preset=preset, crf=crf)
    return ConversionJob(input_path=_SRC, settings=settings, has_audio=has_audio)


# ---------------------------------------------------------------------------
# Compatible preset — the primary safety target
# ---------------------------------------------------------------------------

class TestCompatiblePreset:

    PRESET = "H.264 — Compatible (Discord / PowerPoint)"

    def _cmd(self, **kw) -> list[str]:
        return build_ffmpeg_command(_job(self.PRESET, **kw))

    def test_codec(self):
        cmd = self._cmd()
        assert "-vcodec" in cmd
        assert cmd[cmd.index("-vcodec") + 1] == "libx264"

    def test_profile_and_level(self):
        cmd = self._cmd()
        assert "-profile:v" in cmd
        assert cmd[cmd.index("-profile:v") + 1] == "high"
        assert "-level" in cmd
        assert cmd[cmd.index("-level") + 1] == "4.1"

    def test_pix_fmt(self):
        cmd = self._cmd()
        assert "-pix_fmt" in cmd
        assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"

    def test_crf(self):
        cmd = self._cmd(crf=18)
        assert "-crf" in cmd
        assert cmd[cmd.index("-crf") + 1] == "18"

    def test_preset_speed(self):
        cmd = self._cmd()
        assert "-preset" in cmd
        assert cmd[cmd.index("-preset") + 1] == "medium"

    def test_video_filter(self):
        cmd = self._cmd()
        assert "-vf" in cmd

    def test_cfr_flag(self):
        cmd = self._cmd()
        assert "-fps_mode" in cmd
        assert cmd[cmd.index("-fps_mode") + 1] == "cfr"

    def test_faststart(self):
        cmd = self._cmd()
        assert "-movflags" in cmd
        assert cmd[cmd.index("-movflags") + 1] == "+faststart"

    def test_mp4_output(self):
        cmd = self._cmd()
        assert cmd[-1].endswith(".mp4")

    # -- Audio handling --

    def test_no_audio_source_produces_an(self):
        cmd = self._cmd(has_audio=False)
        assert "-an" in cmd
        assert "-acodec" not in cmd

    def test_audio_source_produces_aac(self):
        cmd = self._cmd(has_audio=True)
        assert "-acodec" in cmd
        assert cmd[cmd.index("-acodec") + 1] == "aac"
        assert "-b:a" in cmd
        assert "-an" not in cmd

    def test_unknown_audio_falls_back_to_aac(self):
        """has_audio=None means not probed — original behaviour: attempt AAC."""
        cmd = self._cmd(has_audio=None)
        assert "-acodec" in cmd
        assert "-an" not in cmd

    # -- Flag ordering --

    def test_flag_order(self):
        # Use has_audio=False so -an is always present for the order assertion
        cmd = self._cmd(has_audio=False)
        idx = cmd.index
        assert idx("-vcodec") < idx("-profile:v")
        assert idx("-profile:v") < idx("-pix_fmt")
        assert idx("-pix_fmt") < idx("-crf")
        assert idx("-crf") < idx("-preset")
        assert idx("-preset") < idx("-vf")
        assert idx("-vf") < idx("-fps_mode")
        assert idx("-fps_mode") < idx("-an")
        assert idx("-an") < idx("-movflags")

    # -- is_recommended / force_cfr sanity --

    def test_preset_flags(self):
        cfg = PRESETS[self.PRESET]
        assert cfg.is_recommended is True
        assert cfg.force_cfr is True
        assert cfg.video_profile == "high"
        assert cfg.video_level == "4.1"
        assert cfg.pix_fmt == "yuv420p"
        assert cfg.extra_video_flags == ()


# ---------------------------------------------------------------------------
# Profile / level contamination — non-H.264 presets must not inherit High/4.1
# ---------------------------------------------------------------------------

class TestNoProfileContamination:

    def test_prores_uses_codec_profile_not_h264_profile(self):
        cmd = build_ffmpeg_command(_job("ProRes 422 — Editing"))
        # ProRes numeric profile "2" comes via extra_video_flags
        assert "-profile:v" in cmd
        assert cmd[cmd.index("-profile:v") + 1] == "2"
        # "high" and "4.1" must not appear at all
        assert "high" not in cmd
        assert "4.1" not in cmd
        assert "-level" not in cmd

    def test_gif_has_no_profile_or_level(self):
        cmd = build_ffmpeg_command(_job("GIF — Animated"))
        assert "-profile:v" not in cmd
        assert "-level" not in cmd
        assert "-pix_fmt" not in cmd
        assert "-acodec" not in cmd
        assert "-an" in cmd

    def test_hevc_balanced_has_no_h264_profile(self):
        cmd = build_ffmpeg_command(_job("H.265 / HEVC — Balanced"))
        assert "high" not in cmd
        assert "4.1" not in cmd
        assert "-level" not in cmd

    def test_nvenc_h264_has_no_profile_level(self):
        """NVENC quality is controlled via extra_video_flags, not video_profile."""
        cmd = build_ffmpeg_command(_job("H.264 NVENC — Fast web"))
        assert "-profile:v" not in cmd
        assert "-level" not in cmd
        assert "-rc" in cmd   # NVENC VBR quality flags are present
        assert "-cq" in cmd

    def test_av1_has_no_profile_level(self):
        cmd = build_ffmpeg_command(_job("AV1 — High efficiency"))
        assert "-profile:v" not in cmd
        assert "-level" not in cmd


# ---------------------------------------------------------------------------
# H.264 Fast / High quality — profile and level should now be explicit
# ---------------------------------------------------------------------------

class TestH264NonCompatiblePresets:

    @pytest.mark.parametrize("preset", [
        "H.264 — Fast (web)",
        "H.264 — High quality",
    ])
    def test_profile_and_level_present(self, preset: str):
        cmd = build_ffmpeg_command(_job(preset))
        assert "-profile:v" in cmd
        assert cmd[cmd.index("-profile:v") + 1] == "high"
        assert "-level" in cmd
        assert cmd[cmd.index("-level") + 1] == "4.1"

    def test_fast_web_uses_fast_encoder_preset(self):
        cmd = build_ffmpeg_command(_job("H.264 — Fast (web)"))
        assert cmd[cmd.index("-preset") + 1] == "fast"

    def test_high_quality_crf_18_when_specified(self):
        cmd = build_ffmpeg_command(_job("H.264 — High quality", crf=18))
        assert cmd[cmd.index("-crf") + 1] == "18"

    def test_fast_web_no_cfr_flag(self):
        """Only the Compatible preset forces CFR."""
        cfg = PRESETS["H.264 — Fast (web)"]
        assert cfg.force_cfr is False
        cmd = build_ffmpeg_command(_job("H.264 — Fast (web)"))
        assert "-fps_mode" not in cmd
