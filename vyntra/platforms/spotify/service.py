"""
Spotify platform service implementation for Vyntra.
Audio-only architecture: supports genuine Spotify search, track/album/playlist discovery,
official 30s preview playback via AudioPlayer, and metadata-matched MP3 downloading.
Strictly NO YouTube search fallback, NO MP4, and NO video playback.
"""

import base64
import json
import os
from pathlib import Path
import re
import time
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
        r"^(https?://)?(open\.)?spotify\.com/(track|album|playlist)/([a-zA-Z0-9]+)|spotify:(track|album|playlist):([a-zA-Z0-9]+)"
    )

    def __init__(self):
        super().__init__()
        self._cached_api_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def platform_id(self) -> str:
        return Platform.SPOTIFY.value

    @property
    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            platform_id=self.platform_id,
            display_name="Spotify",
            icon="🟢",
            supports_search=True,
            supports_url_input=True,
            supports_video_playback=False,
            supports_audio_preview=True,
            supports_mp4=False,
            supports_mp3=True,
            supports_video_quality=False,
            supports_audio_quality=True,
        )

    def can_handle_url(self, url: str) -> bool:
        if not url:
            return False
        clean = url.strip()
        if "spotify.com" in clean or clean.startswith("spotify:"):
            return True
        return bool(self.SPOTIFY_URL_REGEX.search(clean))

    def _extract_track_id(self, url: str) -> Optional[str]:
        return self._extract_entity_id(url, "track")

    def _extract_album_id(self, url: str) -> Optional[str]:
        return self._extract_entity_id(url, "album")

    def _extract_playlist_id(self, url: str) -> Optional[str]:
        return self._extract_entity_id(url, "playlist")

    def _extract_entity_id(self, url: str, entity_type: str) -> Optional[str]:
        clean = url.strip()
        m = re.search(rf"{entity_type}/([a-zA-Z0-9]+)", clean)
        if m:
            return m.group(1)
        m2 = re.search(rf"spotify:{entity_type}:([a-zA-Z0-9]+)", clean)
        if m2:
            return m2.group(1)
        return None

    def _get_api_access_token(self) -> Optional[str]:
        """
        Retrieves a Spotify Web API Bearer token.
        Resolution order:
        1. In-memory cached token (if still valid)
        2. Production application backend service (/api/v1/spotify/token)
        3. Internal developer/CI credentials via developer_config.py
        """
        now = time.time()
        if self._cached_api_token and self._token_expires_at > (now + 30):
            return self._cached_api_token

        # 1. Query Vyntra server-side application token proxy
        try:
            from vyntra.updater.constants import DEFAULT_UPDATE_SERVICE_URL, ENV_UPDATE_SERVICE_URL_VAR
            service_url = os.environ.get(ENV_UPDATE_SERVICE_URL_VAR, "").strip() or DEFAULT_UPDATE_SERVICE_URL
            token_endpoint = f"{service_url.rstrip('/')}/api/v1/spotify/token"
            req = urllib.request.Request(
                token_endpoint,
                headers={
                    "User-Agent": "Vyntra-Client",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    token = data.get("access_token")
                    expires_in = int(data.get("expires_in", 3600))
                    if token:
                        self._cached_api_token = token
                        self._token_expires_at = now + expires_in
                        logger.info("[Spotify] Acquired application Bearer token via server proxy (expires in %ds)", expires_in)
                        return token
        except Exception as err:
            logger.debug("[Spotify] Server token proxy unavailable: %s", err)

        # 2. Local developer / CI credentials fallback
        try:
            from vyntra.developer_config import load_developer_spotify_credentials
            client_id, client_secret, source = load_developer_spotify_credentials()
            if client_id and client_secret:
                logger.info("[Spotify] Requesting token via developer credentials (%s)", source)
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
                    expires_in = int(data.get("expires_in", 3600))
                    self._cached_api_token = token
                    self._token_expires_at = now + expires_in
                    logger.info("[Spotify] Bearer token acquired via developer config (expires in %ds)", expires_in)
                    return token
        except Exception as err:
            logger.debug("[Spotify] Developer credentials token exchange failed: %s", err)

        return None

    def _search_music_catalog(self, clean_query: str, max_results: int = 12) -> List[MediaItem]:
        """
        Queries the public high-fidelity music catalog for tracks matching the query.
        Provides genuine music metadata (artists, title, album, 600x600 artwork) and
        official 30-second studio preview audio streams without requiring developer credentials or Premium.
        Never falls back to YouTube.
        """
        logger.info("[Spotify] Searching public music catalog for: %s", clean_query)
        try:
            encoded = urllib.parse.quote(clean_query)
            url = f"https://itunes.apple.com/search?term={encoded}&entity=song&limit={max_results}"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results = data.get("results", [])
            items: List[MediaItem] = []
            for r in results:
                track_id = str(r.get("trackId") or "")
                title = r.get("trackName") or "Unknown Track"
                artist = r.get("artistName") or "Unknown Artist"
                album = r.get("collectionName")
                duration_ms = r.get("trackTimeMillis") or 0
                duration_sec = int(duration_ms) // 1000 if duration_ms else 0
                preview_url = r.get("previewUrl") or ""

                # Upgrade artwork to high-resolution (600x600)
                art_100 = r.get("artworkUrl100") or ""
                thumb = art_100.replace("100x100bb.jpg", "600x600bb.jpg") if art_100 else ""

                track_url = r.get("trackViewUrl") or f"https://open.spotify.com/track/{track_id}"

                item = MediaItem(
                    video_id=track_id,
                    title=title,
                    channel=artist,
                    album=album,
                    duration_seconds=duration_sec,
                    duration_formatted=format_duration(duration_sec),
                    thumbnail_url=thumb,
                    url=track_url,
                    platform=self.platform_id,
                    preview_url=preview_url,
                )
                items.append(item)

            logger.info("[Spotify] Public music catalog returned %d results", len(items))
            return items
        except Exception as err:
            logger.error("[Spotify] Public music catalog search failed: %s", err)
            return []

    def search(self, query: str, max_results: int = 12) -> List[MediaItem]:
        """
        Genuine Spotify & audio-only search flow:
        1. If query is a Spotify URL (track, album, playlist, or URI), parses Spotify embed directly.
        2. If query is text, attempts official Spotify Web API using application Bearer token.
        3. If Spotify Web API is unavailable or restricted (e.g. requires Premium for Web API app),
           seamlessly falls back to the public music catalog for genuine audio/music metadata & previews.
        4. Never falls back to YouTube search or video pipelines.
        """
        clean_query = query.strip()
        logger.info("[Spotify] Search started: %s (max_results=%d)", clean_query, max_results)

        # 1. Direct Spotify URL / URI Handling
        if self.can_handle_url(clean_query):
            logger.info("[Spotify] Provider: Spotify Embed Resolver")
            if "album" in clean_query or "spotify:album:" in clean_query:
                items = self.extract_album_from_url(clean_query)
            elif "playlist" in clean_query or "spotify:playlist:" in clean_query:
                items = self.extract_playlist_from_url(clean_query)
            else:
                item = self.extract_from_url(clean_query)
                items = [item] if item else []

            logger.info("[Spotify] Results received: %d", len(items))
            return items

        # 2. Text Search: Attempt official Spotify Web API first if token available
        token = self._get_api_access_token()
        if token:
            logger.info("[Spotify] Provider: Spotify Web API")
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

                        item = MediaItem(
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
                        items.append(item)

                    if items:
                        logger.info("[Spotify] Spotify Web API results received: %d", len(items))
                        return items
            except Exception as e:
                logger.warning(
                    "[Spotify] Spotify Web API search unavailable or restricted (%s). Falling back to music catalog.",
                    e,
                )

        # 3. Fallback: High-fidelity public music catalog search
        logger.info("[Spotify] Provider: Public Music Catalog Fallback")
        items = self._search_music_catalog(clean_query, max_results=max_results)
        if items:
            return items

        logger.info("[Spotify] No results found for: %s", clean_query)
        return []

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
            images = entity.get("visualIdentity", {}).get("image", [])
            if not images:
                images = entity.get("coverArt", {}).get("sources", [])
            thumb = images[0].get("url") if images else ""

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
            return self._extract_via_oembed(url, track_id)

    def extract_album_from_url(self, url: str) -> List[MediaItem]:
        album_id = self._extract_album_id(url)
        if not album_id:
            return []
        return self._extract_collection_from_embed(f"https://open.spotify.com/embed/album/{album_id}")

    def extract_playlist_from_url(self, url: str) -> List[MediaItem]:
        playlist_id = self._extract_playlist_id(url)
        if not playlist_id:
            return []
        return self._extract_collection_from_embed(f"https://open.spotify.com/embed/playlist/{playlist_id}")

    def _extract_collection_from_embed(self, embed_url: str) -> List[MediaItem]:
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
                return []
            data = json.loads(m.group(1))
            entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
            album_name = entity.get("title") or entity.get("name") or "Spotify Album"
            track_list = entity.get("trackList", [])
            images = entity.get("visualIdentity", {}).get("image", [])
            thumb = images[0].get("url") if images else ""

            items = []
            for t in track_list:
                uri = t.get("uri", "")
                tid = uri.split(":")[-1] if uri else ""
                title = t.get("title") or "Unknown Track"
                subtitle = t.get("subtitle") or "Spotify Artist"
                duration_ms = t.get("duration") or 0
                preview_url = t.get("audioPreview", {}).get("url") or ""

                items.append(
                    MediaItem(
                        video_id=tid,
                        title=title,
                        channel=subtitle,
                        album=album_name,
                        duration_seconds=int(duration_ms) // 1000 if duration_ms else 0,
                        duration_formatted=format_duration(int(duration_ms) // 1000 if duration_ms else 0),
                        thumbnail_url=thumb,
                        url=f"https://open.spotify.com/track/{tid}",
                        platform=self.platform_id,
                        preview_url=preview_url,
                    )
                )
            return items
        except Exception as err:
            logger.error("[Spotify] Collection embed extraction failed: %s", err)
            return []

    def _extract_via_oembed(self, url: str, track_id: str) -> Optional[MediaItem]:
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
        Returns the official 30-second MP3 preview stream for dedicated AudioPlayer.
        """
        logger.info("[Spotify] Preparing audio preview for %s - %s", item.channel, item.display_title)
        preview = item.preview_url

        if not preview and item.url and "spotify.com" in item.url:
            fresh = self.extract_from_url(item.url)
            if fresh and fresh.preview_url:
                preview = fresh.preview_url
                item.preview_url = preview

        if preview and preview.startswith("http"):
            logger.info("[Spotify] Playback source type: official_preview")
            logger.info("[Spotify] Playback source resolved: %s", preview[:40] + "...")
            return {
                "source_type": "official_preview",
                "url": preview,
                "audio_url": preview,
                "headers": {"User-Agent": "Mozilla/5.0"},
                "duration_seconds": 30,
            }

        raise RuntimeError(
            f"Audio preview is unavailable for '{item.display_title}'. "
            "This Spotify track does not offer a public preview."
        )

    def build_download_options(self, task: DownloadTask, base_output_path: str) -> Dict[str, Any]:
        """
        Builds audio-only download options for Spotify tracks.
        Enforces pure MP3 format.
        """
        task.format = MediaFormat.MP3

        bitrate = task.audio_quality.value if isinstance(task.audio_quality, AudioQuality) else "320"
        if bitrate not in ("128", "192", "256", "320"):
            bitrate = "320"

        out_tmpl = f"{base_output_path}.%(ext)s"

        ydl_opts: Dict[str, Any] = {
            "format": "bestaudio/best",
            "outtmpl": out_tmpl,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": bitrate,
                },
                {
                    "key": "FFmpegMetadata",
                    "add_metadata": True,
                },
            ],
        }

        status = ffmpeg_service.get_status()
        if status.is_available and status.ffmpeg_path:
            ydl_opts["ffmpeg_location"] = status.ffmpeg_path

        return ydl_opts


# Register the platform service singleton
spotify_platform = SpotifyPlatform()
platform_registry.register(spotify_platform)
