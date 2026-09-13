"""
YouTube platform service implementation wrapping existing Vyntra YouTube services.
Preserves 100% of existing search, stream extraction, dynamic format probing, and downloading.
"""

from typing import Any, Callable, Dict, List, Optional
import re

from vyntra.models import DownloadTask, MediaItem, Platform, PlatformCapabilities
from vyntra.platforms.base import BasePlatformService
from vyntra.platforms.registry import platform_registry
from vyntra.services.search_service import search_service
from vyntra.services.youtube_service import youtube_service
from vyntra.utils.logger import logger


class YouTubePlatform(BasePlatformService):
    """Platform service managing YouTube media extraction, search, and download configuration."""

    YOUTUBE_URL_REGEX = re.compile(
        r"^(https?://)?(www\.|m\.)?(youtube\.com/(watch\?v=|shorts/|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})"
    )

    @property
    def platform_id(self) -> str:
        return Platform.YOUTUBE.value

    @property
    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            platform_id=self.platform_id,
            display_name="YouTube",
            icon="🔴",
            supports_search=True,
            supports_url_input=True,
            supports_video_playback=True,
            supports_audio_preview=True,
            supports_mp4=True,
            supports_mp3=True,
            supports_video_quality=True,
            supports_audio_quality=True,
        )

    def can_handle_url(self, url: str) -> bool:
        if not url:
            return False
        return bool(self.YOUTUBE_URL_REGEX.search(url.strip()))

    def search(self, query: str, max_results: int = 12) -> List[MediaItem]:
        results = search_service.search(query=query, max_results=max_results)
        for r in results:
            r.platform = self.platform_id
        return results

    def search_async(
        self,
        query: str,
        on_success: Callable[[List[MediaItem]], None],
        on_error: Callable[[Exception], None],
        max_results: int = 12,
    ) -> None:
        def _wrapper_success(results: List[MediaItem]):
            for r in results:
                r.platform = self.platform_id
            on_success(results)

        search_service.search_async(
            query=query,
            on_success=_wrapper_success,
            on_error=on_error,
            max_results=max_results,
        )

    def extract_from_url(self, url: str) -> Optional[MediaItem]:
        results = search_service.search(query=url.strip(), max_results=1)
        if results:
            item = results[0]
            item.platform = self.platform_id
            return item
        return None

    def prepare_playback_stream(self, item: MediaItem) -> Dict[str, Any]:
        """Extracts playable dual-stream or direct stream using YouTubeExtractionService."""
        stream_data = youtube_service.prepare_playback_stream(item.video_id)
        return stream_data

    def build_download_options(self, task: DownloadTask, out_base_without_ext: str) -> dict:
        """Constructs yt-dlp download options using existing YouTubeService logic."""
        return youtube_service.build_download_options(task, out_base_without_ext)


# Instantiate and register
youtube_platform = YouTubePlatform()
platform_registry.register(youtube_platform)
