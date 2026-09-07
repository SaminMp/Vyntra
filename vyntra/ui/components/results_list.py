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
        self._cards: List[ResultCard] = []
        self._selected_card: Optional[ResultCard] = None

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

        for idx, result in enumerate(results):
            card = ResultCard(
                self,
                result=result,
                on_select=self._handle_card_selected,
                on_preview=self.on_preview,
                on_watch_later_changed=self.on_watch_later_changed,
            )
            card.pack(fill="x", padx=6, pady=4)
            self._cards.append(card)

            # Auto-select the first result by default for convenience
            if idx == 0:
                self._select_card(card)

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
        for child in self.winfo_children():
            child.destroy()
