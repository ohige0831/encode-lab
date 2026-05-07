"""Tests for compatibility.py warning detection."""
import pytest

from logic.compatibility import CompatibilityWarning, check_compatibility
from logic.ffprobe_reader import MediaInfo


def _info(**kw) -> MediaInfo:
    defaults = dict(
        duration_sec=None, width=None, height=None,
        video_codec=None, pix_fmt=None, has_audio_stream=False,
    )
    defaults.update(kw)
    return MediaInfo(**defaults)


def _categories(warnings: list[CompatibilityWarning]) -> set[str]:
    return {w.category for w in warnings}


# ---------------------------------------------------------------------------
# Codec warnings
# ---------------------------------------------------------------------------

class TestCodecWarnings:

    @pytest.mark.parametrize("codec", ["rawvideo", "huffyuv", "ffv1", "vp8", "vp9", "av1"])
    def test_risky_codec_warns(self, codec: str):
        warns = check_compatibility(_info(video_codec=codec))
        assert any(w.category == "codec" for w in warns)

    @pytest.mark.parametrize("codec", ["h264", "hevc", "mjpeg", "mpeg4"])
    def test_safe_codec_no_codec_warning(self, codec: str):
        warns = check_compatibility(_info(video_codec=codec))
        assert not any(w.category == "codec" for w in warns)

    def test_codec_warning_severity_is_warn(self):
        warns = check_compatibility(_info(video_codec="rawvideo"))
        for w in warns:
            if w.category == "codec":
                assert w.severity == "warn"


# ---------------------------------------------------------------------------
# Pixel format warnings
# ---------------------------------------------------------------------------

class TestPixelFormatWarnings:

    @pytest.mark.parametrize("pix_fmt", [
        "bgr24", "rgb24", "yuv444p", "yuv422p",
        "yuv420p10le", "yuv444p10le",
    ])
    def test_risky_pix_fmt_warns(self, pix_fmt: str):
        warns = check_compatibility(_info(pix_fmt=pix_fmt))
        assert any(w.category == "pixel_format" for w in warns)

    @pytest.mark.parametrize("pix_fmt", ["yuv420p", "nv12"])
    def test_safe_pix_fmt_no_warning(self, pix_fmt: str):
        warns = check_compatibility(_info(pix_fmt=pix_fmt))
        assert not any(w.category == "pixel_format" for w in warns)


# ---------------------------------------------------------------------------
# Resolution warnings
# ---------------------------------------------------------------------------

class TestResolutionWarnings:

    def test_odd_width_warns(self):
        warns = check_compatibility(_info(width=1281, height=1024))
        assert any("Width" in w.message and w.category == "resolution" for w in warns)

    def test_odd_height_warns(self):
        warns = check_compatibility(_info(width=1280, height=1025))
        assert any("Height" in w.message and w.category == "resolution" for w in warns)

    def test_both_odd_warns_twice(self):
        warns = check_compatibility(_info(width=1281, height=1025))
        resolution_warns = [w for w in warns if w.category == "resolution"]
        assert len(resolution_warns) == 2

    def test_even_resolution_no_warning(self):
        warns = check_compatibility(_info(width=1280, height=1024))
        assert not any(w.category == "resolution" for w in warns)


# ---------------------------------------------------------------------------
# Audio-less source must NOT produce a warning
# ---------------------------------------------------------------------------

class TestNoAudioIsSafe:

    def test_no_audio_no_audio_category_warning(self):
        """Research videos without audio are normal — no warning should be raised."""
        warns = check_compatibility(_info(
            video_codec="rawvideo", pix_fmt="bgr24",
            width=1280, height=1024, has_audio_stream=False,
        ))
        assert "audio" not in _categories(warns)

    def test_no_audio_still_allows_codec_and_pix_fmt_warnings(self):
        warns = check_compatibility(_info(
            video_codec="rawvideo", pix_fmt="bgr24",
            width=1280, height=1024, has_audio_stream=False,
        ))
        assert "codec" in _categories(warns)
        assert "pixel_format" in _categories(warns)


# ---------------------------------------------------------------------------
# Research video full scenario — rawvideo bgr24 1280×1024 no audio 15fps
# ---------------------------------------------------------------------------

class TestResearchVideoScenario:

    _INFO = _info(
        video_codec="rawvideo",
        pix_fmt="bgr24",
        width=1280,
        height=1024,
        has_audio_stream=False,
        duration_sec=375.6,
    )

    def test_exactly_two_warnings(self):
        warns = check_compatibility(self._INFO)
        assert len(warns) == 2

    def test_warning_categories(self):
        warns = check_compatibility(self._INFO)
        assert _categories(warns) == {"codec", "pixel_format"}

    def test_no_resolution_warning(self):
        """1280×1024 is even — no dimension warning expected."""
        warns = check_compatibility(self._INFO)
        assert "resolution" not in _categories(warns)

    def test_no_audio_warning(self):
        warns = check_compatibility(self._INFO)
        assert "audio" not in _categories(warns)

    def test_all_warnings_are_warn_severity(self):
        warns = check_compatibility(self._INFO)
        assert all(w.severity == "warn" for w in warns)

    def test_compatible_preset_message_in_codec_warning(self):
        warns = check_compatibility(self._INFO)
        codec_warn = next(w for w in warns if w.category == "codec")
        assert "Compatible" in codec_warn.message

    def test_yuv420p_mentioned_in_pix_fmt_warning(self):
        warns = check_compatibility(self._INFO)
        pix_warn = next(w for w in warns if w.category == "pixel_format")
        assert "yuv420p" in pix_warn.message


# ---------------------------------------------------------------------------
# CompatibilityWarning dataclass
# ---------------------------------------------------------------------------

class TestCompatibilityWarningDataclass:

    def test_category_field_exists_with_default(self):
        w = CompatibilityWarning(message="test", severity="warn")
        assert w.category == ""

    def test_category_can_be_set(self):
        w = CompatibilityWarning(message="test", severity="warn", category="codec")
        assert w.category == "codec"

    def test_frozen(self):
        w = CompatibilityWarning(message="test", severity="warn", category="codec")
        with pytest.raises((AttributeError, TypeError)):
            w.category = "other"  # type: ignore[misc]
