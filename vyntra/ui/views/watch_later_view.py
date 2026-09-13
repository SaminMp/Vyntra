"""
Dedicated Watch Later / Saved Videos View for Vyntra.
"""

from typing import Callable, Optional
import customtkinter as ctk

from vyntra.models import MediaFormat, SearchResult
from vyntra.services.image_service import image_service
from vyntra.services.watch_later_service import WatchLaterItem, watch_later_service
from vyntra.ui.theme import Theme


class WatchLaterCard(ctk.CTkFrame):
    """Card representing a saved video in the Watch Later library."""

    THUMBNAIL_SIZE = (150, 84)

    def __init__(
        self,
        master,
        item: WatchLaterItem,
        on_watch: Callable[[SearchResult], None],
        on_download: Callable[[SearchResult, MediaFormat], None],
        on_remove: Callable[[str], None],
        **kwargs,
    ):
        super().__init__(
            master,
            corner_radius=Theme.RADIUS_CARD,
            fg_color=Theme.BG_CARD,
            border_width=1,
            border_color=Theme.BORDER_CARD,
            **kwargs,
        )

        self.item = item
        self.result = item.result
        self.on_watch = on_watch
        self.on_download = on_download
        self.on_remove = on_remove

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

        self.thumb_label = ctk.CTkLabel(self.thumb_frame, text="", image=None)
        self.thumb_label.place(relx=0.5, rely=0.5, anchor="center")

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

        self.title_label = ctk.CTkLabel(
            self.info_frame,
            text=self.result.display_title,
            font=Theme.FONT_SUBHEADER,
            text_color=Theme.TEXT_PRIMARY,
            anchor="w",
            justify="left",
            wraplength=380,
        )
        self.title_label.grid(row=0, column=0, sticky="nw", pady=(0, 4))

        platform_name = str(getattr(self.result, "platform", "youtube") or "youtube").lower()
        platform_icons = {
            "youtube": "🔴 YouTube",
            "instagram": "📸 Instagram",
            "tiktok": "🎵 TikTok",
            "spotify": "🟢 Spotify",
        }
        platform_badge_text = platform_icons.get(platform_name, "🔴 YouTube")

        self.channel_label = ctk.CTkLabel(
            self.info_frame,
            text=f"{platform_badge_text}  •  👤 {self.result.channel}",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_ACCENT,
            anchor="w",
        )
        self.channel_label.grid(row=1, column=0, sticky="w", pady=(0, 2))

        meta_parts = []
        if self.result.views_formatted and self.result.views_formatted != "N/A":
            meta_parts.append(f"👁️ {self.result.views_formatted}")
        meta_parts.append(f"📅 Saved: {self.item.added_at}")

        self.meta_label = ctk.CTkLabel(
            self.info_frame,
            text="   •   ".join(meta_parts),
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            anchor="w",
        )
        self.meta_label.grid(row=2, column=0, sticky="w")

        # 3. Action Buttons (Right)
        self.action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.action_frame.grid(row=0, column=2, padx=(6, 14), pady=10, sticky="e")

        # Watch / Preview button
        play_label = "▶ Preview" if platform_name == "spotify" else "▶ Watch"
        self.watch_btn = ctk.CTkButton(
            self.action_frame,
            text=play_label,
            font=Theme.FONT_CAPTION,
            width=78,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.ACCENT_CYAN,
            command=lambda: self.on_watch(self.result),
        )
        self.watch_btn.pack(side="left", padx=(0, 6))

        # Download MP3 button
        self.mp3_btn = ctk.CTkButton(
            self.action_frame,
            text="⬇ MP3",
            font=Theme.FONT_CAPTION,
            width=68,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.PRIMARY,
            command=lambda: self.on_download(self.result, MediaFormat.MP3),
        )
        self.mp3_btn.pack(side="left", padx=(0, 6))

        # Download MP4 button (strictly excluded for Spotify)
        if platform_name != "spotify":
            self.mp4_btn = ctk.CTkButton(
                self.action_frame,
                text="⬇ MP4",
                font=Theme.FONT_CAPTION,
                width=68,
                height=32,
                corner_radius=Theme.RADIUS_BUTTON,
                fg_color=Theme.BG_MUTED,
                hover_color=Theme.PRIMARY_HOVER,
                command=lambda: self.on_download(self.result, MediaFormat.MP4),
            )
            self.mp4_btn.pack(side="left", padx=(0, 6))

        # Remove button
        self.remove_btn = ctk.CTkButton(
            self.action_frame,
            text="✕",
            font=Theme.FONT_BODY_BOLD,
            width=32,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.ERROR,
            command=lambda: self.on_remove(self.result.video_id),
        )
        self.remove_btn.pack(side="left")

        # Load Thumbnail
        self._load_thumbnail()

    def _load_thumbnail(self):
        def _on_success(ctk_img):
            try:
                self.after(0, lambda: self.thumb_label.configure(image=ctk_img))
            except Exception:
                pass

        placeholder = image_service.get_thumbnail_async(
            url=self.result.thumbnail_url,
            size=self.THUMBNAIL_SIZE,
            on_success=_on_success,
        )
        self.thumb_label.configure(image=placeholder)


class WatchLaterView(ctk.CTkScrollableFrame):
    """Scrollable view displaying all saved Watch Later videos with playback and download actions."""

    def __init__(
        self,
        master,
        on_watch: Callable[[SearchResult], None],
        on_download: Callable[[SearchResult, MediaFormat], None],
        on_back: Callable[[], None],
        on_count_changed: Optional[Callable[[int], None]] = None,
        **kwargs,
    ):
        super().__init__(
            master,
            corner_radius=Theme.RADIUS_CARD,
            fg_color=Theme.BG_MAIN,
            border_width=0,
            **kwargs,
        )

        self.on_watch = on_watch
        self.on_download = on_download
        self.on_back = on_back
        self.on_count_changed = on_count_changed

        self.grid_columnconfigure(0, weight=1)
        self.refresh()

    def refresh(self):
        """Reloads all saved items from database and refreshes UI cards."""
        for child in self.winfo_children():
            child.destroy()

        items = watch_later_service.get_all()
        if self.on_count_changed:
            self.on_count_changed(len(items))

        # Header Bar inside view
        header_bar = ctk.CTkFrame(self, fg_color="transparent")
        header_bar.pack(fill="x", padx=8, pady=(4, 12))
        header_bar.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(header_bar, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")

        title_lbl = ctk.CTkLabel(
            title_box,
            text=f"⭐ Watch Later ({len(items)})",
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_PRIMARY,
        )
        title_lbl.pack(side="left")

        back_btn = ctk.CTkButton(
            header_bar,
            text="← Back to Search",
            font=Theme.FONT_CAPTION,
            width=130,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_CARD,
            hover_color=Theme.BG_CARD_HOVER,
            command=self.on_back,
        )
        back_btn.grid(row=0, column=1, sticky="e")

        if not items:
            self._show_empty_state()
            return

        for item in items:
            card = WatchLaterCard(
                self,
                item=item,
                on_watch=self.on_watch,
                on_download=self.on_download,
                on_remove=self._handle_remove,
            )
            card.pack(fill="x", padx=6, pady=4)

    def _handle_remove(self, video_id: str):
        watch_later_service.remove(video_id)
        self.refresh()

    def _show_empty_state(self):
        empty_frame = ctk.CTkFrame(self, fg_color="transparent")
        empty_frame.pack(fill="both", expand=True, pady=60)

        icon = ctk.CTkLabel(
            empty_frame,
            text="⭐",
            font=(Theme.FONT_FAMILY, 48),
        )
        icon.pack(pady=(0, 10))

        title = ctk.CTkLabel(
            empty_frame,
            text="No Videos Saved Yet",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_PRIMARY,
        )
        title.pack(pady=(0, 6))

        subtitle = ctk.CTkLabel(
            empty_frame,
            text="Click '♡ Watch Later' on any YouTube search result to save it here for watching or downloading later.",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED,
            wraplength=420,
        )
        subtitle.pack()
