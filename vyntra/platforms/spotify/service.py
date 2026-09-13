"""
Spotify platform service implementation for Vyntra.
Audio-only architecture: supports official 30s preview playback and metadata-matched MP3 downloading.
Strictly NO MP4 or video quality options.
"""

import base64
import json
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional
import urllib.parse
import urllib.request
import yt_dlp

from vyntra.config import config_manager
from vyntra.models import AudioQuality, DownloadTask, MediaFormat, MediaItem, Platform, PlatformCapabilities
from vyntra.platforms.base import BasePlatformService
from vyntra.platforms.registry import platform_registry
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.utils.filename import sanitize_filename
from vyntra.utils.formatters import format_duration
from vyntra.utils.logger import logger


class SpotifyPlatform(BasePlatformService):
    """
    Platform service managing Spotify track discovery, official audio preview streaming,
    and metadata-matched high-fidelity MP3 downloads.
    """

    SPOTIFY_URL_REGEX = re.compile(
        r"^(https?://)?(open\.)?spotify\.com/(track|album|playlist)/([a-zA-Z0-9]+)|spotify:track:([a-zA-Z0-9]+)"
    )

    def __init__(self):
        super().__init__()
        self._cached_api_token: Optional[str] = None

    @property
    def platform_id(self) -> str:
        return Platform.SPOTIFY.value

    @property
    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            platform_id=self.platform_id,
            display_name="Spotify",
            icon="🟢",
            supports_search=True,           # Supported via Spotify Web API or track URLs
            supports_url_input=True,
            supports_video_playback=False,  # Strictly audio-only
            supports_audio_preview=True,    # 30-second official MP3 preview stream
            supports_mp4=False,             # STRICTLY NO MP4
            supports_mp3=True,              # Pure MP3 audio downloading
            supports_video_quality=False,   # NO video quality
            supports_audio_quality=True,    # 128 / 192 / 256 / 320 kbps
        )

    def can_handle_url(self, url: str) -> bool:
        if not url:
            return False
        clean = url.strip()
        if "spotify.com" in clean or clean.startswith("spotify:"):
            return True
        return bool(self.SPOTIFY_URL_REGEX.search(clean))

    def _extract_track_id(self, url: str) -> Optional[str]:
        """Extracts the Spotify track ID from a URL or URI."""
        clean = url.strip()
        m = re.search(r"track/([a-zA-Z0-9]+)", clean)
        if m:
            return m.group(1)
        m2 = re.search(r"spotify:track:([a-zA-Z0-9]+)", clean)
        if m2:
            return m2.group(1)
        return None

    def _get_api_access_token(self) -> Optional[str]:
        """
        Retrieves a Spotify Web API Bearer token using Client Credentials grant
        if the user has configured spotify_client_id and spotify_client_secret.
        """
        client_id = getattr(config_manager.config, "spotify_client_id", "").strip()
        client_secret = getattr(config_manager.config, "spotify_client_secret", "").strip()

        if not client_id or not client_secret:
            return None

        if self._cached_api_token:
            return self._cached_api_token

        try:
            auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
            req = urllib.request.Request(
                "https://accounts.spotify.com/api/token",
                data=b"grant_type=client_credentials",
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                token = data.get("access_token")
                self._cached_api_token = token
                return token
        except Exception as err:
            logger.warning("[Spotify] Client Credentials token exchange failed: %s", err)
            return None

    def search(self, query: str, max_results: int = 12) -> List[MediaItem]:
        """
        Searches Spotify for tracks using official Web API if configured,
        or falls back to direct URL parsing if a URL is supplied.
        """
        clean_query = query.strip()
        if self.can_handle_url(clean_query):
            item = self.extract_from_url(clean_query)
            return [item] if item else []

        token = self._get_api_access_token()
        if token:
            try:
                encoded = urllib.parse.quote(clean_query)
                url = f"https://api.spotify.com/v1/search?q={encoded}&type=track&limit={max_results}"
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    items = []
                    for t in data.get("tracks", {}).get("items", []):
                        track_id = t.get("id") or ""
                        name = t.get("name") or "Unknown Track"
                        artists = ", ".join(a.get("name") for a in t.get("artists", []))
                        duration_ms = t.get("duration_ms") or 0
                        duration_sec = duration_ms // 1000
                        album_obj = t.get("album") or {}
                        album_name = album_obj.get("name")
                        images = album_obj.get("images") or []
                        thumb = images[0]["url"] if images else ""
                        preview_url = t.get("preview_url") or ""

                        items.append(
                            MediaItem(
                                video_id=track_id,
                                title=name,
                                channel=artists,
                                album=album_name,
                                duration_seconds=duration_sec,
                                duration_formatted=format_duration(duration_sec),
                                thumbnail_url=thumb,
                                url=f"https://open.spotify.com/track/{track_id}",
                                platform=self.platform_id,
                                preview_url=preview_url,
                            )
                        )
                    return items
            except Exception as e:
                logger.error("[Spotify] API search failed: %s", e)

        # Fallback when no Spotify Client ID is configured:
        # Search via YouTube Music / Audio matching to preview the track metadata
        logger.info("[Spotify] No Client ID configured; searching for track query: %s", clean_query)
        from vyntra.services.search_service import search_service
        yt_results = search_service.search(f"{clean_query} official audio", max_results=max_results)
        spotify_results = []
        for r in yt_results:
            spotify_results.append(
                MediaItem(
                    video_id=r.video_id,
                    title=r.title,
                    channel=r.channel,
                    duration_seconds=r.duration_seconds,
                    duration_formatted=r.duration_formatted,
                    thumbnail_url=r.thumbnail_url,
                    url=r.url,
                    platform=self.platform_id,
                    audio_source_url=r.url,
                )
            )
        return spotify_results

    def extract_from_url(self, url: str) -> Optional[MediaItem]:
        """
        Extracts pristine Spotify track metadata and 30-second official preview stream
        from Spotify's public embed endpoint without requiring API keys.
        """
        track_id = self._extract_track_id(url)
        if not track_id:
            logger.warning("[Spotify] Invalid track URL: %s", url)
            return None

        embed_url = f"https://open.spotify.com/embed/track/{track_id}"
        req = urllib.request.Request(
            embed_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8")

            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
            if not m:
                raise ValueError("Could not parse Spotify embed data")

            data = json.loads(m.group(1))
            entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
            title = entity.get("title") or entity.get("name") or f"Spotify Track {track_id}"
            artists = ", ".join(a.get("name") for a in entity.get("artists", [])) or "Spotify Artist"
            duration_ms = entity.get("duration") or 0
            duration_sec = int(duration_ms) // 1000 if duration_ms else 0
            preview_url = entity.get("audioPreview", {}).get("url") or ""

            # Extract cover art image
            cover_art_sources = entity.get("coverArt", {}).get("sources", [])
            thumb = cover_art_sources[0].get("url") if cover_art_sources else ""

            return MediaItem(
                video_id=track_id,
                title=title,
                channel=artists,
                duration_seconds=duration_sec,
                duration_formatted=format_duration(duration_sec),
                thumbnail_url=thumb,
                url=f"https://open.spotify.com/track/{track_id}",
                platform=self.platform_id,
                preview_url=preview_url,
            )
        except Exception as err:
            logger.error("[Spotify] Embed extraction failed for %s: %s", url, err)
            # Fallback to oembed
            return self._extract_via_oembed(url, track_id)

    def _extract_via_oembed(self, url: str, track_id: str) -> Optional[MediaItem]:
        """Secondary fallback for Spotify metadata using the official oEmbed API."""
        try:
            oembed_url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(url)}"
            req = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return MediaItem(
                    video_id=track_id,
                    title=data.get("title", f"Spotify Track {track_id}"),
                    channel="Spotify Artist",
                    thumbnail_url=data.get("thumbnail_url", ""),
                    url=f"https://open.spotify.com/track/{track_id}",
                    platform=self.platform_id,
                )
        except Exception as err:
            logger.error("[Spotify] oEmbed fallback failed: %s", err)
            return None

    def prepare_playback_stream(self, item: MediaItem) -> Dict[str, Any]:
        """
        Returns the official 30-second MP3 preview stream for SynchronizedMediaPlayer.
        """
        logger.info("[Spotify] Preparing preview audio stream for %s - %s", item.channel, item.display_title)
        preview = item.preview_url

        if not preview and item.url and "spotify.com" in item.url:
            fresh = self.extract_from_url(item.url)
            if fresh and fresh.preview_url:
                preview = fresh.preview_url
                item.preview_url = preview

        if preview and preview.startswith("http"):
            return {
                "url": preview,
                "headers": {"User-Agent": "Mozilla/5.0"},
            }

        # If Spotify did not supply a 30s preview snippet, acquire matching audio stream
        logger.info("[Spotify] No official preview snippet available; matching audio stream for %s", item.display_title)
        search_query = f"{item.channel} - {item.display_title} official audio"
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "format": "bestaudio/best",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{search_query}", download=False)
            entries = info.get("entries", [])
            if entries:
                matched_url = entries[0].get("url")
                if matched_url:
                    return {
                        "url": matched_url,
                        "headers": {"User-Agent": "Mozilla/5.0"},
                    }

        raise RuntimeError(f"Could not resolve preview audio for Spotify track: {item.display_title}")

    def build_download_options(self, task: DownloadTask, out_base_without_ext: str) -> dict:
        """
        Constructs audio-only MP3 download options.
        Strictly enforces MP3 format (rejects MP4).
        Matches Spotify metadata against YouTube audio and transcodes to pristine MP3.
        """
        # Enforce audio-only
        task.format = MediaFormat.MP3

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

        # Use search query if this is a Spotify URL rather than a direct media stream
        item = task.result
        if "spotify.com" in item.url or item.platform == Platform.SPOTIFY.value:
            # Set search query as target
            task.result.url = f"ytsearch1:{item.channel} - {item.display_title} official audio"

        return opts


# Instantiate and register
spotify_platform = SpotifyPlatform()
platform_registry.register(spotify_platform)
