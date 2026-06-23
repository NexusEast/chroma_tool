# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Chroma Tool GUI.

Build with:
    pyinstaller --noconfirm chroma_tool.spec

Outputs a single windowed EXE at ``dist/chroma_tool.exe``.  Per-user
settings and profiles are written at runtime to %APPDATA%\\ChromaTool,
so nothing else needs to ship alongside the EXE.
"""
from pathlib import Path

HERE = Path(SPECPATH).resolve()


a = Analysis(
    ['gui.py'],
    pathex=[str(HERE)],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Pull in every sibling module by name so PyInstaller bundles them
        # even if a future refactor adds a dynamic import.
        'batch',
        'i18n',
        'io_utils',
        'keying',
        'naming',
        'pipeline',
        'profiles',
        'settings',
        'shadows',
        'splitting',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim well-known scientific bloat that PyInstaller sometimes pulls
        # in via numpy/cv2 transitive deps.
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'pytest',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='chroma_tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
