"""
Abstract base class defining the UpdateProvider interface for Vyntra.
Allows swapping update backends (Private GitHub Releases, Proxy Service, etc.)
without modifying UI or application lifecycle components.
"""

from abc import ABC, abstractmethod
from pathlib import Path
import threading
from typing import Callable, Optional

from vyntra.updater.models import DownloadProgress, ReleaseAsset, UpdateCheckResult


class BaseUpdateProvider(ABC):
    """Interface for update discovery and asset retrieval providers."""

    @abstractmethod
    def check_for_updates(self, current_version: str) -> UpdateCheckResult:
        """
        Queries release metadata source and determines if a newer release is available.
        """
        pass

    @abstractmethod
    def download_asset(
        self,
        asset: ReleaseAsset,
        expected_sha256: Optional[str] = None,
        on_progress: Optional[Callable[[DownloadProgress], None]] = None,
        cancel_flag: Optional[threading.Event] = None,
    ) -> Path:
        """
        Downloads a release asset to staging, verifies its cryptographic integrity,
        and returns the local Path to the verified binary file.
        """
        pass
