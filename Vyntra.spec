# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification file for Vyntra (Cross-Platform).
Packages the desktop application into:
- Standalone Windows executable (.exe) on Windows
- Native Application Bundle (Vyntra.app) on macOS / Apple devices
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

block_cipher = None
is_darwin = sys.platform == "darwin"
is_windows = sys.platform == "win32"

# Root project directory
project_dir = os.path.abspath(SPECPATH)
try:
    sys.path.insert(0, project_dir)
    from vyntra import __version__ as app_version
except Exception:
    app_version = "1.1.3"

# Base datas and assets
datas = [
    (os.path.join(project_dir, 'credentials.json'), '.'),
    (os.path.join(project_dir, 'assets', 'icon.ico'), 'assets'),
    (os.path.join(project_dir, 'assets', 'icon.png'), 'assets'),
]

# Include Apple ICNS on macOS or if present
icns_path = os.path.join(project_dir, 'assets', 'icon.icns')
if os.path.isfile(icns_path):
    datas.append((icns_path, 'assets'))

binaries = []

# Core hidden imports across platforms
hiddenimports = [
    'PIL._tkinter_finder',
    'bottle',
    'sounddevice',
    'av',
    'numpy',
    'vyntra.platforms',
    'vyntra.platforms.base',
    'vyntra.platforms.registry',
    'vyntra.platforms.youtube',
    'vyntra.platforms.instagram',
    'vyntra.platforms.tiktok',
    'vyntra.platforms.spotify',
    'vyntra.ui.pages',
    'vyntra.ui.views.update_modal',
    'vyntra.updater',
    'vyntra.updater.constants',
    'vyntra.updater.version_utils',
    'vyntra.updater.models',
    'vyntra.updater.platform_detector',
    'vyntra.updater.download_manager',
    'vyntra.updater.installers',
    'vyntra.updater.installers.base',
    'vyntra.updater.installers.windows_installer',
    'vyntra.updater.installers.macos_installer',
    'vyntra.updater.manager',
    'curl_cffi',
    'curl_cffi.requests',
    '_cffi_backend',
    'brotli',
]

# Platform-specific keyring backends
if is_darwin:
    hiddenimports.extend([
        'keyring.backends.macOS',
        'keyring.backends.macOS.Keyring',
    ])
elif is_windows:
    hiddenimports.extend([
        'keyring.backends.Windows',
        'keyring.backends.Windows.WinVaultKeyring',
    ])

# Explicitly collect complete packages with assets, DLLs/dylibs, and submodules
packages_to_collect = [
    'customtkinter',
    'yt_dlp',
    'keyring',
    'av',
    '_sounddevice_data',
    'numpy',
    'curl_cffi',
    'brotli',
]

if is_windows:
    for win_pkg in ['clr_loader', 'pythonnet', 'webview']:
        try:
            import importlib.util
            if importlib.util.find_spec(win_pkg):
                packages_to_collect.append(win_pkg)
        except Exception:
            pass

for pkg in packages_to_collect:
    try:
        pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
        datas.extend(pkg_datas)
        binaries.extend(pkg_binaries)
        hiddenimports.extend(pkg_hiddenimports)
    except Exception as e:
        print(f"Note: collect_all skipped for {pkg}: {e}")

# Determine primary icon file
if is_darwin and os.path.isfile(icns_path):
    primary_icon = icns_path
else:
    primary_icon = os.path.join(project_dir, 'assets', 'icon.ico')

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
    argv_emulation=is_darwin,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=primary_icon,
)

# macOS Application Bundle (.app)
if is_darwin:
    app = BUNDLE(
        exe,
        name='Vyntra.app',
        icon=primary_icon,
        bundle_identifier='com.saminmp.vyntra',
        info_plist={
            'CFBundleDisplayName': 'Vyntra',
            'CFBundleName': 'Vyntra',
            'CFBundlePackageType': 'APPL',
            'CFBundleSignature': '????',
            'CFBundleShortVersionString': app_version,
            'CFBundleVersion': app_version,
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,
            'LSApplicationCategoryType': 'public.app-category.music',
            'NSHumanReadableCopyright': 'Copyright © 2026 Vyntra',
        },
    )
