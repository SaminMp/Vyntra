"""
GitHub Release Provider for Vyntra updater.
Implements release metadata discovery from GitHub Releases API,
asset selection, and secure asset streaming for public and private repositories.
"""

from pathlib import Path
import threading
from typing import Callable, Dict, List, Optional
import requests

from vyntra.updater.auth_manager import UpdaterAuthManager, updater_auth_manager
from vyntra.updater.constants import (
    CHECKSUM_FILE_NAMES,
    DEFAULT_CHANNEL,
    GITHUB_OWNER,
    GITHUB_REPO,
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
from vyntra.updater.platform_detector import select_platform_asset
from vyntra.updater.providers.base import BaseUpdateProvider
from vyntra.updater.version_utils import is_newer, normalize_tag
from vyntra.utils.logger import logger


class GitHubReleaseProvider(BaseUpdateProvider):
    """
    Update provider communicating with GitHub Releases API.
    Supports official public repository releases without authentication,
    and authenticated private repository releases if a token is configured.
    """

    def __init__(
        self,
        owner: str = GITHUB_OWNER,
        repo: str = GITHUB_REPO,
        auth_mgr: Optional[UpdaterAuthManager] = None,
        downloader: Optional[UpdateDownloadManager] = None,
        require_auth: bool = False,
    ):
        self.owner = owner
        self.repo = repo
        self.auth_mgr = auth_mgr or updater_auth_manager
        self.downloader = downloader or UpdateDownloadManager()
        self.require_auth = require_auth

    @property
    def latest_release_url(self) -> str:
        return f"https://api.github.com/repos/{self.owner}/{self.repo}/releases/latest"

    def check_for_updates(self, current_version: str) -> UpdateCheckResult:
        """
        Queries GitHub Releases for the latest published release.
        If require_auth is True and no token is present, returns auth_required.
        Otherwise, performs a public GitHub API request (adding Authorization header if token exists).
        """
        token = self.auth_mgr.get_token() if self.auth_mgr else None
        if self.require_auth and not token:
            logger.info("[Updater] No update token configured. Private repository checks skipped.")
            return UpdateCheckResult(
                status="auth_required",
                current_version=current_version,
                auth_status="unauthenticated",
                error_message="Private repository update access not connected. Connect update access in Settings.",
            )

        headers = {
            "User-Agent": USER_AGENT_TEMPLATE.format(version=current_version),
            "Accept": "application/vnd.github.v3+json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token.strip()}"

        try:
            logger.info(
                "[Updater] Querying GitHub Releases for %s/%s (current: v%s)...",
                self.owner,
                self.repo,
                current_version,
            )
            resp = requests.get(
                self.latest_release_url,
                headers=headers,
                timeout=(NETWORK_CONNECT_TIMEOUT, NETWORK_READ_TIMEOUT),
            )

            if resp.status_code in (401, 403):
                if token:
                    err_msg = "GitHub update access token is invalid, expired, or lacking read permissions."
                    logger.warning("[Updater] %s (HTTP %s)", err_msg, resp.status_code)
                    return UpdateCheckResult(
                        status="auth_required",
                        current_version=current_version,
                        auth_status="invalid_token",
                        error_message=err_msg,
                    )
                else:
                    err_msg = f"GitHub API rate limit exceeded or access forbidden (HTTP {resp.status_code})."
                    logger.warning("[Updater] %s", err_msg)
                    return UpdateCheckResult(
                        status="error",
                        current_version=current_version,
                        auth_status="ok",
                        error_message=err_msg,
                    )

            elif resp.status_code == 404:
                if not token:
                    try:
                        repo_check = requests.get(
                            f"https://api.github.com/repos/{self.owner}/{self.repo}",
                            headers={"User-Agent": headers["User-Agent"], "Accept": "application/vnd.github.v3+json"},
                            timeout=(NETWORK_CONNECT_TIMEOUT, NETWORK_READ_TIMEOUT),
                        )
                        if repo_check.status_code == 404:
                            err_msg = (
                                f"Repository '{self.owner}/{self.repo}' is private. "
                                "Enter a GitHub access token in Settings to check for updates."
                            )
                            logger.info("[Updater] %s", err_msg)
                            return UpdateCheckResult(
                                status="auth_required",
                                current_version=current_version,
                                auth_status="unauthenticated",
                                error_message=err_msg,
                            )
                    except Exception as e:
                        logger.debug("[Updater] Repo visibility check error: %s", e)

                logger.info("[Updater] No published releases found on repository %s/%s.", self.owner, self.repo)
                return UpdateCheckResult(
                    status="up_to_date",
                    current_version=current_version,
                    auth_status="ok",
                )

            elif resp.status_code != 200:
                err_msg = f"GitHub API error HTTP {resp.status_code}"
                logger.warning("[Updater] %s", err_msg)
                return UpdateCheckResult(
                    status="error",
                    current_version=current_version,
                    auth_status="ok",
                    error_message=err_msg,
                )

            release_data = resp.json()
            return self._parse_and_evaluate_release(release_data, current_version, token)

        except requests.exceptions.Timeout:
            msg = "Connection to GitHub timed out"
            logger.info("[Updater] Release check failed: %s", msg)
            return UpdateCheckResult(status="error", current_version=current_version, error_message=msg)

        except requests.exceptions.ConnectionError:
            msg = "Network unavailable"
            logger.info("[Updater] Release check failed: %s", msg)
            return UpdateCheckResult(status="error", current_version=current_version, error_message=msg)

        except Exception as e:
            logger.warning("[Updater] Unexpected error querying GitHub releases: %s", e)
            return UpdateCheckResult(status="error", current_version=current_version, error_message=str(e))

    def _parse_and_evaluate_release(
        self,
        data: Dict,
        current_version: str,
        token: Optional[str],
    ) -> UpdateCheckResult:
        """Parses release payload and evaluates SemVer precedence and platform assets."""
        tag_name = data.get("tag_name", "")
        release_version = normalize_tag(tag_name)
        is_draft = data.get("draft", False)
        is_prerelease = data.get("prerelease", False)

        if is_draft or (is_prerelease and DEFAULT_CHANNEL == "stable"):
            logger.info("[Updater] Latest tag %s is draft/prerelease. Ignoring for stable channel.", tag_name)
            return UpdateCheckResult(
                status="up_to_date",
                current_version=current_version,
                auth_status="ok",
            )

        raw_assets = data.get("assets", [])
        assets: List[ReleaseAsset] = []
        checksum_asset_api_url: Optional[str] = None
        checksum_asset_download_url: Optional[str] = None

        for a in raw_assets:
            name = a.get("name", "")
            asset_id = a.get("id")
            api_url = a.get("url")
            browser_download_url = a.get("browser_download_url", "")
            size = a.get("size", 0)
            content_type = a.get("content_type", "")
            digest = a.get("digest")

            if any(name.lower() == cfn.lower() for cfn in CHECKSUM_FILE_NAMES):
                checksum_asset_api_url = api_url
                checksum_asset_download_url = browser_download_url

            assets.append(
                ReleaseAsset(
                    name=name,
                    download_url=browser_download_url,
                    size=size,
                    asset_id=asset_id,
                    api_url=api_url,
                    sha256=digest,
                    content_type=content_type,
                )
            )

        # Fetch SHA256SUMS.txt if present
        checksums_map: Dict[str, str] = {}
        if checksum_asset_api_url or checksum_asset_download_url:
            checksums_map = self._fetch_checksums(checksum_asset_api_url, checksum_asset_download_url, token)
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

        if is_newer(release_version, current_version):
            target_asset = select_platform_asset(assets)
            if target_asset:
                logger.info(
                    "[Updater] New update available: v%s (target asset: %s, size: %.1f MB)",
                    release_version,
                    target_asset.name,
                    target_asset.size_mb,
                )
                return UpdateCheckResult(
                    status="available",
                    current_version=current_version,
                    latest_release=release_info,
                    target_asset=target_asset,
                    auth_status="ok",
                )
            else:
                logger.warning("[Updater] Release v%s found, but no compatible package for host platform.", release_version)
                return UpdateCheckResult(
                    status="no_asset",
                    current_version=current_version,
                    latest_release=release_info,
                    auth_status="ok",
                    error_message=f"Version v{release_version} is available, but no compatible asset was found for your operating system.",
                )
        else:
            logger.info("[Updater] Vyntra is up to date (current: v%s, latest: v%s).", current_version, release_version)
            return UpdateCheckResult(
                status="up_to_date",
                current_version=current_version,
                latest_release=release_info,
                auth_status="ok",
            )

    def _fetch_checksums(
        self,
        api_url: Optional[str],
        download_url: Optional[str],
        token: Optional[str],
    ) -> Dict[str, str]:
        """Downloads and parses SHA256SUMS.txt from GitHub release (authenticated or public)."""
        if token and api_url:
            return self._fetch_private_checksums(api_url, token)

        mapping = {}
        target_url = download_url or api_url
        if not target_url:
            return mapping

        from vyntra import __version__
        headers = {
            "Accept": "application/octet-stream",
            "User-Agent": USER_AGENT_TEMPLATE.format(version=__version__),
        }
        try:
            resp = requests.get(
                target_url,
                headers=headers,
                timeout=(NETWORK_CONNECT_TIMEOUT, NETWORK_READ_TIMEOUT),
            )
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        h = parts[0].strip().lower()
                        fn = parts[-1].strip().lstrip("*")
                        mapping[fn] = h
                logger.info("[Updater] Parsed %d verified checksums from release manifest.", len(mapping))
        except Exception as e:
            logger.debug("[Updater] Could not fetch public checksums manifest: %s", e)
        return mapping

    def _fetch_private_checksums(self, asset_api_url: str, token: str) -> Dict[str, str]:
        """Authenticated download of SHA256SUMS.txt from private GitHub release."""
        from vyntra import __version__
        mapping = {}
        headers = {
            "Authorization": f"Bearer {token.strip()}",
            "Accept": "application/octet-stream",
            "User-Agent": USER_AGENT_TEMPLATE.format(version=__version__),
        }
        try:
            # Probe redirect
            probe = requests.get(
                asset_api_url,
                headers=headers,
                allow_redirects=False,
                timeout=(NETWORK_CONNECT_TIMEOUT, NETWORK_READ_TIMEOUT),
            )
            fetch_url = asset_api_url
            fetch_headers = dict(headers)
            if probe.status_code in (301, 302, 303, 307, 308):
                loc = probe.headers.get("Location")
                if loc:
                    fetch_url = loc
                    fetch_headers.pop("Authorization", None)

            resp = requests.get(fetch_url, headers=fetch_headers, timeout=(NETWORK_CONNECT_TIMEOUT, NETWORK_READ_TIMEOUT))
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        h = parts[0].strip().lower()
                        fn = parts[-1].strip().lstrip("*")
                        mapping[fn] = h
                logger.info("[Updater] Parsed %d verified checksums from private release manifest.", len(mapping))
        except Exception as e:
            logger.debug("[Updater] Could not fetch private checksums manifest: %s", e)
        return mapping

    def download_asset(
        self,
        asset: ReleaseAsset,
        expected_sha256: Optional[str] = None,
        on_progress: Optional[Callable[[DownloadProgress], None]] = None,
        cancel_flag: Optional[threading.Event] = None,
    ) -> Path:
        """Downloads release asset using authorized token if available."""
        token = self.auth_mgr.get_token() if self.auth_mgr else None
        return self.downloader.download_asset(
            asset=asset,
            expected_sha256=expected_sha256 or asset.sha256,
            auth_token=token,
            on_progress=on_progress,
        )


class GitHubPrivateReleaseProvider(GitHubReleaseProvider):
    """
    Backwards-compatible update provider communicating securely with private GitHub repository releases
    using user-authorized credentials stored in the host OS Keyring.
    """

    def __init__(
        self,
        owner: str = GITHUB_OWNER,
        repo: str = GITHUB_REPO,
        auth_mgr: Optional[UpdaterAuthManager] = None,
        downloader: Optional[UpdateDownloadManager] = None,
        require_auth: bool = True,
    ):
        super().__init__(
            owner=owner,
            repo=repo,
            auth_mgr=auth_mgr,
            downloader=downloader,
            require_auth=require_auth,
        )
