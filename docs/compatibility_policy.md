# Output Compatibility Policy

## Goal

EncodeLab targets maximum playback compatibility: the output must open correctly in
Discord, PowerPoint, QuickTime (macOS/iOS), Windows Media Player, modern browsers,
and SNS upload pipelines — without requiring the viewer to install codecs.

---

## Why H.264 / MP4

H.264 (AVC) inside an MP4 container is the lowest common denominator for video
interoperability as of 2025. It is hardware-decoded on every platform released since
~2010. Alternatives:

| Format | Problem |
|--------|---------|
| H.265 / HEVC | Not decoded by default on Windows; Discord/browsers inconsistent |
| VP9 / AV1 | No hardware decode on older machines; PowerPoint does not support |
| ProRes | macOS/Final Cut only; 10× larger than H.264 at equivalent quality |
| Rawvideo / AVI | Uncompressed or lossless; ~472 Mbps; no streaming; not embeddable |

---

## Why `-profile:v high -level 4.1`

- **High profile**: Enables CABAC entropy coding and 8×8 DCT, improving quality at equal bitrate over Baseline/Main. Supported by every H.264 decoder since ~2010.
- **Level 4.1**: Covers up to 1920×1080@60fps. Understood by all hardware decoders from 2010 onward, including older Apple TV, PlayStation 3, and Android devices.

Without explicit profile/level, ffmpeg defaults may produce a stream that software-decodes fine but fails in QuickTime or is rejected by PowerPoint's media engine.

---

## Why `-pix_fmt yuv420p`

Research cameras and screen recorders often output:

| Source format | Problem |
|---------------|---------|
| `bgr24` (rawvideo) | RGB — QuickTime and most HW decoders do not support |
| `yuv444p` | 4:4:4 chroma — not in H.264 Baseline/Main/High@4.1 spec |
| `yuv422p` | 4:2:2 chroma — H.264 High 4:2:2 profile, not universally decoded |
| `yuv420p10le` | 10-bit — requires HEVC or H.264 High 10 profile; broken in QuickTime |

`yuv420p` (8-bit 4:2:0) is the mandatory pixel format for H.264 High@4.1. It is
universally decoded and is what every streaming platform re-encodes to anyway.

---

## Why `-fps_mode cfr` (Constant Frame Rate)

Variable Frame Rate (VFR) sources cause:

- **PowerPoint**: Audio/video desync after the first keyframe skip
- **Discord**: Stuttering playback; preview thumbnail generation failure
- **Older Windows Media Player**: Playback hangs

Research cameras recording at a nominal 15 fps but with dropped frames produce VFR
output. `-fps_mode cfr` inserts duplicate frames to enforce a constant frame rate.

> **ffmpeg 5.0+ only**: The `-fps_mode` flag was introduced in ffmpeg 5.0. Versions
> 4.x require `-vsync cfr` instead. Version detection is a planned future addition.

---

## Why `-movflags +faststart`

MP4 files store their index (moov atom) at the end by default. `-faststart` moves it
to the beginning, enabling:

- Progressive streaming in browsers (video plays before full download)
- Discord inline preview generation
- Faster seek in media players

Without this flag, Discord often shows a grey thumbnail and PowerPoint may refuse to
embed the file.

---

## Why `-vf scale=trunc(iw/2)*2:trunc(ih/2)*2`

H.264 yuv420p requires even width and height. Sources with odd dimensions (e.g.,
1279×1023 from some capture cards) cause ffmpeg to error with:

```
width not divisible by 2 (1279x1023)
```

The scale filter rounds each dimension down to the nearest even number. The visual
difference (at most 1 pixel) is imperceptible.

---

## Why `-an` for audio-less sources

If ffprobe reports no audio stream and the conversion command includes `-acodec aac`,
ffmpeg exits with:

```
Output file does not contain any stream
```

EncodeLab detects `has_audio_stream = False` via ffprobe and automatically appends
`-an`, suppressing audio processing entirely.

---

## Rawvideo / bgr24 / AVI — Why Not for Sharing

Raw AVI files from research cameras are unsuitable for sharing because:

| Property | Value | Problem |
|----------|-------|---------|
| Codec | rawvideo | Uncompressed — no hardware decoder in consumer software |
| Pixel format | bgr24 | RGB byte order — unsupported by H.264/HEVC decoders |
| Container | AVI | No streaming support; moov-equivalent at end |
| Bitrate | ~472 Mbps | 22 GB per 6-minute recording |
| Audio | None | Silent source causes ffmpeg error without `-an` |

Converting to H.264 / yuv420p / CFR / MP4 / faststart reduces a 22 GB AVI to
~400–600 MB at CRF 23 while remaining frame-accurate for analysis.

---

## Compatible Preset — Full ffmpeg Command

Generated for a rawvideo bgr24 1280×1024 15fps silent AVI:

```
ffmpeg -y -i input.avi
  -vcodec libx264
  -profile:v high
  -level 4.1
  -pix_fmt yuv420p
  -crf 23
  -preset medium
  -vf scale=trunc(iw/2)*2:trunc(ih/2)*2
  -fps_mode cfr
  -an
  -movflags +faststart
  input_converted.mp4
```

---

## Future: Ultra Safe Preset

A planned preset for maximum legacy compatibility (Level 3.1, Baseline profile,
720p cap) targeting very old hardware decoders and mobile devices pre-2015:

| Flag | Value | Reason |
|------|-------|--------|
| `-profile:v baseline` | Baseline | PlayStation 3, early Android, feature phones |
| `-level 3.1` | 3.1 | 1280×720@30fps max |
| `-vf scale=-2:720` | Downscale to 720p | Stays within Level 3.1 limits |
| `-b:v 4M -maxrate 4M` | CBR cap | Streaming-safe bitrate |

This preset is not yet implemented. Implement by adding a new `PresetConfig` entry
to `logic/presets.py` — no other files need modification.
