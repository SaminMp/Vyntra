"""
Modern Search Bar component with enter trigger and direct URL recognition.
"""

from typing import Callable
import customtkinter as ctk

from vyntra.ui.theme import Theme


class SearchBar(ctk.CTkFrame):
    """Clean, high-aesthetic search input container with action buttons."""

    def __init__(self, master, on_search: Callable[[str], None], **kwargs):
        super().__init__(
            master,
            corner_radius=Theme.RADIUS_CARD,
            fg_color=Theme.BG_CARD,
            border_width=1,
            border_color=Theme.BORDER_CARD,
            **kwargs,
        )

        self.on_search = on_search
        self._is_searching = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Search Icon prefix
        self.icon_label = ctk.CTkLabel(
            self,
            text="🔍",
            font=(Theme.FONT_FAMILY, 15),
            text_color=Theme.TEXT_MUTED,
            width=32,
        )
        self.icon_label.grid(row=0, column=0, padx=(14, 4), pady=10, sticky="w")

        # Text Entry
        self.entry = ctk.CTkEntry(
            self,
            placeholder_text="Search YouTube by title or paste a video URL...",
            font=Theme.FONT_BODY,
            fg_color="transparent",
            text_color=Theme.TEXT_PRIMARY,
            placeholder_text_color=Theme.TEXT_MUTED,
            border_width=0,
            height=38,
        )
        self.entry.grid(row=0, column=1, padx=4, pady=6, sticky="ew")
        self.grid_columnconfigure(1, weight=1)

        # Clear Button
        self.clear_btn = ctk.CTkButton(
            self,
            text="✕",
            font=(Theme.FONT_FAMILY, 11, "bold"),
            width=28,
            height=28,
            corner_radius=14,
            fg_color="transparent",
            hover_color=Theme.BG_CARD_HOVER,
            text_color=Theme.TEXT_MUTED,
            command=self.clear,
        )
        self.clear_btn.grid(row=0, column=2, padx=(4, 8), pady=6, sticky="e")

        # Search Action Button
        self.search_btn = ctk.CTkButton(
            self,
            text="Search",
            font=Theme.FONT_SUBHEADER,
            width=100,
            height=36,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_PRIMARY,
            command=self._handle_search,
        )
        self.search_btn.grid(row=0, column=3, padx=(4, 8), pady=6, sticky="e")

        # Bind Enter Key
        self.entry.bind("<Return>", lambda e: self._handle_search())
        self.entry.bind("<KeyRelease>", self._on_text_change)

        self._update_clear_button_visibility()

    def _on_text_change(self, event=None):
        self._update_clear_button_visibility()

    def _update_clear_button_visibility(self):
        if self.entry.get().strip():
            self.clear_btn.grid(row=0, column=2, padx=(4, 8), pady=6, sticky="e")
        else:
            self.clear_btn.grid_remove()

    def clear(self):
        """Clears search input text."""
        self.entry.delete(0, "end")
        self._update_clear_button_visibility()
        self.entry.focus_set()

    def get_query(self) -> str:
        return self.entry.get().strip()

    def set_query(self, text: str):
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self._update_clear_button_visibility()

    def set_loading(self, loading: bool):
        """Toggles loading state on the search button."""
        self._is_searching = loading
        if loading:
            self.search_btn.configure(text="Searching...", state="disabled", fg_color=Theme.BG_MUTED)
            self.entry.configure(state="disabled")
        else:
            self.search_btn.configure(text="Search", state="normal", fg_color=Theme.PRIMARY)
            self.entry.configure(state="normal")
            self.entry.focus_set()

    def _handle_search(self):
        if self._is_searching:
            return
        query = self.get_query()
        if query and self.on_search:
            self.on_search(query)
