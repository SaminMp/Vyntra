"""
Vyntra Update Service Provider.
Communicates with the server-side Vyntra Update Service over HTTPS,
allowing clients to discover releases and stream verified assets without
exposing or requiring any private repository credentials.
"""

import os
from pathlib import Path
import threading
from typing import Callable, Optional
import requests

from vyntra.updater.constants import (
    DEFAULT_UPDATE_SERVICE_URL,
    ENV_UPDATE_SERVICE_URL_VAR,
    NETWORK_CONNECT_TIMEOUT,
    NETWORK_READ_TIMEOUT,
    USER_AGENT_TEMPLATE,
)
from vyntra.updater.download_manager import UpdateDownloadManager
from vyntra.updater.models import (
    DownloadProgress,
    ReleaseAsset,
    ReleaseInfo,
    UpdateCheckResult,
)
from vyntra.updater.platform_detector import get_current_arch, get_current_platform
from vyntra.updater.providers.base import BaseUpdateProvider
from vyntra.utils.logger import logger


class VyntraUpdateServiceProvider(BaseUpdateProvider):
    """
    Client update provider that interfaces with the dedicated Vyntra Update Service.
    Preserves private repository security by keeping all GitHub credentials on the server.
    """

    def __init__(
        self,
        service_url: Optional[str] = None,
        downloader: Optional[UpdateDownloadManager] = None,
    ):
        self.service_url = (
            service_url
            or os.environ.get(ENV_UPDATE_SERVICE_URL_VAR, "").strip()
            or DEFAULT_UPDATE_SERVICE_URL
        ).rstrip("/")
        self.downloader = downloader or UpdateDownloadManager()

    def check_for_updates(self, current_version: str) -> UpdateCheckResult:
        """
        Queries the Vyntra Update Service for the latest published release.
        Requires zero authentication tokens on the client.
        """
        host_platform = get_current_platform()
        host_arch = get_current_arch()
        target_platform = f"{host_platform}-{host_arch}"

        endpoint = f"{self.service_url}/api/v1/updates/latest"
        params = {
            "platform": target_platform,
            "current_version": current_version,
        }
        headers = {
            "User-Agent": USER_AGENT_TEMPLATE.format(version=current_version),
            "Accept": "application/json",
        }

        try:
            logger.info(
                "[Updater] Checking for updates via %s (platform: %s, current: v%s)...",
                self.service_url,
                target_platform,
                current_version,
            )
            resp = requests.get(
                endpoint,
                params=params,
                headers=headers,
                timeout=(NETWORK_CONNECT_TIMEOUT, NETWORK_READ_TIMEOUT),
            )

            if resp.status_code == 404:
                logger.debug("[Updater] Update service reports no updates found.")
                return UpdateCheckResult(status="up_to_date", current_version=current_version)

            if resp.status_code != 200:
                logger.debug("[Updater] Update service returned HTTP %s", resp.status_code)
                return UpdateCheckResult(
                    status="up_to_date",
                    current_version=current_version,
                    error_message=f"Update service status HTTP {resp.status_code}",
                )

            data = resp.json()
            is_available = data.get("update_available", False)
            remote_version = data.get("version", "").lstrip("v")

            if is_available and remote_version:
                asset_name = data.get("asset_name", f"Vyntra-{target_platform}")
                download_url = data.get("download_url", "")
                sha256 = data.get("sha256")
                size = data.get("size", 0)
                notes = data.get("release_notes", "No release notes provided.")

                target_asset = ReleaseAsset(
                    name=asset_name,
                    download_url=download_url,
                    size=size,
                    sha256=sha256,
                )

                release_info = ReleaseInfo(
                    version=remote_version,
                    tag=f"v{remote_version}",
                    name=data.get("name") or f"Vyntra v{remote_version}",
                    release_notes=notes,
                    published_at=data.get("published_at", ""),
                    assets=[target_asset],
                )

                logger.info(
                    "[Updater] New release discovered: v%s (target asset: %s, size: %.1f MB)",
                    remote_version,
                    target_asset.name,
                    target_asset.size_mb,
                )
                return UpdateCheckResult(
                    status="available",
                    current_version=current_version,
                    latest_release=release_info,
                    target_asset=target_asset,
                )

            logger.debug("[Updater] Vyntra is up to date (current: v%s).", current_version)
            return UpdateCheckResult(status="up_to_date", current_version=current_version)

        except requests.exceptions.RequestException as e:
            logger.debug("[Updater] Update service unreachable (%s). Continuing offline.", e)
            return UpdateCheckResult(status="up_to_date", current_version=current_version)

        except Exception as e:
            logger.debug("[Updater] Error checking updates: %s", e)
            return UpdateCheckResult(status="up_to_date", current_version=current_version)

    def download_asset(
        self,
        asset: ReleaseAsset,
        expected_sha256: Optional[str] = None,
        on_progress: Optional[Callable[[DownloadProgress], None]] = None,
        cancel_flag: Optional[threading.Event] = None,
    ) -> Path:
        """
        Streams release asset securely from the update service and validates SHA-256.
        """
        return self.downloader.download_asset(
            asset=asset,
            expected_sha256=expected_sha256 or asset.sha256,
            on_progress=on_progress,
        )
