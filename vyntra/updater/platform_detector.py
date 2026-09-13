"""
Platform, architecture, and environment detection utilities for Vyntra updater.
Determines running runtime (frozen binary vs source), resolves application
install path, and selects the matching platform release asset.
"""

from pathlib import Path
import platform
import sys
from typing import List, Optional

from vyntra.updater.constants import (
    ARCH_ARM64,
    ARCH_X64,
    PLATFORM_MACOS,
    PLATFORM_WINDOWS,
)
from vyntra.updater.models import ReleaseAsset


def get_current_platform() -> str:
    """
    Returns normalized platform identifier:
    - 'windows' for Windows
    - 'darwin' for macOS
    - other sys.platform values for Linux/Unix
    """
    if sys.platform.startswith("win"):
        return PLATFORM_WINDOWS
    elif sys.platform == "darwin":
        return PLATFORM_MACOS
    return sys.platform


def get_current_arch() -> str:
    """
    Returns normalized CPU architecture identifier:
    - 'x64' for x86_64 / AMD64
    - 'arm64' for ARM64 / Apple Silicon
    """
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64", "x64"):
        return ARCH_X64
    elif machine in ("arm64", "aarch64"):
        return ARCH_ARM64
    return machine


def is_frozen() -> bool:
    """
    Returns True if running as a standalone compiled application
    packaged by PyInstaller; False if running from source code.
    """
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_installed_binary_path() -> Path:
    """
    Returns the Path to the installed application binary or bundle:
    - Windows: Path to running Vyntra.exe
    - macOS: Path to the enclosing Vyntra.app bundle directory
    - Development: Path to current sys.executable
    """
    exec_path = Path(sys.executable).resolve()

    if sys.platform == "darwin":
        # On macOS, if running inside /Applications/Vyntra.app/Contents/MacOS/Vyntra,
        # find the enclosing .app bundle root
        for parent in exec_path.parents:
            if parent.name.endswith(".app"):
                return parent

    return exec_path


def select_platform_asset(assets: List[ReleaseAsset]) -> Optional[ReleaseAsset]:
    """
    Selects the most suitable ReleaseAsset matching the host OS and architecture.
    Returns None if no compatible asset is available.
    """
    current_os = get_current_platform()
    current_arch = get_current_arch()

    # Filter out checksum files
    bin_assets = [
        a for a in assets
        if not a.name.endswith(".txt") and not a.name.endswith(".sha256") and not a.name.endswith(".md5")
    ]

    if current_os == PLATFORM_WINDOWS:
        # Preferred patterns for Windows
        # 1. Architecture specific: Vyntra-Windows-x64.exe
        # 2. General windows: Vyntra-Windows.exe, Vyntra.exe
        for a in bin_assets:
            nl = a.name.lower()
            if (nl.endswith(".exe") or nl.endswith(".zip")) and "windows" in nl and current_arch in nl:
                return a

        for a in bin_assets:
            nl = a.name.lower()
            if (nl.endswith(".exe") or nl.endswith(".zip")) and "windows" in nl:
                return a

        for a in bin_assets:
            nl = a.name.lower()
            if nl.endswith(".exe") and "vyntra" in nl:
                return a

    elif current_os == PLATFORM_MACOS:
        # Preferred patterns for macOS:
        # 1. dmg matching architecture: Vyntra-macOS-arm64.dmg / Vyntra-macOS-x64.dmg
        # 2. dmg general: Vyntra-macOS.dmg / Vyntra.dmg
        # 3. portable zip fallback: Vyntra-macOS-Portable.zip
        for a in bin_assets:
            nl = a.name.lower()
            if nl.endswith(".dmg"):
                if current_arch == ARCH_ARM64 and ("arm64" in nl or "apple-silicon" in nl or "m1" in nl):
                    return a
                elif current_arch == ARCH_X64 and ("x64" in nl or "intel" in nl or "x86_64" in nl):
                    return a

        # Universal or default DMG
        for a in bin_assets:
            nl = a.name.lower()
            if nl.endswith(".dmg") and ("macos" in nl or "vyntra" in nl):
                return a

        # Fallback to portable zip if no DMG present
        for a in bin_assets:
            nl = a.name.lower()
            if nl.endswith(".zip") and "macos" in nl:
                return a

    return None
