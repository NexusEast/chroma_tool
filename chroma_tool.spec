# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Chroma Tool GUI.

Build with:
    pyinstaller --noconfirm chroma_tool.spec

On Windows / Linux this outputs a single windowed executable at
``dist/chroma_tool`` (``.exe`` on Windows).  On macOS it additionally
wraps that binary in a double-clickable ``dist/Chroma Tool.app`` bundle.
Per-user settings and profiles are written at runtime to the user's
config directory, so nothing else needs to ship alongside the binary.
"""
import sys
from pathlib import Path

HERE = Path(SPECPATH).resolve()

APP_VERSION = "2.1.1"

# Optional drag-and-drop support.  tkinterdnd2 ships native tkdnd Tcl
# binaries that must be collected explicitly; if the package isn't
# installed we simply build without drag-and-drop (the GUI falls back).
try:
    from PyInstaller.utils.hooks import collect_all

    _dnd_datas, _dnd_binaries, _dnd_hiddenimports = collect_all('tkinterdnd2')
except Exception:
    _dnd_datas, _dnd_binaries, _dnd_hiddenimports = [], [], []


a = Analysis(
    ['gui.py'],
    pathex=[str(HERE)],
    binaries=_dnd_binaries,
    datas=_dnd_datas,
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
    ] + _dnd_hiddenimports,
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

# On macOS wrap the binary in a proper .app bundle so it can be launched
# by double-click (a bare Unix executable would open a Terminal instead).
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='Chroma Tool.app',
        icon=None,
        bundle_identifier='com.nexuseast.chromatool',
        version=APP_VERSION,
        info_plist={
            'NSHighResolutionCapable': True,
            'CFBundleShortVersionString': APP_VERSION,
            'CFBundleVersion': APP_VERSION,
            'NSRequiresAquaSystemAppearance': False,
        },
    )
