"""
Abstract base class for platform-specific update installers.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseInstaller(ABC):
    """Interface for platform update installers."""

    @abstractmethod
    def install_and_restart(self, staged_file: Path, target_path: Path) -> None:
        """
        Launches the detached platform installer helper, terminates the
        currently running Vyntra instance, replaces the binary with rollback
        safeguards, and starts the new version.
        """
        pass
