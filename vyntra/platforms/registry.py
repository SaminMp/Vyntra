"""
Platform registry for discovering, registering, and retrieving platform services.
"""

from typing import Dict, List, Optional
from vyntra.models import Platform
from vyntra.platforms.base import BasePlatformService
from vyntra.utils.logger import logger


class PlatformRegistry:
    """Central registry for all supported media platform services in Vyntra."""

    def __init__(self):
        self._platforms: Dict[str, BasePlatformService] = {}

    def register(self, platform: BasePlatformService) -> None:
        """Registers a platform service instance."""
        pid = platform.platform_id.lower()
        self._platforms[pid] = platform
        logger.debug("[Registry] Registered platform service: %s (%s)", platform.capabilities.display_name, pid)

    def _ensure_defaults(self) -> None:
        """Loads built-in platforms if registry is currently empty."""
        if len(self._platforms) < 4:
            try:
                import vyntra.platforms.youtube
                import vyntra.platforms.instagram
                import vyntra.platforms.tiktok
                import vyntra.platforms.spotify
            except Exception as err:
                logger.debug("[Registry] Autoload platforms notice: %s", err)

    def get(self, platform_id: Optional[str] = None) -> BasePlatformService:
        """
        Retrieves the platform service for the given ID.
        Defaults to YouTube if not specified or unrecognized.
        """
        self._ensure_defaults()
        if platform_id:
            pid = platform_id.lower()
            if pid in self._platforms:
                return self._platforms[pid]
        # Fallback to YouTube
        youtube = self._platforms.get(Platform.YOUTUBE.value)
        if youtube:
            return youtube
        if self._platforms:
            return next(iter(self._platforms.values()))
        raise RuntimeError("No platform services have been registered in PlatformRegistry.")

    def list_platforms(self) -> List[BasePlatformService]:
        """Returns all registered platform services."""
        return list(self._platforms.values())

    def detect_platform_from_url(self, url: str) -> Optional[BasePlatformService]:
        """Inspects URL to find which platform service can handle it."""
        if not url:
            return None
        for platform in self._platforms.values():
            if platform.can_handle_url(url):
                return platform
        return None

    def shutdown_all(self, wait: bool = True, cancel_futures: bool = True) -> None:
        """Shuts down executors across all registered platform services."""
        for platform in self._platforms.values():
            try:
                platform.shutdown(wait=wait, cancel_futures=cancel_futures)
            except Exception as err:
                logger.debug("[Registry] Error shutting down platform %s: %s", platform.platform_id, err)


# Global singleton registry
platform_registry = PlatformRegistry()
