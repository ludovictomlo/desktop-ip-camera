# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# Explicitly include python312.dll to avoid PyInstaller 6.x path-embedding bug
python_dll_name = f'python{sys.version_info.major}{sys.version_info.minor}.dll'
python_dll_path = os.path.join(os.path.dirname(sys.executable), python_dll_name)
extra_binaries = collect_dynamic_libs('cv2')
if os.path.exists(python_dll_path):
    extra_binaries.append((python_dll_path, '.'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=extra_binaries,
    datas=[
        ('config_default.json', '.'),
        ('app', 'app'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        'cv2',
        'numpy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# One-file build: everything packed into a single self-extracting exe
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TapoViewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
