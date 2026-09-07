# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification file for Vyntra.
Packages the desktop application into a standalone Windows executable.
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Root project directory
project_dir = os.path.abspath(SPECPATH)

# Base datas and hidden imports
datas = [
    (os.path.join(project_dir, 'credentials.json'), '.'),
    (os.path.join(project_dir, 'assets', 'icon.ico'), 'assets'),
    (os.path.join(project_dir, 'assets', 'icon.png'), 'assets'),
]
binaries = []
hiddenimports = [
    'keyring.backends.Windows',
    'keyring.backends.Windows.WinVaultKeyring',
    'PIL._tkinter_finder',
    'bottle',
]

# Explicitly collect complete packages with assets, DLLs, and submodules
packages_to_collect = [
    'customtkinter',
    'webview',
    'clr_loader',
    'pythonnet',
    'yt_dlp',
    'keyring',
]

for pkg in packages_to_collect:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas.extend(pkg_datas)
    binaries.extend(pkg_binaries)
    hiddenimports.extend(pkg_hiddenimports)

a = Analysis(
    [os.path.join(project_dir, 'run.py')],
    pathex=[project_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'unittest',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Vyntra',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_dir, 'assets', 'icon.ico'),
)
