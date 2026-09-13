"""
Abstract base class for dedicated platform pages in Vyntra.
Provides comprehensive lifecycle management, generation tokens, and timer cancellation
to prevent destroyed-widget TclErrors and race conditions during platform switching.
"""

from abc import ABC, abstractmethod
from typing import Callable, List, Optional
import customtkinter as ctk

from vyntra.models import PlatformCapabilities
from vyntra.platforms.base import BasePlatformService
from vyntra.ui.theme import Theme
from vyntra.utils.logger import logger


class BasePlatformPage(ctk.CTkFrame, ABC):
    """
    Base class for dedicated platform view pages.
    Provides standard layout hooks, platform capability awareness,
    and robust lifecycle management for asynchronous operations.
    """

    def __init__(self, master, app, platform_service: BasePlatformService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self.platform_service = platform_service

        self._is_active: bool = False
        self._search_generation: int = 0
        self._pending_after_ids: List[str] = []

    @property
    def platform_id(self) -> str:
        return self.platform_service.platform_id

    @property
    def capabilities(self) -> PlatformCapabilities:
        return self.platform_service.capabilities

    @property
    def is_page_active(self) -> bool:
        return self._is_active and bool(self.winfo_exists())

    def next_generation(self) -> int:
        """Increments and returns the next operation generation token."""
        self._search_generation += 1
        return self._search_generation

    def is_generation_current(self, generation: int) -> bool:
        """Checks if a background result corresponds to the latest operation."""
        return self.is_page_active and (generation == self._search_generation)

    def safe_after(self, delay_ms: int, callback: Callable[[], None]) -> Optional[str]:
        """
        Schedules a callback via Tkinter .after() with tracking and automatic lifecycle checking.
        If the page is destroyed or inactive when the timer fires, the callback is safely ignored.
        """
        if not self.winfo_exists():
            return None

        after_id: Optional[str] = None

        def _safe_wrapper():
            if after_id in self._pending_after_ids:
                self._pending_after_ids.remove(after_id)
            if self.is_page_active:
                try:
                    callback()
                except Exception as e:
                    logger.debug("[Page:%s] Callback execution error: %s", self.platform_id, e)

        after_id = self.after(delay_ms, _safe_wrapper)
        self._pending_after_ids.append(after_id)
        return after_id

    def cancel_pending_afters(self):
        """Cancels all pending scheduled after callbacks."""
        for aid in list(self._pending_after_ids):
            try:
                self.after_cancel(aid)
            except Exception:
                pass
        self._pending_after_ids.clear()

    def activate(self):
        """Called when this page becomes the active visible page."""
        self._is_active = True

    def deactivate(self):
        """Called when switching away from this page. Invalidates pending work."""
        self._is_active = False
        self.next_generation()  # Invalidate any in-flight background operations
        self.cancel_pending_afters()

    def destroy(self):
        """Clean teardown on widget destruction."""
        self.deactivate()
        super().destroy()
