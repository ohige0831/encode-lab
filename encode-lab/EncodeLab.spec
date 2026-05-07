# -*- mode: python ; coding: utf-8 -*-
# EncodeLab — PyInstaller spec
#
# Build (run from encode-lab/):
#   pyinstaller --noconfirm --clean EncodeLab.spec
#
# Preferred flow — use the build script which also handles ffmpeg:
#   ..\scripts\build_exe.ps1
#   ..\scripts\build_exe.ps1 -Clean          # wipe build/ and dist/ first
#   ..\scripts\build_exe.ps1 -SkipFfmpeg     # skip ffmpeg copy step
#
# Output layout:
#   dist/EncodeLab/
#     EncodeLab.exe
#     ffmpeg/            ← ffmpeg.exe + ffprobe.exe (copied by build script)
#     _internal/         ← Python runtime + PySide6 (managed by PyInstaller)
#
# NOTE: ffmpeg/ must sit next to EncodeLab.exe (not inside _internal/).
#       main.py:_prepend_bundled_ffmpeg() prepends this path to PATH at startup.
#       The build script copies from vendor/ffmpeg/ or from the system PATH.

import os

# Resolve all paths relative to the spec file so builds work regardless of
# the working directory from which pyinstaller is invoked.
_here = os.path.dirname(os.path.abspath(SPEC))

# ---------------------------------------------------------------------------
# Analysis — collect sources and dependencies
# ---------------------------------------------------------------------------

a = Analysis(
    [os.path.join(_here, "main.py")],

    # Allow PyInstaller to find the ui/ and logic/ packages without installing
    # them as packages — they live directly in encode-lab/.
    pathex=[_here],

    binaries=[],

    # No data files required: ui/ and logic/ are pure Python, ffprobe is
    # called as a subprocess (not a bundled data file), and ffmpeg/ is placed
    # next to the exe by the build script (see layout above).
    datas=[],

    # PySide6 modules used directly; listed here as a safety net in case
    # PyInstaller's auto-analysis misses them in future versions.
    hiddenimports=[
        "PySide6.QtWidgets",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtPrintSupport",  # pulled in transitively by QtWidgets
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],

    # Exclude heavy PySide6 subsystems that EncodeLab never imports.
    # This reduces the bundle by several hundred MB.
    excludes=[
        # Web engine stack
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        # 3-D / charts / data visualisation
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DAnimation",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        # QML / Quick
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtQuickControls2",
        # Multimedia — we use ffmpeg subprocess, not Qt media APIs
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        # Miscellaneous subsystems not used
        "PySide6.QtNetwork",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtSerialPort",
        "PySide6.QtSensors",
        "PySide6.QtLocation",
        "PySide6.QtPositioning",
        "PySide6.QtRemoteObjects",
        "PySide6.QtStateMachine",
    ],

    noarchive=False,
)

# ---------------------------------------------------------------------------
# PYZ — compressed bytecode archive
# ---------------------------------------------------------------------------

pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
# EXE — the launcher executable
# ---------------------------------------------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # one-folder mode: binaries collected separately
    name="EncodeLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # GUI only — no terminal window on Windows
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="assets/icon.ico",  # uncomment and provide a path when ready
    icon=None,
    version=None,            # version_file="version_info.txt" when ready
)

# ---------------------------------------------------------------------------
# COLLECT — assemble the one-folder distribution in dist/EncodeLab/
# ---------------------------------------------------------------------------

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="EncodeLab",
)
