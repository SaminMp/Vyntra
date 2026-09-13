"""
Robust chunked download manager with streaming SHA-256 checksum computation
and real-time download progress tracking.
"""

from datetime import datetime
import hashlib
from pathlib import Path
import threading
import time
from typing import Callable, Optional
import requests

from vyntra.updater.constants import (
    NETWORK_CONNECT_TIMEOUT,
    NETWORK_READ_TIMEOUT,
    USER_AGENT_TEMPLATE,
    get_staging_dir,
)
from vyntra.updater.models import DownloadProgress, ReleaseAsset
from vyntra.utils.logger import logger


class UpdateIntegrityError(Exception):
    """Raised when the downloaded update payload fails SHA-256 verification."""
    pass


class UpdateDownloadError(Exception):
    """Raised when a network or I/O error interrupts the download."""
    pass


class UpdateDownloadManager:
    """
    Manages streaming download of release assets into staging storage with
    on-the-fly cryptographic verification and progress reporting.
    """

    CHUNK_SIZE = 64 * 1024  # 64 KB chunks

    def __init__(self):
        self._cancel_flag = threading.Event()
        self._is_downloading = False
        self._current_dest: Optional[Path] = None

    def cancel(self):
        """Signals active download to abort and clean up."""
        self._cancel_flag.set()

    @property
    def is_downloading(self) -> bool:
        return self._is_downloading

    def download_asset(
        self,
        asset: ReleaseAsset,
        expected_sha256: Optional[str] = None,
        on_progress: Optional[Callable[[DownloadProgress], None]] = None,
    ) -> Path:
        """
        Downloads a release asset to staging, verifies its SHA-256 digest,
        and returns the local Path to the verified asset file.

        Raises:
            UpdateIntegrityError: If checksum verification fails.
            UpdateDownloadError: If network fails or download is cancelled.
        """
        self._cancel_flag.clear()
        self._is_downloading = True

        staging_dir = get_staging_dir()
        dest_path = staging_dir / asset.name
        self._current_dest = dest_path

        # Clean any stale file at destination
        if dest_path.exists():
            try:
                dest_path.unlink()
            except Exception as e:
                logger.warning("[Updater] Could not remove stale staging file: %s", e)

        headers = {
            "User-Agent": USER_AGENT_TEMPLATE.format(version="1.1.3"),
            "Accept": "application/octet-stream",
        }

        hasher = hashlib.sha256()
        downloaded = 0
        total_size = asset.size

        start_time = time.time()
        last_progress_time = start_time
        bytes_since_last = 0
        current_speed = 0.0

        try:
            logger.info("[Updater] Starting download of asset: %s (%s)", asset.name, asset.download_url)
            with requests.get(
                asset.download_url,
                headers=headers,
                stream=True,
                timeout=(NETWORK_CONNECT_TIMEOUT, NETWORK_READ_TIMEOUT),
            ) as response:
                response.raise_for_status()

                # Update total size if Content-Length header provided
                content_len = response.headers.get("content-length")
                if content_len and content_len.isdigit():
                    total_size = int(content_len)

                with open(dest_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                        if self._cancel_flag.is_set():
                            logger.info("[Updater] Download cancelled by user.")
                            raise UpdateDownloadError("Download was cancelled.")

                        if not chunk:
                            continue

                        f.write(chunk)
                        hasher.update(chunk)
                        chunk_len = len(chunk)
                        downloaded += chunk_len
                        bytes_since_last += chunk_len

                        # Calculate speed every 0.25 seconds
                        now = time.time()
                        dt = now - last_progress_time
                        if dt >= 0.25:
                            current_speed = bytes_since_last / dt
                            last_progress_time = now
                            bytes_since_last = 0

                            if on_progress:
                                pct = (downloaded / total_size * 100) if total_size > 0 else 0.0
                                prog = DownloadProgress(
                                    downloaded_bytes=downloaded,
                                    total_bytes=total_size,
                                    percent=min(100.0, pct),
                                    speed_bps=current_speed,
                                    is_complete=False,
                                    status_text=f"Downloading... {downloaded / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB",
                                )
                                on_progress(prog)

            # Final download progress dispatch
            if on_progress:
                prog = DownloadProgress(
                    downloaded_bytes=downloaded,
                    total_bytes=total_size,
                    percent=100.0,
                    speed_bps=0.0,
                    is_complete=True,
                    status_text="Verifying package integrity...",
                )
                on_progress(prog)

            computed_hash = hasher.hexdigest().lower()
            logger.info("[Updater] Download complete. Computed SHA-256: %s", computed_hash)

            # -----------------------------------------------------------------
            # Cryptographic Verification
            # -----------------------------------------------------------------
            target_hash = expected_sha256 or asset.sha256
            if target_hash:
                target_hash = target_hash.strip().lower()
                logger.info("[Updater] Verifying against expected SHA-256: %s", target_hash)
                if computed_hash != target_hash:
                    # Clean up corrupted file immediately
                    if dest_path.exists():
                        dest_path.unlink()
                    err_msg = (
                        f"Checksum mismatch! Expected: {target_hash[:16]}..., "
                        f"Computed: {computed_hash[:16]}... Download rejected for security."
                    )
                    logger.error("[Updater] %s", err_msg)
                    raise UpdateIntegrityError(err_msg)
                logger.info("[Updater] SHA-256 verification SUCCESSFUL.")
            else:
                logger.info("[Updater] No SHA-256 hash available for asset. Proceeding with downloaded binary.")

            return dest_path

        except (requests.RequestException, OSError) as e:
            # Clean up incomplete file
            if dest_path.exists():
                try:
                    dest_path.unlink()
                except Exception:
                    pass
            logger.error("[Updater] Download failed: %s", e)
            raise UpdateDownloadError(f"Download network error: {e}") from e

        finally:
            self._is_downloading = False
