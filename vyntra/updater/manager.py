"""
Core UpdateManager orchestrator for Vyntra.
Coordinates GitHub Releases API queries, non-blocking background checks,
state transitions, download verification, and platform installation handoff.
"""

from enum import Enum
import json
from pathlib import Path
import threading
from typing import Callable, Dict, List, Optional
import requests

from vyntra import __version__
from vyntra.updater.constants import (
    CHECKSUM_FILE_NAMES,
    DEFAULT_CHANNEL,
    LATEST_RELEASE_API_URL,
    NETWORK_CONNECT_TIMEOUT,
    NETWORK_READ_TIMEOUT,
    USER_AGENT_TEMPLATE,
)
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
    select_platform_asset,
)
from vyntra.updater.version_utils import is_newer, normalize_tag
from vyntra.utils.logger import logger


class UpdateState(str, Enum):
    IDLE = "idle"
    CHECKING = "checking"
    AVAILABLE = "available"
    UP_TO_DATE = "up_to_date"
    NO_COMPATIBLE_ASSET = "no_compatible_asset"
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

    def __init__(self):
        self._state = UpdateState.IDLE
        self._check_lock = threading.Lock()
        self._update_lock = threading.Lock()
        self._listeners: List[Callable[[UpdateCheckResult], None]] = []
        self._downloader = UpdateDownloadManager()

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
        """Worker thread executing HTTP request against GitHub Releases."""
        if not self._check_lock.acquire(blocking=False):
            logger.debug("[Updater] Update check already in progress. Ignoring duplicate request.")
            return

        self._state = UpdateState.CHECKING
        current_version = __version__
        result: Optional[UpdateCheckResult] = None

        try:
            logger.info("[Updater] Checking GitHub Releases for updates (current: v%s)...", current_version)
            headers = {
                "User-Agent": USER_AGENT_TEMPLATE.format(version=current_version),
                "Accept": "application/vnd.github.v3+json",
            }

            resp = requests.get(
                LATEST_RELEASE_API_URL,
                headers=headers,
                timeout=(NETWORK_CONNECT_TIMEOUT, NETWORK_READ_TIMEOUT),
            )

            if resp.status_code == 404:
                # No releases published yet on the repository
                logger.info("[Updater] No published releases found on repository.")
                result = UpdateCheckResult(
                    status="up_to_date",
                    current_version=current_version,
                )
                self._state = UpdateState.UP_TO_DATE
            elif resp.status_code != 200:
                err_msg = f"GitHub API returned HTTP {resp.status_code}"
                logger.warning("[Updater] %s", err_msg)
                result = UpdateCheckResult(
                    status="error",
                    current_version=current_version,
                    error_message=err_msg,
                )
                self._state = UpdateState.ERROR
            else:
                release_data = resp.json()
                result = self._evaluate_release(release_data, current_version)

        except requests.exceptions.Timeout:
            msg = "Network connection timed out"
            logger.warning("[Updater] Update check failed: %s", msg)
            result = UpdateCheckResult(status="error", current_version=current_version, error_message=msg)
            self._state = UpdateState.ERROR

        except requests.exceptions.ConnectionError:
            msg = "Network unavailable"
            logger.info("[Updater] Update check failed: %s", msg)
            result = UpdateCheckResult(status="error", current_version=current_version, error_message=msg)
            self._state = UpdateState.ERROR

        except Exception as e:
            logger.warning("[Updater] Unexpected error checking for updates: %s", e)
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

    def _evaluate_release(self, data: Dict, current_version: str) -> UpdateCheckResult:
        """Parses GitHub release JSON and compares against current installed version."""
        tag_name = data.get("tag_name", "")
        release_version = normalize_tag(tag_name)
        is_draft = data.get("draft", False)
        is_prerelease = data.get("prerelease", False)

        # Ignore draft releases or unreleased tags
        if is_draft or (is_prerelease and DEFAULT_CHANNEL == "stable"):
            logger.info("[Updater] Latest release tag %s is draft or prerelease. Ignoring for stable channel.", tag_name)
            self._state = UpdateState.UP_TO_DATE
            return UpdateCheckResult(
                status="up_to_date",
                current_version=current_version,
            )

        # Parse attached release assets
        raw_assets = data.get("assets", [])
        assets: List[ReleaseAsset] = []
        checksum_url: Optional[str] = None

        for a in raw_assets:
            name = a.get("name", "")
            download_url = a.get("browser_download_url", "")
            size = a.get("size", 0)
            content_type = a.get("content_type", "")
            digest = a.get("digest")

            # Check if this asset is a SHA-256 checksums manifest
            if any(name.lower() == cfn.lower() for cfn in CHECKSUM_FILE_NAMES):
                checksum_url = download_url

            assets.append(
                ReleaseAsset(
                    name=name,
                    download_url=download_url,
                    size=size,
                    sha256=digest,
                    content_type=content_type,
                )
            )

        # Parse checksum file if present
        checksums_map: Dict[str, str] = {}
        if checksum_url:
            checksums_map = self._fetch_checksums_map(checksum_url)
            for asset in assets:
                if asset.name in checksums_map:
                    asset.sha256 = checksums_map[asset.name]

        release_info = ReleaseInfo(
            version=release_version,
            tag=tag_name,
            name=data.get("name") or tag_name,
            release_notes=data.get("body") or "No release notes provided.",
            published_at=data.get("published_at", ""),
            is_draft=is_draft,
            is_prerelease=is_prerelease,
            assets=assets,
            checksums=checksums_map,
            html_url=data.get("html_url", ""),
        )

        # Check semantic version precedence
        if is_newer(release_version, current_version):
            target_asset = select_platform_asset(assets)
            if target_asset:
                logger.info(
                    "[Updater] New update available: v%s (target asset: %s, size: %.1f MB)",
                    release_version,
                    target_asset.name,
                    target_asset.size_mb,
                )
                self._state = UpdateState.AVAILABLE
                return UpdateCheckResult(
                    status="available",
                    current_version=current_version,
                    latest_release=release_info,
                    target_asset=target_asset,
                )
            else:
                logger.warning("[Updater] New version v%s available, but no compatible asset found for host platform.", release_version)
                self._state = UpdateState.NO_COMPATIBLE_ASSET
                return UpdateCheckResult(
                    status="no_asset",
                    current_version=current_version,
                    latest_release=release_info,
                    error_message=f"Version v{release_version} is available, but no compatible package was found for your operating system.",
                )
        else:
            logger.info("[Updater] Vyntra is up to date (current: v%s, latest: v%s).", current_version, release_version)
            self._state = UpdateState.UP_TO_DATE
            return UpdateCheckResult(
                status="up_to_date",
                current_version=current_version,
                latest_release=release_info,
            )

    def _fetch_checksums_map(self, url: str) -> Dict[str, str]:
        """Downloads and parses SHA256SUMS.txt format into {filename: sha256}."""
        mapping = {}
        try:
            resp = requests.get(url, timeout=(NETWORK_CONNECT_TIMEOUT, NETWORK_READ_TIMEOUT))
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        h = parts[0].strip().lower()
                        fn = parts[-1].strip().lstrip("*")
                        mapping[fn] = h
        except Exception as e:
            logger.warning("[Updater] Could not fetch checksums from %s: %s", url, e)
        return mapping

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
            # 1. Download and cryptographic verification
            staged_path = self._downloader.download_asset(
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
        self._downloader.cancel()
        self._state = UpdateState.IDLE


# Global singleton instance
update_manager = UpdateManager()
