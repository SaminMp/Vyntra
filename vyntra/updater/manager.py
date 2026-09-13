"""
Core UpdateManager orchestrator for Vyntra.
Coordinates GitHub Releases API queries, non-blocking background checks,
state transitions, download verification, and platform installation handoff.
"""

from enum import Enum
from pathlib import Path
import threading
from typing import Callable, List, Optional, Tuple

from vyntra import __version__
from vyntra.updater.download_manager import (
    UpdateDownloadError,
    UpdateDownloadManager,
    UpdateIntegrityError,
)
from vyntra.updater.installers import get_platform_installer
from vyntra.updater.models import (
    DownloadProgress,
    ReleaseAsset,
    ReleaseInfo,
    UpdateCheckResult,
)
from vyntra.updater.platform_detector import (
    get_installed_binary_path,
    is_frozen,
)
from vyntra.updater.providers.base import BaseUpdateProvider
from vyntra.updater.providers.github_provider import GitHubReleaseProvider
from vyntra.utils.logger import logger


class UpdateState(str, Enum):
    IDLE = "idle"
    CHECKING = "checking"
    AVAILABLE = "available"
    UP_TO_DATE = "up_to_date"
    NO_COMPATIBLE_ASSET = "no_compatible_asset"
    AUTH_REQUIRED = "auth_required"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    READY_TO_INSTALL = "ready_to_install"
    INSTALLING = "installing"
    ERROR = "error"


class UpdateManager:
    """
    Central orchestrator managing Vyntra's update lifecycle.
    Thread-safe and designed for non-blocking UI integration.
    """

    def __init__(
        self,
        provider: Optional[BaseUpdateProvider] = None,
    ):
        self._state = UpdateState.IDLE
        self._check_lock = threading.Lock()
        self._update_lock = threading.Lock()
        self._listeners: List[Callable[[UpdateCheckResult], None]] = []

        self.provider = provider or GitHubReleaseProvider()
        self._downloader = getattr(self.provider, "downloader", None) or UpdateDownloadManager()

        self._last_result: Optional[UpdateCheckResult] = None
        self._staged_asset_path: Optional[Path] = None

    @property
    def state(self) -> UpdateState:
        return self._state

    @property
    def last_result(self) -> Optional[UpdateCheckResult]:
        return self._last_result

    def add_listener(self, listener: Callable[[UpdateCheckResult], None]):
        """Registers a callback for update check result events."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[UpdateCheckResult], None]):
        """Unregisters an update callback."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify_listeners(self, result: UpdateCheckResult):
        for cb in list(self._listeners):
            try:
                cb(result)
            except Exception as e:
                logger.debug("[Updater] Listener callback error: %s", e)

    # -------------------------------------------------------------------------
    # 1. Update Check Lifecycle
    # -------------------------------------------------------------------------
    def check_for_updates(
        self,
        callback: Optional[Callable[[UpdateCheckResult], None]] = None,
        background: bool = True,
    ):
        """
        Initiates a non-blocking GitHub release check in a daemon worker thread.
        Guarantees that Vyntra startup is never delayed or blocked.
        """
        thread = threading.Thread(
            target=self._run_check_worker,
            args=(callback, background),
            name="Vyntra-UpdateCheck-Thread",
            daemon=True,
        )
        thread.start()

    def _run_check_worker(
        self,
        callback: Optional[Callable[[UpdateCheckResult], None]],
        background: bool,
    ):
        """Worker thread executing release check via configured UpdateProvider."""
        if not self._check_lock.acquire(blocking=False):
            logger.debug("[Updater] Update check already in progress. Ignoring duplicate request.")
            return

        self._state = UpdateState.CHECKING
        current_version = __version__
        result: Optional[UpdateCheckResult] = None

        try:
            result = self.provider.check_for_updates(current_version)

            if result.status == "available":
                self._state = UpdateState.AVAILABLE
            elif result.status == "up_to_date":
                self._state = UpdateState.UP_TO_DATE
            elif result.status == "auth_required":
                self._state = UpdateState.AUTH_REQUIRED
            elif result.status == "no_asset":
                self._state = UpdateState.NO_COMPATIBLE_ASSET
            else:
                self._state = UpdateState.ERROR

        except Exception as e:
            logger.warning("[Updater] Unexpected error running update check: %s", e)
            result = UpdateCheckResult(status="error", current_version=current_version, error_message=str(e))
            self._state = UpdateState.ERROR

        finally:
            self._last_result = result
            self._check_lock.release()

            if result:
                if callback:
                    try:
                        callback(result)
                    except Exception as e:
                        logger.debug("[Updater] Check callback exception: %s", e)
                self._notify_listeners(result)

    # -------------------------------------------------------------------------
    # 2. Download & Installation Lifecycle
    # -------------------------------------------------------------------------
    def download_and_install_update(
        self,
        on_progress: Optional[Callable[[DownloadProgress], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        """
        Triggers download of the target update asset followed by detached
        installation and application restart. Runs in a dedicated thread.
        """
        if not self._last_result or not self._last_result.target_asset:
            if on_error:
                on_error("No update is currently pending download.")
            return

        thread = threading.Thread(
            target=self._run_download_and_install_worker,
            args=(self._last_result.target_asset, on_progress, on_error),
            name="Vyntra-UpdateDownload-Thread",
            daemon=True,
        )
        thread.start()

    def _run_download_and_install_worker(
        self,
        asset: ReleaseAsset,
        on_progress: Optional[Callable[[DownloadProgress], None]],
        on_error: Optional[Callable[[str], None]],
    ):
        if not self._update_lock.acquire(blocking=False):
            logger.warning("[Updater] Download and install transaction already in progress.")
            return

        self._state = UpdateState.DOWNLOADING

        try:
            # 1. Download and cryptographic verification via provider
            staged_path = self.provider.download_asset(
                asset=asset,
                expected_sha256=asset.sha256,
                on_progress=on_progress,
            )
            self._staged_asset_path = staged_path
            self._state = UpdateState.READY_TO_INSTALL

            # 2. Check development vs production runtime
            if not is_frozen():
                logger.info("[Updater] Running in development environment (source mode). Binary replacement skipped.")
                if on_progress:
                    on_progress(
                        DownloadProgress(
                            downloaded_bytes=asset.size,
                            total_bytes=asset.size,
                            percent=100.0,
                            is_complete=True,
                            status_text="Verified! (Installation skipped in development source mode)",
                        )
                    )
                return

            # 3. Resolve installer and target binary
            installer = get_platform_installer()
            if not installer:
                raise RuntimeError("No update installer available for this operating system.")

            target_path = get_installed_binary_path()
            logger.info("[Updater] Launching platform installer: target=%s, staged=%s", target_path, staged_path)

            if on_progress:
                on_progress(
                    DownloadProgress(
                        downloaded_bytes=asset.size,
                        total_bytes=asset.size,
                        percent=100.0,
                        is_complete=True,
                        status_text="Installing update... Vyntra will restart automatically.",
                    )
                )

            self._state = UpdateState.INSTALLING
            installer.install_and_restart(staged_path, target_path)

        except UpdateIntegrityError as e:
            self._state = UpdateState.ERROR
            logger.error("[Updater] Update integrity verification failed: %s", e)
            if on_error:
                on_error(f"Integrity check failed: {e}")

        except UpdateDownloadError as e:
            self._state = UpdateState.ERROR
            logger.error("[Updater] Update download failed: %s", e)
            if on_error:
                on_error(f"Download failed: {e}")

        except Exception as e:
            self._state = UpdateState.ERROR
            logger.error("[Updater] Unexpected update error: %s", e, exc_info=True)
            if on_error:
                on_error(f"Update error: {e}")

        finally:
            self._update_lock.release()

    def cancel_download(self):
        """Cancels active download and cleans up staging file."""
        if hasattr(self.provider, "downloader") and self.provider.downloader:
            self.provider.downloader.cancel()
        elif self._downloader:
            self._downloader.cancel()
        self._state = UpdateState.IDLE


# Global singleton instance
update_manager = UpdateManager()
