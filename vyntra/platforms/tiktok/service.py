"""
TikTok platform service implementation for Vyntra.
Extracts TikTok videos and audio via yt-dlp.
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


class TikTokPlatform(BasePlatformService):
    """Platform service managing TikTok video extraction, playback streaming, and downloading."""

    TIKTOK_URL_REGEX = re.compile(
        r"^(https?://)?(www\.|m\.|vm\.|vt\.)?(tiktok\.com/)(@[\w.-]+/video/\d+|[\w.-]+/\d+|\w+/?)"
    )

    @property
    def platform_id(self) -> str:
        return Platform.TIKTOK.value

    @property
    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            platform_id=self.platform_id,
            display_name="TikTok",
            icon="🎵",
            supports_search=False,          # Honest UI: TikTok search requires browser msToken & X-Bogus signatures
            supports_url_input=True,
            supports_video_playback=True,
            supports_audio_preview=True,
            supports_mp4=True,
            supports_mp3=True,
            supports_video_quality=False,    # TikTok provides single original video stream
            supports_audio_quality=True,
        )

    def can_handle_url(self, url: str) -> bool:
        if not url:
            return False
        clean = url.strip()
        if "tiktok.com" in clean:
            return True
        return bool(self.TIKTOK_URL_REGEX.search(clean))

    def _get_ydl_base_opts(self) -> dict:
        """Constructs base options for yt-dlp TikTok queries."""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "noplaylist": True,
            "socket_timeout": 15,
        }
        cookie_path = getattr(config_manager.config, "tiktok_custom_cookie_path", "")
        if cookie_path and Path(cookie_path).is_file():
            opts["cookiefile"] = cookie_path
        return opts

    def classify_error(self, err: Exception) -> tuple[bool, str, str]:
        """
        Classifies TikTok extraction errors into retryable vs non-retryable categories
        and returns clean, user-friendly messages without raw stack traces.
        Returns: (is_retryable: bool, category: str, user_friendly_message: str)
        """
        err_str = str(err).lower()
        if "unexpected response from webpage request" in err_str or "challenge" in err_str:
            return (
                False,
                "challenge_or_waf_block",
                "Unable to load this TikTok video right now due to TikTok challenge verification. Please try again later.",
            )
        elif "not found" in err_str or "does not exist" in err_str or "unavailable" in err_str:
            return (
                False,
                "video_not_found",
                "This TikTok video was deleted or is not publicly accessible.",
            )
        elif "private" in err_str or "login" in err_str:
            return (
                False,
                "login_or_private",
                "This TikTok video is private or requires an account login.",
            )
        elif any(k in err_str for k in ("timed out", "timeout", "connection reset", "502", "503", "504")):
            return (
                True,
                "network_temporary",
                "Network timeout connecting to TikTok. Please check your internet connection and try again.",
            )
        else:
            return (
                False,
                "extraction_error",
                "Unable to load this TikTok video right now. Please verify the link and try again later.",
            )

    def diagnose(self, test_url: str = "") -> str:
        """
        Generates a comprehensive, safe diagnostics report for TikTok extraction.
        Guarantees zero leakage of cookies, tokens, or private user data.
        """
        import importlib
        import sys

        lines = [
            "Vyntra TikTok Diagnostics",
            "─────────────────────────────",
            "",
            "TikTok URL:",
            test_url.strip() if test_url else "(No URL specified)",
            "",
            "yt-dlp:",
            getattr(yt_dlp, "__version__", getattr(yt_dlp.version, "__version__", "unknown")),
            "",
            "Python:",
            sys.version.split()[0],
            "",
        ]

        # Check curl_cffi
        curl_installed = False
        try:
            curl_mod = importlib.import_module("curl_cffi")
            curl_ver = getattr(curl_mod, "__version__", "installed")
            lines.extend(["curl_cffi:", f"INSTALLED (v{curl_ver})", ""])
            curl_installed = True
        except ImportError:
            lines.extend(["curl_cffi:", "MISSING (Optional dependency for TLS browser impersonation)", ""])

        # Check browser impersonation capability
        impersonation_status = "AVAILABLE" if curl_installed else "UNAVAILABLE (Requires curl_cffi)"
        lines.extend(["Browser impersonation:", impersonation_status, ""])

        # Check cookies
        cookie_path = getattr(config_manager.config, "tiktok_custom_cookie_path", "")
        if cookie_path and Path(cookie_path).is_file():
            lines.extend(["Cookies:", f"AVAILABLE (Configured: {Path(cookie_path).name})", ""])
        else:
            lines.extend(["Cookies:", "NOT USED (Public extraction mode)", ""])

        # Perform live extraction test if URL provided
        if test_url and self.can_handle_url(test_url):
            try:
                item = self.extract_from_url(test_url)
                if item:
                    lines.extend([
                        "Extraction:",
                        "SUCCESS",
                        "",
                        "Extracted Title:",
                        item.display_title,
                        "",
                        "Duration:",
                        item.duration_formatted,
                    ])
                else:
                    lines.extend([
                        "Extraction:",
                        "FAILED (No metadata returned)",
                        "",
                        "Failure category:",
                        "empty_metadata",
                    ])
            except Exception as e:
                is_retryable, category, friendly_msg = self.classify_error(e)
                clean_err = str(e).replace("\n", " ")[:200]
                lines.extend([
                    "Extraction:",
                    "FAILED",
                    "",
                    "Failure category:",
                    category,
                    "",
                    "Retryable:",
                    "YES" if is_retryable else "NO",
                    "",
                    "Underlying error:",
                    clean_err,
                ])
        else:
            lines.extend(["Extraction:", "SKIPPED (No valid TikTok URL provided for test)"])

        return "\n".join(lines)

    def extract_from_url(self, url: str) -> Optional[MediaItem]:
        """
        Extracts video metadata and stream URL using yt-dlp TikTok extractor.
        """
        clean_url = url.strip()
        logger.info("[TikTok] Extracting metadata for: %s", clean_url)
        opts = self._get_ydl_base_opts()

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(clean_url, download=False)
                if not info:
                    return None

                media_id = str(info.get("id") or "")
                raw_title = str(info.get("title") or info.get("description") or f"TikTok Video {media_id}").strip()
                title = raw_title.split("\n")[0][:120].strip() or f"TikTok Video {media_id}"
                channel = str(info.get("uploader") or info.get("creator") or info.get("uploader_id") or "TikTok Creator")
                duration = int(info.get("duration") or 0)
                thumb = str(info.get("thumbnail") or "")
                stream_url = str(info.get("url") or "")

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
            is_retryable, category, user_msg = self.classify_error(err)
            logger.error("[TikTok] Extraction failed (category=%s, retryable=%s): %s", category, is_retryable, err)
            raise RuntimeError(user_msg) from err

    def prepare_playback_stream(self, item: MediaItem) -> Dict[str, Any]:
        """
        Resolves direct playable stream URL for SynchronizedMediaPlayer.
        """
        logger.info("[TikTok] Preparing playback stream for %s (%s)", item.display_title, item.video_id)
        if item.audio_source_url and item.audio_source_url.startswith("http"):
            return {
                "url": item.audio_source_url,
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://www.tiktok.com/",
                },
            }

        fresh_item = self.extract_from_url(item.url)
        if fresh_item and fresh_item.audio_source_url:
            item.audio_source_url = fresh_item.audio_source_url
            return {
                "url": fresh_item.audio_source_url,
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://www.tiktok.com/",
                },
            }

        raise RuntimeError(f"Could not resolve playable video stream for TikTok: {item.url}")

    def build_download_options(self, task: DownloadTask, out_base_without_ext: str) -> dict:
        """Constructs yt-dlp download options for TikTok MP4 or MP3 output."""
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
            opts["format"] = "bestvideo+bestaudio/best"
            opts["postprocessors"] = [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
                {"key": "FFmpegMetadata", "add_metadata": True},
            ]

        cookie_path = getattr(config_manager.config, "tiktok_custom_cookie_path", "")
        if cookie_path and Path(cookie_path).is_file():
            opts["cookiefile"] = cookie_path

        return opts


# Instantiate and register
tiktok_platform = TikTokPlatform()
platform_registry.register(tiktok_platform)
