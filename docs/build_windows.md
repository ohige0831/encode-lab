# Building EncodeLab on Windows

## Prerequisites

- Windows 10 / 11 (64-bit)
- Python 3.12 (from python.org or Microsoft Store)
- ffmpeg 5.0+ on PATH, or binaries in `encode-lab\vendor\ffmpeg\`

Install Python dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## ffmpeg Binaries

The build script accepts ffmpeg from three sources (in priority order):

1. **`encode-lab\vendor\ffmpeg\`** — version-pinned, reproducible builds  
2. **Chocolatey** — shims are auto-resolved to real binaries in `chocolatey\lib\ffmpeg\`  
3. **System PATH** — any ffmpeg on PATH

To pin a specific version, download from https://www.gyan.dev/ffmpeg/builds/ and copy:

```
encode-lab\vendor\ffmpeg\ffmpeg.exe
encode-lab\vendor\ffmpeg\ffprobe.exe
```

These files are gitignored. They will be copied into `dist\EncodeLab\ffmpeg\` at build time.

---

## Build Steps

```powershell
# From the project root, with .venv active:

# Run tests first
cd encode-lab
pytest tests/ -v
cd ..

# Build (clean recommended before release)
.\scripts\build_exe.ps1 -Clean
```

The script performs:
1. Environment validation (Python, PyInstaller)
2. Optional `build/` and `dist/` cleanup
3. PyInstaller one-folder build
4. ffmpeg / ffprobe copy with shim detection
5. Output verification

---

## Output Layout

```
encode-lab\dist\EncodeLab\
  EncodeLab.exe          Launcher (~1.7 MB)
  ffmpeg\
    ffmpeg.exe           ~83 MB
    ffprobe.exe          ~83 MB
  _internal\             Python 3.12 + PySide6 runtime (managed by PyInstaller)
```

Run:

```powershell
.\encode-lab\dist\EncodeLab\EncodeLab.exe
```

---

## PATH-Independent Test

Verify the bundled ffmpeg is used — not the system one:

```powershell
# Remove system ffmpeg from PATH temporarily
$env:PATH = $env:PATH -replace [regex]::Escape((Split-Path (where.exe ffmpeg) -Parent)) + ';', ''

# Launch — should work without system ffmpeg
.\encode-lab\dist\EncodeLab\EncodeLab.exe
```

The app prepends `dist\EncodeLab\ffmpeg\` to PATH at startup
(`main.py:_prepend_bundled_ffmpeg`), so no system install is needed at runtime.

---

## Distribution

Package the entire `dist\EncodeLab\` folder:

```powershell
Compress-Archive -Path '.\encode-lab\dist\EncodeLab\*' -DestinationPath 'EncodeLab.zip'
```

The zip is self-contained. Recipients unzip and run `EncodeLab.exe` — no Python, no ffmpeg install required.

---

## Shim Detection

Chocolatey installs a small shim (`~0.4 MB`) in `C:\ProgramData\chocolatey\bin\` that
points to the real binary. The build script detects binaries under 5 MB and resolves
the real path from `C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\`.

If resolution fails, the script prints a red warning and falls back to the shim.
In that case, the built package will only work on machines with Chocolatey installed.

To avoid this, copy real binaries to `vendor\ffmpeg\` as described above.
