"""
YouTube search and metadata extraction service using yt-dlp.
"""

from concurrent.futures import ThreadPoolExecutor
import re
from typing import Callable, List, Optional
import yt_dlp

from vyntra.config import config_manager
from vyntra.models import SearchResult
from vyntra.services.youtube_service import youtube_service
from vyntra.utils.formatters import format_duration, format_view_count
from vyntra.utils.logger import logger


YOUTUBE_URL_PATTERNS = [
    re.compile(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|embed/|v/|shorts/|.+\?v=)?([^&=%\?]{11})'),
    re.compile(r'^(https?://)?(www\.)?youtu\.be/([^&=%\?]{11})'),
]


import threading


class SearchService:
    """Provides fast searching and metadata extraction from YouTube."""

    def __init__(self, max_workers: int = 2):
        self._max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None
        self._lock = threading.Lock()
        self._ensure_executor()

    def _ensure_executor(self):
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="SearchWorker")

    def shutdown(self, wait: bool = True, cancel_futures: bool = True) -> None:
        """Shuts down background search workers cleanly."""
        executor = None
        with self._lock:
            executor = self._executor
            self._executor = None

        if executor is not None:
            try:
                executor.shutdown(wait=wait, cancel_futures=cancel_futures)
            except TypeError:
                executor.shutdown(wait=wait)

    def reset(self) -> None:
        """Resets search service worker pool."""
        self.shutdown(wait=True)
        self._ensure_executor()

    def is_youtube_url(self, query: str) -> bool:
        """Checks whether the query is a direct YouTube video or shorts URL."""
        cleaned = query.strip()
        for pattern in YOUTUBE_URL_PATTERNS:
            if pattern.search(cleaned):
                return True
        return False

    def search(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """
        Executes search or direct URL extraction synchronously.

        Args:
            query: Free-text search terms or YouTube URL.
            max_results: Max items to return (defaults to config).

        Returns:
            List of parsed SearchResult objects.
        """
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        if max_results is None:
            max_results = config_manager.config.max_search_results

        is_direct_url = self.is_youtube_url(cleaned_query)

        # Use the unified yt-dlp options (SSL, proxy, user-agent, cookies) as base
        # to ensure consistent network behavior across all YouTube operations.
        ydl_opts = youtube_service.get_base_ydl_options(purpose="search")
        ydl_opts.update({
            "extract_flat": True if not is_direct_url else False,
            "skip_download": True,
            "ignoreerrors": True,
        })

        search_target = cleaned_query if is_direct_url else f"ytsearch{max_results}:{cleaned_query}"
        logger.info("Executing YouTube search for: '%s' (Direct URL: %s)", cleaned_query, is_direct_url)

        results: List[SearchResult] = []

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_target, download=False)
                if not info:
                    return []

                # If direct single video URL
                if "entries" not in info:
                    parsed = self._parse_entry(info)
                    if parsed:
                        results.append(parsed)
                else:
                    for entry in info.get("entries", []):
                        if entry:
                            parsed = self._parse_entry(entry)
                            if parsed:
                                results.append(parsed)

        except Exception as err:
            classified = youtube_service.classify_error(err)
            logger.error("Error during YouTube search: %s (classified: %s)", err, classified)
            raise RuntimeError(classified) from err

        logger.info("Search returned %d results for '%s'", len(results), cleaned_query)
        return results

    def search_async(
        self,
        query: str,
        on_success: Callable[[List[SearchResult]], None],
        on_error: Callable[[Exception], None],
        max_results: Optional[int] = None,
    ) -> None:
        """
        Executes search on a background worker thread.
        """
        def _worker():
            try:
                items = self.search(query, max_results)
                on_success(items)
            except Exception as err:
                on_error(err)

        self._executor.submit(_worker)

    def _parse_entry(self, entry: dict) -> Optional[SearchResult]:
        """Maps yt-dlp dictionary into a SearchResult instance."""
        video_id = entry.get("id")
        title = entry.get("title")

        if not video_id or not title:
            return None

        # Resolve duration
        duration_secs = entry.get("duration") or 0
        if isinstance(duration_secs, float):
            duration_secs = int(duration_secs)

        # Resolve views
        view_count = entry.get("view_count")

        # Resolve channel/uploader
        channel = entry.get("uploader") or entry.get("channel") or "Unknown Artist"

        # Resolve best thumbnail URL
        thumbnail_url = entry.get("thumbnail") or ""
        if not thumbnail_url and "thumbnails" in entry and entry["thumbnails"]:
            # Pick the last thumbnail (often highest resolution)
            thumbnail_url = entry["thumbnails"][-1].get("url", "")
        if not thumbnail_url:
            thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

        url = entry.get("webpage_url") or entry.get("url") or f"https://www.youtube.com/watch?v=dQw4w9WgXcQ".replace("dQw4w9WgXcQ", video_id)
        description = entry.get("description") or ""

        return SearchResult(
            video_id=video_id,
            title=title,
            channel=channel,
            duration_seconds=duration_secs,
            duration_formatted=format_duration(duration_secs),
            views=view_count,
            views_formatted=format_view_count(view_count),
            thumbnail_url=thumbnail_url,
            url=url,
            description=description,
            publish_date=entry.get("upload_date", ""),
        )

    def get_available_resolutions(self, video_id_or_url: str) -> List[str]:
        """
        Probes the video for available video stream resolutions using the unified YouTube service.
        Returns a sorted list of human-friendly labels, e.g.:
        ['Best (Auto)', '2160p (4K)', '1440p (2K)', '1080p (FHD)', '720p (HD)', '480p', '360p']
        Never returns fake fallbacks when probing fails.
        """
        resolutions, _ = youtube_service.get_available_resolutions(video_id_or_url)
        return resolutions

    def get_available_resolutions_async(
        self,
        video_id_or_url: str,
        on_result: Callable[..., None],
    ) -> None:
        """
        Asynchronously probes available resolutions on a worker thread.
        Supports both on_result(resolutions) and on_result(resolutions, error_message).
        """
        def _worker():
            resolutions, err_msg = youtube_service.get_available_resolutions(video_id_or_url)
            try:
                on_result(resolutions, err_msg)
            except TypeError:
                on_result(resolutions)

        self._ensure_executor()
        if self._executor is not None:
            self._executor.submit(_worker)


# Global singleton instance
search_service = SearchService()

