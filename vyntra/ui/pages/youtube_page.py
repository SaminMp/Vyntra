"""
Dedicated YouTube Platform Page for Vyntra.
Preserves 100% of YouTube search, playback, quality selection, and downloading.
Enhanced with prominent header banner and generation lifecycle safety.
"""

from typing import List, Optional
import customtkinter as ctk

from vyntra.models import DownloadTask, MediaFormat, MediaItem, ProgressInfo, SearchResult
from vyntra.platforms.youtube.service import youtube_platform
from vyntra.services.search_service import search_service
from vyntra.ui.components.download_panel import DownloadPanel
from vyntra.ui.components.platform_selector import PLATFORM_METADATA
from vyntra.ui.components.results_list import ResultsList
from vyntra.ui.components.search_bar import SearchBar
from vyntra.ui.pages.base_page import BasePlatformPage
from vyntra.ui.theme import Theme


class YouTubePage(BasePlatformPage):
    """
    Dedicated view for searching, watching, and downloading YouTube content.
    """

    def __init__(self, master, app, **kwargs):
        super().__init__(master, app, platform_service=youtube_platform, **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # Results list expands

        # 0. Prominent Header Banner
        self._build_header()

        # 1. Search Bar
        self.search_container = ctk.CTkFrame(self, fg_color="transparent")
        self.search_container.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 8))
        self.search_container.grid_columnconfigure(0, weight=1)

        self.search_bar = SearchBar(self.search_container, on_search=self._handle_search)
        self.search_bar.grid(row=0, column=0, sticky="ew")

        # 2. Results List
        self.results_list = ResultsList(
            self,
            on_result_selected=self._handle_result_selected,
            on_preview=self._handle_preview,
            on_watch_later_changed=self.app._update_watch_later_badge,
        )
        self.results_list.grid(row=2, column=0, sticky="nsew", padx=16, pady=4)

        # 3. Download Panel
        self.download_panel = DownloadPanel(
            self,
            on_download=self.app._handle_start_download,
            on_cancel=self.app._handle_cancel_download,
        )
        self.download_panel.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 16))

    def _build_header(self):
        """Prominent platform branding banner with title and capability subtitle."""
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))

        meta = PLATFORM_METADATA.get("youtube")
        icon = meta.icon if meta else "▶"
        subtitle_text = meta.subtitle if meta else "Search, watch and download videos with hardware A/V sync"

        title = ctk.CTkLabel(
            header_frame,
            text=f"{icon}  YouTube",
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_PRIMARY,
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            header_frame,
            text=subtitle_text,
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_SECONDARY,
        )
        subtitle.pack(anchor="w", pady=(2, 0))

    def _handle_search(self, query: str):
        gen = self.next_generation()
        self.search_bar.set_loading(True)
        self.results_list.show_loading_state(query)

        def _on_success(results: List[MediaItem]):
            self.safe_after(0, lambda: self._display_results(results, gen))

        def _on_error(err: Exception):
            self.safe_after(0, lambda: self._display_error(err, gen))

        self.platform_service.search_async(
            query=query,
            on_success=_on_success,
            on_error=_on_error,
        )

    def _display_results(self, results: List[MediaItem], generation: int):
        if not self.is_generation_current(generation):
            return
        self.search_bar.set_loading(False)
        self.results_list.display_results(results)

    def _display_error(self, err: Exception, generation: int):
        if not self.is_generation_current(generation):
            return
        self.search_bar.set_loading(False)
        self.results_list.show_error_state(f"Search failed: {str(err)}")
        self.app.status_banner.show_error(f"Search failed: {str(err)}")

    def _handle_result_selected(self, result: MediaItem):
        self.download_panel.set_selected_result(result)

    def _handle_preview(self, result: MediaItem):
        self.app._handle_play_video(result)

    def update_progress(self, prog: ProgressInfo):
        if self.download_panel.winfo_exists():
            self.download_panel.update_progress(prog)

    def set_downloading(self, is_downloading: bool):
        if self.download_panel.winfo_exists():
            self.download_panel.set_downloading(is_downloading)
