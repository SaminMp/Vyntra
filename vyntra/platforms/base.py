"""
Abstract base class and capability definitions for Vyntra media platforms.
"""

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from vyntra.models import DownloadTask, MediaItem, PlatformCapabilities
from vyntra.utils.logger import logger


import threading


class BasePlatformService(ABC):
    """
    Standard contract that every media platform service in Vyntra must implement.
    Ensures consistent behavior across YouTube, Instagram, TikTok, and Spotify.
    """

    def __init__(self):
        self._executor: Optional[ThreadPoolExecutor] = None
        self._lock = threading.Lock()
        self._ensure_executor()

    def _ensure_executor(self):
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix=f"{self.platform_id.capitalize()}Worker")

    def shutdown(self, wait: bool = True, cancel_futures: bool = True) -> None:
        """Shuts down background platform workers cleanly."""
        executor = None
        with self._lock:
            executor = self._executor
            self._executor = None

        if executor is not None:
            try:
                executor.shutdown(wait=wait, cancel_futures=cancel_futures)
            except TypeError:
                executor.shutdown(wait=wait)

    @property
    @abstractmethod
    def platform_id(self) -> str:
        """Unique identifier for the platform (e.g. 'youtube', 'instagram', 'tiktok', 'spotify')."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> PlatformCapabilities:
        """Declared platform capabilities and feature support."""
        pass

    @abstractmethod
    def can_handle_url(self, url: str) -> bool:
        """Returns True if the given URL belongs to or can be processed by this platform."""
        pass

    def search(self, query: str, max_results: int = 12) -> List[MediaItem]:
        """
        Synchronously searches the platform for content.
        Raises NotImplementedError if capabilities.supports_search is False.
        """
        raise NotImplementedError(f"Search is not supported by {self.capabilities.display_name}")

    def search_async(
        self,
        query: str,
        on_success: Callable[[List[MediaItem]], None],
        on_error: Callable[[Exception], None],
        max_results: int = 12,
    ) -> None:
        """Executes platform search asynchronously on a worker thread."""
        def _task():
            try:
                results = self.search(query=query, max_results=max_results)
                on_success(results)
            except Exception as e:
                logger.error("[%s] Search error: %s", self.capabilities.display_name, e)
                on_error(e)

        self._ensure_executor()
        if self._executor is not None:
            self._executor.submit(_task)

    def extract_from_url(self, url: str) -> Optional[MediaItem]:
        """
        Synchronously extracts media item metadata from a direct platform URL.
        """
        raise NotImplementedError(f"URL extraction is not implemented by {self.capabilities.display_name}")

    def extract_from_url_async(
        self,
        url: str,
        on_success: Callable[[MediaItem], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        """Executes URL extraction asynchronously on a worker thread."""
        def _task():
            try:
                item = self.extract_from_url(url=url)
                if item is None:
                    raise ValueError(f"Could not extract media from URL: {url}")
                on_success(item)
            except Exception as e:
                logger.error("[%s] URL extraction error: %s", self.capabilities.display_name, e)
                on_error(e)

        self._ensure_executor()
        if self._executor is not None:
            self._executor.submit(_task)

    @abstractmethod
    def prepare_playback_stream(self, item: MediaItem) -> Dict[str, Any]:
        """
        Resolves live playback stream source(s) and HTTP headers for SynchronizedMediaPlayer.
        Returns a dictionary compatible with SynchronizedMediaPlayer:
        e.g. {'url': stream_url, 'headers': {...}} or {'video_url': ..., 'audio_url': ...}
        """
        pass

    @abstractmethod
    def build_download_options(self, task: DownloadTask, out_base_without_ext: str) -> dict:
        """
        Constructs yt-dlp / postprocessor options dictionary for this platform's download task.
        """
        pass
