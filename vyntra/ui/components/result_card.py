"""
Interactive search result card component with thumbnail, metadata, and selection state.
"""

from typing import Callable, Optional
import customtkinter as ctk

from vyntra.models import SearchResult
from vyntra.services.image_service import image_service
from vyntra.ui.theme import Theme


class ResultCard(ctk.CTkFrame):
    """Card representing a single YouTube search result."""

    THUMBNAIL_SIZE = (150, 84)  # Standard 16:9 aspect ratio

    def __init__(
        self,
        master,
        result: SearchResult,
        on_select: Callable[[SearchResult], None],
        **kwargs,
    ):
        super().__init__(
            master,
            corner_radius=Theme.RADIUS_CARD,
            fg_color=Theme.BG_CARD,
            border_width=1,
            border_color=Theme.BORDER_CARD,
            cursor="hand2",
            **kwargs,
        )

        self.result = result
        self.on_select = on_select
        self._is_selected = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 1. Thumbnail Container (Left)
        self.thumb_frame = ctk.CTkFrame(
            self,
            width=self.THUMBNAIL_SIZE[0],
            height=self.THUMBNAIL_SIZE[1],
            corner_radius=Theme.RADIUS_CARD,
            fg_color="#000000",
        )
        self.thumb_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsw")
        self.thumb_frame.grid_propagate(False)

        # Thumbnail Image Label
        self.thumb_label = ctk.CTkLabel(self.thumb_frame, text="", image=None)
        self.thumb_label.place(relx=0.5, rely=0.5, anchor="center")

        # Duration Badge (Bottom-Right overlay)
        if self.result.duration_formatted and self.result.duration_formatted != "00:00":
            self.duration_badge = ctk.CTkLabel(
                self.thumb_frame,
                text=f" {self.result.duration_formatted} ",
                font=Theme.FONT_BADGE,
                text_color="#FFFFFF",
                fg_color="#111827",
                corner_radius=Theme.RADIUS_BADGE,
            )
            self.duration_badge.place(relx=0.95, rely=0.92, anchor="se")

        # 2. Metadata Section (Center)
        self.info_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.info_frame.grid(row=0, column=1, padx=(6, 12), pady=10, sticky="nsew")
        self.info_frame.grid_columnconfigure(0, weight=1)

        # Title Label
        self.title_label = ctk.CTkLabel(
            self.info_frame,
            text=self.result.display_title,
            font=Theme.FONT_SUBHEADER,
            text_color=Theme.TEXT_PRIMARY,
            anchor="w",
            justify="left",
            wraplength=480,
        )
        self.title_label.grid(row=0, column=0, sticky="nw", pady=(0, 4))

        # Channel Label
        self.channel_label = ctk.CTkLabel(
            self.info_frame,
            text=f"👤 {self.result.channel}",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_ACCENT,
            anchor="w",
        )
        self.channel_label.grid(row=1, column=0, sticky="w", pady=(0, 2))

        # Views & Duration Meta line
        meta_parts = []
        if self.result.views_formatted and self.result.views_formatted != "N/A":
            meta_parts.append(f"👁️ {self.result.views_formatted}")
        if self.result.duration_formatted:
            meta_parts.append(f"⏱️ {self.result.duration_formatted}")

        meta_text = "   •   ".join(meta_parts)
        self.meta_label = ctk.CTkLabel(
            self.info_frame,
            text=meta_text,
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            anchor="w",
        )
        self.meta_label.grid(row=2, column=0, sticky="w")

        # 3. Action / Selection Badge (Right)
        self.action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.action_frame.grid(row=0, column=2, padx=(6, 14), pady=10, sticky="e")

        self.select_btn = ctk.CTkButton(
            self.action_frame,
            text="Select",
            font=Theme.FONT_CAPTION,
            width=76,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._handle_click,
        )
        self.select_btn.pack(side="right", padx=2)

        # Bind hover and click events across all child widgets
        self._bind_events([
            self,
            self.info_frame,
            self.title_label,
            self.channel_label,
            self.meta_label,
            self.thumb_frame,
            self.thumb_label,
        ])

        # Load Thumbnail asynchronously
        self._load_thumbnail()

    def _bind_events(self, widgets):
        for w in widgets:
            w.bind("<Button-1>", lambda e: self._handle_click())
            w.bind("<Enter>", lambda e: self._on_hover(True))
            w.bind("<Leave>", lambda e: self._on_hover(False))

    def _load_thumbnail(self):
        """Asynchronously pulls thumbnail into label."""
        def _on_success(ctk_img):
            try:
                # Thread-safe UI update
                self.after(0, lambda: self.thumb_label.configure(image=ctk_img))
            except Exception:
                pass

        placeholder = image_service.get_thumbnail_async(
            url=self.result.thumbnail_url,
            size=self.THUMBNAIL_SIZE,
            on_success=_on_success,
        )
        self.thumb_label.configure(image=placeholder)

    def _on_hover(self, is_hover: bool):
        if not self._is_selected:
            if is_hover:
                self.configure(fg_color=Theme.BG_CARD_HOVER, border_color=Theme.BORDER_HIGHLIGHT)
            else:
                self.configure(fg_color=Theme.BG_CARD, border_color=Theme.BORDER_CARD)

    def set_selected(self, selected: bool):
        """Updates the visual state when card is selected or deselected."""
        self._is_selected = selected
        if selected:
            self.configure(
                fg_color=Theme.BG_CARD_SELECTED,
                border_color=Theme.BORDER_SELECTED,
                border_width=2,
            )
            self.select_btn.configure(
                text="✓ Selected",
                fg_color=Theme.PRIMARY,
                hover_color=Theme.PRIMARY_HOVER,
            )
        else:
            self.configure(
                fg_color=Theme.BG_CARD,
                border_color=Theme.BORDER_CARD,
                border_width=1,
            )
            self.select_btn.configure(
                text="Select",
                fg_color=Theme.BG_MUTED,
                hover_color=Theme.PRIMARY_HOVER,
            )

    def _handle_click(self):
        if self.on_select:
            self.on_select(self.result)
