"""
Scrollable container for search result cards with loading and empty state handling.
"""

from typing import Callable, Dict, List, Optional
import customtkinter as ctk

from vyntra.models import SearchResult
from vyntra.ui.components.result_card import ResultCard
from vyntra.ui.theme import Theme


class ResultsList(ctk.CTkScrollableFrame):
    """Scrollable list of search results with state management."""

    def __init__(
        self,
        master,
        on_result_selected: Callable[[SearchResult], None],
        on_preview: Optional[Callable[[SearchResult], None]] = None,
        on_watch_later_changed: Optional[Callable[[], None]] = None,
        on_download_selection_changed: Optional[Callable[[List[SearchResult]], None]] = None,
        **kwargs,
    ):
        super().__init__(
            master,
            corner_radius=Theme.RADIUS_CARD,
            fg_color=Theme.BG_MAIN,
            border_width=0,
            **kwargs,
        )

        self.on_result_selected = on_result_selected
        self.on_preview = on_preview
        self.on_watch_later_changed = on_watch_later_changed
        self.on_download_selection_changed = on_download_selection_changed
        self._cards: List[ResultCard] = []
        self._selected_card: Optional[ResultCard] = None
        self._toolbar_frame: Optional[ctk.CTkFrame] = None
        self._selection_summary_lbl: Optional[ctk.CTkLabel] = None

        self.grid_columnconfigure(0, weight=1)

        # Show initial empty placeholder
        self.show_empty_state()

    def show_empty_state(self, message: str = "Search YouTube above for songs, soundtracks, or videos"):
        """Displays friendly empty state illustration."""
        self._clear_widgets()

        empty_frame = ctk.CTkFrame(self, fg_color="transparent")
        empty_frame.pack(fill="both", expand=True, pady=60)

        icon = ctk.CTkLabel(
            empty_frame,
            text="🎧",
            font=(Theme.FONT_FAMILY, 48),
        )
        icon.pack(pady=(0, 10))

        title = ctk.CTkLabel(
            empty_frame,
            text="Explore Media on YouTube",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_PRIMARY,
        )
        title.pack(pady=(0, 6))

        subtitle = ctk.CTkLabel(
            empty_frame,
            text=message,
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED,
            wraplength=400,
        )
        subtitle.pack()

    def show_loading_state(self, query: str):
        """Displays searching status."""
        self._clear_widgets()

        loading_frame = ctk.CTkFrame(self, fg_color="transparent")
        loading_frame.pack(fill="both", expand=True, pady=60)

        icon = ctk.CTkLabel(
            loading_frame,
            text="⏳",
            font=(Theme.FONT_FAMILY, 40),
        )
        icon.pack(pady=(0, 10))

        title = ctk.CTkLabel(
            loading_frame,
            text=f"Searching for '{query}'...",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_PRIMARY,
        )
        title.pack(pady=(0, 6))

        subtitle = ctk.CTkLabel(
            loading_frame,
            text="Fetching video metadata, thumbnails, and durations from YouTube...",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED,
        )
        subtitle.pack()

    def show_error_state(self, error_message: str):
        """Displays error message."""
        self._clear_widgets()

        err_frame = ctk.CTkFrame(self, fg_color="transparent")
        err_frame.pack(fill="both", expand=True, pady=60)

        icon = ctk.CTkLabel(
            err_frame,
            text="⚠️",
            font=(Theme.FONT_FAMILY, 40),
        )
        icon.pack(pady=(0, 10))

        title = ctk.CTkLabel(
            err_frame,
            text="Search Failed",
            font=Theme.FONT_HEADER,
            text_color=Theme.ERROR,
        )
        title.pack(pady=(0, 6))

        subtitle = ctk.CTkLabel(
            err_frame,
            text=error_message,
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED,
            wraplength=500,
        )
        subtitle.pack()

    def display_results(self, results: List[SearchResult]):
        """Renders list of SearchResult items as ResultCard components."""
        self._clear_widgets()

        if not results:
            self.show_empty_state("No matching videos found. Try a different search term.")
            return

        # Top batch actions toolbar
        self._toolbar_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._toolbar_frame.pack(fill="x", padx=10, pady=(2, 8))
        self._toolbar_frame.grid_columnconfigure(2, weight=1)

        select_all_btn = ctk.CTkButton(
            self._toolbar_frame,
            text="☑ Select All",
            font=Theme.FONT_CAPTION,
            width=90,
            height=28,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.PRIMARY_HOVER,
            command=self.select_all,
        )
        select_all_btn.grid(row=0, column=0, padx=(0, 8), sticky="w")

        deselect_all_btn = ctk.CTkButton(
            self._toolbar_frame,
            text="☐ Deselect All",
            font=Theme.FONT_CAPTION,
            width=95,
            height=28,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self.deselect_all,
        )
        deselect_all_btn.grid(row=0, column=1, padx=(0, 12), sticky="w")

        self._selection_summary_lbl = ctk.CTkLabel(
            self._toolbar_frame,
            text=f"{len(results)} videos found • 0 selected for download",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
        )
        self._selection_summary_lbl.grid(row=0, column=2, sticky="e")

        for idx, result in enumerate(results):
            card = ResultCard(
                self,
                result=result,
                on_select=self._handle_card_selected,
                on_preview=self.on_preview,
                on_watch_later_changed=self.on_watch_later_changed,
                on_download_config_changed=self._handle_download_config_changed,
            )
            card.pack(fill="x", padx=6, pady=4)
            self._cards.append(card)

            # Auto-select the first result by default for convenience
            if idx == 0:
                self._select_card(card)

    def get_selected_download_items(self) -> List[SearchResult]:
        """Returns all results checked for batch download."""
        return [card.result for card in self._cards if getattr(card.result, "selected_for_download", False)]

    def select_all(self):
        """Checks all cards for batch download."""
        for card in self._cards:
            card.set_download_checked(True)
        self._handle_download_config_changed()

    def deselect_all(self):
        """Unchecks all cards."""
        for card in self._cards:
            card.set_download_checked(False)
        self._handle_download_config_changed()

    def _handle_download_config_changed(self, result: Optional[SearchResult] = None):
        """Updates summary and notifies parent view of selection change."""
        selected_items = self.get_selected_download_items()
        count = len(selected_items)
        total = len(self._cards)
        if self._selection_summary_lbl and self._selection_summary_lbl.winfo_exists():
            self._selection_summary_lbl.configure(
                text=f"{total} videos found • {count} selected for download"
            )
        if self.on_download_selection_changed:
            self.on_download_selection_changed(selected_items)

    def _handle_card_selected(self, result: SearchResult):
        for card in self._cards:
            if card.result.video_id == result.video_id:
                self._select_card(card)
                break

    def _select_card(self, card: ResultCard):
        if self._selected_card and self._selected_card != card:
            self._selected_card.set_selected(False)

        self._selected_card = card
        card.set_selected(True)

        if self.on_result_selected:
            self.on_result_selected(card.result)

    def _clear_widgets(self):
        self._selected_card = None
        self._cards.clear()
        self._toolbar_frame = None
        self._selection_summary_lbl = None
        for child in self.winfo_children():
            child.destroy()
