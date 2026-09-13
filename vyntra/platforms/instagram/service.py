"""
Instagram platform service implementation for Vyntra.
Extracts Reels, Posts, and Videos via yt-dlp.
"""

from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional
import yt_dlp

from vyntra.config import config_manager
from vyntra.models import AudioQuality, DownloadTask, MediaFormat, MediaItem, Platform, PlatformCapabilities
from vyntra.platforms.base import BasePlatformService
from vyntra.platforms.registry import platform_registry
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.utils.filename import sanitize_filename
from vyntra.utils.formatters import format_duration
from vyntra.utils.logger import logger


class InstagramPlatform(BasePlatformService):
    """Platform service managing Instagram extraction, playback streaming, and downloading."""

    INSTAGRAM_URL_REGEX = re.compile(
        r"^(https?://)?(www\.)?(instagram\.com|instagr\.am)/(p|reel|tv|stories)/([a-zA-Z0-9_-]+)"
    )

    @property
    def platform_id(self) -> str:
        return Platform.INSTAGRAM.value

    @property
    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            platform_id=self.platform_id,
            display_name="Instagram",
            icon="📸",
            supports_search=False,          # Honest UI: Instagram has no public unauthenticated keyword search API
            supports_url_input=True,
            supports_video_playback=True,
            supports_audio_preview=True,
            supports_mp4=True,
            supports_mp3=True,
            supports_video_quality=False,    # Instagram serves single fixed stream resolution
            supports_audio_quality=True,
        )

    def can_handle_url(self, url: str) -> bool:
        if not url:
            return False
        return bool(self.INSTAGRAM_URL_REGEX.search(url.strip()))

    def _get_ydl_base_opts(self) -> dict:
        """Constructs base options for yt-dlp Instagram queries."""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "noplaylist": True,
            "socket_timeout": 15,
        }
        # Check if user has configured custom cookies in config
        cookie_path = getattr(config_manager.config, "instagram_custom_cookie_path", "")
        if cookie_path and Path(cookie_path).is_file():
            opts["cookiefile"] = cookie_path
        return opts

    def extract_from_url(self, url: str) -> Optional[MediaItem]:
        """
        Extracts reel/post metadata and stream information using yt-dlp Instagram extractor.
        """
        clean_url = url.strip()
        logger.info("[Instagram] Extracting metadata for: %s", clean_url)
        opts = self._get_ydl_base_opts()

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(clean_url, download=False)
                if not info:
                    return None

                media_id = str(info.get("id") or "")
                title = str(info.get("title") or info.get("description") or f"Instagram Reel {media_id}").strip()
                # Clean up title for single line display
                title = title.split("\n")[0][:120].strip() or f"Instagram Post {media_id}"
                channel = str(info.get("uploader") or info.get("uploader_id") or "Instagram Creator")
                duration = int(info.get("duration") or 0)
                thumb = str(info.get("thumbnail") or "")
                stream_url = str(info.get("url") or "")

                # Some posts provide formats list
                if not stream_url and info.get("formats"):
                    for fmt in reversed(info["formats"]):
                        if fmt.get("url"):
                            stream_url = fmt["url"]
                            break

                item = MediaItem(
                    video_id=media_id,
                    title=title,
                    channel=f"@{channel.lstrip('@')}",
                    duration_seconds=duration,
                    duration_formatted=format_duration(duration),
                    thumbnail_url=thumb,
                    url=clean_url,
                    platform=self.platform_id,
                    audio_source_url=stream_url,
                )
                return item
        except Exception as err:
            logger.error("[Instagram] Extraction failed: %s", err)
            raise RuntimeError(f"Instagram extraction failed: {err}")

    def prepare_playback_stream(self, item: MediaItem) -> Dict[str, Any]:
        """
        Resolves direct playable stream URL for SynchronizedMediaPlayer.
        """
        logger.info("[Instagram] Preparing playback stream for %s (%s)", item.display_title, item.video_id)
        if item.audio_source_url and item.audio_source_url.startswith("http"):
            return {
                "url": item.audio_source_url,
                "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            }

        # Re-extract fresh stream URL if not cached
        fresh_item = self.extract_from_url(item.url)
        if fresh_item and fresh_item.audio_source_url:
            item.audio_source_url = fresh_item.audio_source_url
            return {
                "url": fresh_item.audio_source_url,
                "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            }

        raise RuntimeError(f"Could not resolve playable video stream for Instagram: {item.url}")

    def build_download_options(self, task: DownloadTask, out_base_without_ext: str) -> dict:
        """Constructs yt-dlp download options for Instagram MP4 or MP3 output."""
        ffmpeg_status = ffmpeg_service.get_status()
        opts: Dict[str, Any] = {
            "outtmpl": f"{out_base_without_ext}.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "writethumbnail": False,
        }

        if ffmpeg_status.is_available and ffmpeg_status.ffmpeg_path:
            opts["ffmpeg_location"] = str(Path(ffmpeg_status.ffmpeg_path).parent)

        if task.format == MediaFormat.MP3:
            # Extract audio and convert to MP3
            bitrate = "320"
            if task.audio_quality == AudioQuality.STANDARD:
                bitrate = "192"
            elif task.audio_quality == AudioQuality.HIGH:
                bitrate = "256"

            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": bitrate,
                },
                {"key": "FFmpegMetadata", "add_metadata": True},
            ]
        else:
            # Standard MP4 download
            opts["format"] = "bestvideo+bestaudio/best"
            opts["postprocessors"] = [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
                {"key": "FFmpegMetadata", "add_metadata": True},
            ]

        cookie_path = getattr(config_manager.config, "instagram_custom_cookie_path", "")
        if cookie_path and Path(cookie_path).is_file():
            opts["cookiefile"] = cookie_path

        return opts


# Instantiate and register
instagram_platform = InstagramPlatform()
platform_registry.register(instagram_platform)
