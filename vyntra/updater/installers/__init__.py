"""
Platform installer factory for Vyntra updater.
"""

import sys
from typing import Optional

from vyntra.updater.installers.base import BaseInstaller
from vyntra.updater.installers.macos_installer import MacOSInstaller
from vyntra.updater.installers.windows_installer import WindowsInstaller


def get_platform_installer() -> Optional[BaseInstaller]:
    """Returns the appropriate installer for the current host operating system."""
    if sys.platform.startswith("win"):
        return WindowsInstaller()
    elif sys.platform == "darwin":
        return MacOSInstaller()
    return None


__all__ = ["BaseInstaller", "WindowsInstaller", "MacOSInstaller", "get_platform_installer"]
