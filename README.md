# EncodeLab

A lightweight Windows GUI video converter built on ffmpeg.

Drag-and-drop video files, choose a preset, and convert. Designed for researchers and power users who need high-compatibility output for Discord, PowerPoint, QuickTime, and browsers — without learning ffmpeg flags.

---

## Features

- Drag & drop input (single or multiple files)
- Preset-based conversion (Compatible, H.264 Fast, H.264 High Quality, ProRes)
- **Compatible preset** (recommended): H.264 High 4.1 / yuv420p / CFR / faststart — plays everywhere
- Compatibility warnings for rawvideo / bgr24 / odd-resolution sources
- Audio-aware conversion (no errors on silent research videos)
- Safe output: original files are never overwritten
- Self-contained `.exe` with bundled ffmpeg (no PATH dependency at runtime)

---

## Requirements

| Component | Version |
|-----------|---------|
| Windows   | 10 / 11 (64-bit) |
| Python    | 3.12 |
| ffmpeg    | 5.0+ (for `-fps_mode cfr`) |
| PySide6   | 6.6+ |
| PyInstaller | 6.0+ |
| pytest    | 8.0+ (dev/test only) |

---

## Quick Start (development)

```powershell
# 1. Clone the repository
git clone https://github.com/ohige0831/EncodeLab.git
cd EncodeLab

# 2. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run from source
cd encode-lab
python main.py
```

---

## Run Tests

From the project root (with `.venv` active):

```powershell
cd encode-lab
pytest tests/ -v
```

Expected: **84 passed**

---

## Build Distributable .exe

### 1. Place ffmpeg binaries (first time only)

The build script resolves Chocolatey shims automatically. If you have ffmpeg
installed via Chocolatey or on your PATH, the script finds the real binaries.

To use vendor-pinned binaries instead, copy them manually:

```
encode-lab\vendor\ffmpeg\ffmpeg.exe    (~83 MB)
encode-lab\vendor\ffmpeg\ffprobe.exe   (~83 MB)
```

Download from: https://www.gyan.dev/ffmpeg/builds/  
Recommended: `ffmpeg-release-essentials.zip` → extract `bin\ffmpeg.exe` and `bin\ffprobe.exe`.

### 2. Run the build script

```powershell
# Standard build (incremental)
.\scripts\build_exe.ps1

# Clean build (wipes build/ and dist/ first — recommended before release)
.\scripts\build_exe.ps1 -Clean

# Skip ffmpeg copy (if you will add binaries manually)
.\scripts\build_exe.ps1 -SkipFfmpeg
```

### 3. Output location

```
encode-lab\dist\EncodeLab\
  EncodeLab.exe          (~1.7 MB launcher)
  ffmpeg\
    ffmpeg.exe           (~83 MB)
    ffprobe.exe          (~83 MB)
  _internal\             (Python runtime + PySide6, managed by PyInstaller)
```

Run directly:

```powershell
.\encode-lab\dist\EncodeLab\EncodeLab.exe
```

### 4. Test without system ffmpeg on PATH

```powershell
$env:PATH = $env:PATH -replace [regex]::Escape((Split-Path (where.exe ffmpeg) -Parent)) + ';', ''
.\encode-lab\dist\EncodeLab\EncodeLab.exe
```

### 5. Package for distribution

```powershell
Compress-Archive -Path '.\encode-lab\dist\EncodeLab\*' -DestinationPath 'EncodeLab.zip'
```

---

## ffmpeg Handling Policy

| Scenario | ffmpeg source |
|----------|--------------|
| Running from source | System PATH |
| Running built `.exe` | `dist\EncodeLab\ffmpeg\` (bundled) |
| Building the `.exe` | `vendor\ffmpeg\` → Chocolatey lib → system PATH (in priority order) |

**Shim detection**: `build_exe.ps1` detects Chocolatey shims (< 5 MB) and
automatically resolves the real binary from `C:\ProgramData\chocolatey\lib\ffmpeg\`.
A warning is printed if only a shim can be found.

ffmpeg binaries are **not committed to git** (platform-specific, ~83 MB each).

---

## Presets

| Preset | Codec | Profile | Pixel fmt | CFR | Notes |
|--------|-------|---------|-----------|-----|-------|
| **Compatible** ⭐ | H.264 | High 4.1 | yuv420p | Yes | Discord, PowerPoint, QuickTime, browsers |
| H.264 Fast | H.264 | High 4.1 | yuv420p | No  | Quick conversion, slightly larger |
| H.264 High Quality | H.264 | High 4.1 | yuv420p | No  | CRF 18, high detail retention |
| ProRes 422 | ProRes | 422 (profile 2) | yuv422p10le | No | Editing workflow |

See [docs/compatibility_policy.md](docs/compatibility_policy.md) for why these settings were chosen.

---

## Architecture

```
encode-lab/
  main.py                  Entry point, ffmpeg PATH setup
  logic/
    presets.py             PresetConfig dataclass — single source of truth
    converter.py           ffmpeg command builder + ConversionJob
    ffprobe_reader.py      ffprobe wrapper → MediaInfo
    compatibility.py       Pure-logic compatibility checker (no Qt)
    worker.py              QThread-based conversion worker
    probe_worker.py        QThread-based ffprobe worker
    environment.py         Runtime environment checks
    size_estimator.py      Output size estimation
  ui/
    main_window.py         Main window orchestrator
    drop_zone.py           Drag & drop widget
    file_list.py           File queue table
    log_panel.py           Conversion log display
    advanced_panel.py      Advanced settings panel
  tests/
    conftest.py
    test_converter.py      Command generation tests
    test_compatibility.py  Warning detection tests
    test_ffprobe_reader.py MediaInfo parsing tests
  vendor/
    ffmpeg/
      .gitkeep             Instructions — binaries excluded from git
scripts/
  build_exe.ps1            PyInstaller build + ffmpeg copy + shim detection
docs/
  compatibility_policy.md  H.264 / yuv420p / CFR / faststart rationale
  build_windows.md         Windows build guide
```

**Key design rule**: `logic/` contains no Qt imports. `ui/` owns all Qt code.
`PresetConfig` is the single source of truth — all ffmpeg flags flow from it.

---

## Known Notes

- **ffmpeg 5.0+ required** for `-fps_mode cfr`. Older versions need `-vsync cfr` (not yet auto-detected).
- **Rawvideo / bgr24 sources** trigger compatibility warnings automatically. Use the Compatible preset.
- **Odd resolutions** are padded to even dimensions by the Compatible preset's `-vf scale=trunc(iw/2)*2:trunc(ih/2)*2`.
- **Audio-less sources**: `-an` is applied automatically when ffprobe detects no audio stream, preventing ffmpeg errors.
