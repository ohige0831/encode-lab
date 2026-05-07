"""Tests for ffprobe_reader._parse() — pure JSON parsing, no subprocess."""
import pytest

from logic.ffprobe_reader import MediaInfo, _parse

# ---------------------------------------------------------------------------
# Sample ffprobe JSON payloads
# ---------------------------------------------------------------------------

_RAW_VIDEO_JSON = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "rawvideo",
            "width": 1280,
            "height": 1024,
            "pix_fmt": "bgr24",
        }
    ],
    "format": {
        "duration": "375.6",
    },
}

_H264_WITH_AUDIO_JSON = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "pix_fmt": "yuv420p",
        },
        {
            "codec_type": "audio",
            "codec_name": "aac",
        },
    ],
    "format": {"duration": "60.0"},
}

_EMPTY_JSON: dict = {"streams": [], "format": {}}


# ---------------------------------------------------------------------------
# rawvideo source (matches the actual research files)
# ---------------------------------------------------------------------------

class TestParseRawvideo:

    def test_duration(self):
        info = _parse(_RAW_VIDEO_JSON)
        assert info.duration_sec == pytest.approx(375.6, rel=1e-3)

    def test_resolution(self):
        info = _parse(_RAW_VIDEO_JSON)
        assert info.width == 1280
        assert info.height == 1024

    def test_codec(self):
        info = _parse(_RAW_VIDEO_JSON)
        assert info.video_codec == "rawvideo"

    def test_pix_fmt(self):
        info = _parse(_RAW_VIDEO_JSON)
        assert info.pix_fmt == "bgr24"

    def test_no_audio_stream(self):
        info = _parse(_RAW_VIDEO_JSON)
        assert info.has_audio_stream is False

    def test_resolution_str_property(self):
        info = _parse(_RAW_VIDEO_JSON)
        assert info.resolution_str == "1280\xd71024"

    def test_duration_str_property(self):
        info = _parse(_RAW_VIDEO_JSON)
        assert info.duration_str == "6:15"

    def test_codec_str_property(self):
        info = _parse(_RAW_VIDEO_JSON)
        assert info.codec_str == "rawvideo"


# ---------------------------------------------------------------------------
# H.264 with audio
# ---------------------------------------------------------------------------

class TestParseH264WithAudio:

    def test_has_audio_stream(self):
        info = _parse(_H264_WITH_AUDIO_JSON)
        assert info.has_audio_stream is True

    def test_pix_fmt_yuv420p(self):
        info = _parse(_H264_WITH_AUDIO_JSON)
        assert info.pix_fmt == "yuv420p"

    def test_codec(self):
        info = _parse(_H264_WITH_AUDIO_JSON)
        assert info.video_codec == "h264"


# ---------------------------------------------------------------------------
# Edge cases / failure robustness
# ---------------------------------------------------------------------------

class TestParseEdgeCases:

    def test_empty_streams_returns_none_fields(self):
        info = _parse(_EMPTY_JSON)
        assert info.duration_sec is None
        assert info.width is None
        assert info.height is None
        assert info.video_codec is None
        assert info.pix_fmt is None
        assert info.has_audio_stream is False

    def test_missing_streams_key(self):
        info = _parse({"format": {"duration": "10.0"}})
        assert info.video_codec is None
        assert info.has_audio_stream is False

    def test_missing_format_key(self):
        info = _parse({"streams": []})
        assert info.duration_sec is None

    def test_duration_zero_returns_none(self):
        data = {"streams": [], "format": {"duration": "0"}}
        info = _parse(data)
        assert info.duration_sec is None

    def test_duration_negative_returns_none(self):
        data = {"streams": [], "format": {"duration": "-1.5"}}
        info = _parse(data)
        assert info.duration_sec is None

    def test_duration_non_numeric_returns_none(self):
        data = {"streams": [], "format": {"duration": "N/A"}}
        info = _parse(data)
        assert info.duration_sec is None

    def test_no_pix_fmt_in_stream(self):
        data = {
            "streams": [{"codec_type": "video", "codec_name": "h264",
                         "width": 1920, "height": 1080}],
            "format": {"duration": "10.0"},
        }
        info = _parse(data)
        assert info.pix_fmt is None

    def test_audio_only_stream(self):
        data = {
            "streams": [{"codec_type": "audio", "codec_name": "aac"}],
            "format": {"duration": "120.0"},
        }
        info = _parse(data)
        assert info.video_codec is None
        assert info.has_audio_stream is True

    def test_mediainfo_is_frozen(self):
        info = MediaInfo()
        with pytest.raises((AttributeError, TypeError)):
            info.video_codec = "h264"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MediaInfo formatted properties
# ---------------------------------------------------------------------------

class TestMediaInfoProperties:

    def test_duration_str_hours(self):
        info = MediaInfo(duration_sec=3723.0)  # 1h 2m 3s
        assert info.duration_str == "1:02:03"

    def test_duration_str_minutes(self):
        info = MediaInfo(duration_sec=247.0)  # 4m 7s
        assert info.duration_str == "4:07"

    def test_duration_str_none(self):
        assert MediaInfo().duration_str == "—"

    def test_resolution_str_none(self):
        assert MediaInfo().resolution_str == "—"

    def test_codec_str_none(self):
        assert MediaInfo().codec_str == "—"
