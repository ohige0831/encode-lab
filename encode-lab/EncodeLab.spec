# -*- mode: python ; coding: utf-8 -*-
# EncodeLab v1 — PyInstaller spec
#
# Build from the encode-lab/ directory:
#   pyinstaller --noconfirm --clean EncodeLab.spec
#
# Output: dist/EncodeLab/EncodeLab.exe  (one-folder layout)

import os

# Resolve paths relative to this spec file so the spec works regardless of
# the working directory from which pyinstaller is invoked.
_here = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(_here, "main.py")],
    pathex=[_here],          # lets PyInstaller find the ui/ and logic/ packages
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EncodeLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # GUI-only; no terminal window
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,               # replace with an .ico path when an icon is ready
)

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
