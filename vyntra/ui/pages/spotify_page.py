"""
Dedicated Spotify Audio-Only Platform Page for Vyntra.
Supports track search, URL parsing, official 30s audio preview streaming, and MP3 downloading.
STRICTLY NO MP4, NO video quality, and NO video player controls.
Lifecycle-safe: prevents destroyed widget TclErrors and stale callback race conditions.
"""

from pathlib import Path
from tkinter import filedialog
from typing import Dict, List, Optional
import customtkinter as ctk

from vyntra.config import config_manager
from vyntra.models import AudioQuality, DownloadTask, MediaFormat, MediaItem, ProgressInfo
from vyntra.platforms.spotify.service import spotify_platform
from vyntra.services.image_service import image_service
from vyntra.ui.components.platform_selector import PLATFORM_METADATA
from vyntra.ui.pages.base_page import BasePlatformPage
from vyntra.ui.theme import Theme
from vyntra.utils.logger import logger


class SpotifyPage(BasePlatformPage):
    """
    Dedicated view for Spotify Music.
    Audio-only: supports preview streaming and pristine MP3 downloading with ID3 metadata.
    """

    def __init__(self, master, app, **kwargs):
        super().__init__(master, app, platform_service=spotify_platform, **kwargs)

        self._current_items: List[MediaItem] = []
        self._selected_item: Optional[MediaItem] = None
        self._cards: List[ctk.CTkFrame] = []
        self._card_checkboxes: List[ctk.CTkCheckBox] = []
        self._card_quality_menus: List[ctk.CTkOptionMenu] = []
        self._is_loading = False
        self._is_downloading = False
        self._collection_cache: Dict[str, List[MediaItem]] = {}
        self._active_collection_key: Optional[str] = None
        self._toolbar_frame: Optional[ctk.CTkFrame] = None
        self._selection_summary_lbl: Optional[ctk.CTkLabel] = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # Results container expands

        self._build_header()
        self._build_search_section()
        self._build_results_section()
        self._build_download_section()

    def _build_header(self):
        """Prominent platform branding banner with title and capability subtitle."""
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))

        meta = PLATFORM_METADATA.get("spotify")
        icon = meta.icon if meta else "♫"
        subtitle_text = meta.subtitle if meta else "Search music, stream 30s previews, and download high-fidelity MP3s"

        title_label = ctk.CTkLabel(
            header_frame,
            text=f"{icon}  Spotify",
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_PRIMARY,
        )
        title_label.pack(anchor="w")

        subtitle_label = ctk.CTkLabel(
            header_frame,
            text=subtitle_text,
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_SECONDARY,
        )
        subtitle_label.pack(anchor="w", pady=(2, 0))

    def _build_search_section(self):
        input_card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        input_card.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        input_card.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            input_card,
            placeholder_text="Search song title, artist, or paste Spotify track URL...",
            font=Theme.FONT_BODY,
            height=40,
            border_width=1,
            border_color=Theme.BORDER_CARD,
        )
        self.search_entry.grid(row=0, column=0, padx=(12, 8), pady=12, sticky="ew")
        self.search_entry.bind("<Return>", lambda e: self._handle_search())

        self.search_btn = ctk.CTkButton(
            input_card,
            text="Search",
            font=Theme.FONT_BODY_BOLD,
            height=40,
            width=110,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._handle_search,
        )
        self.search_btn.grid(row=0, column=1, padx=(0, 12), pady=12)

    def _build_results_section(self):
        self.results_container = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=Theme.RADIUS_CARD,
        )
        self.results_container.grid(row=2, column=0, sticky="nsew", padx=16, pady=4)
        self.results_container.grid_columnconfigure(0, weight=1)

        # Permanent placeholder widget (never destroyed)
        self.placeholder_label = ctk.CTkLabel(
            self.results_container,
            text="Search for music or paste a Spotify link above.",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED,
        )
        self.placeholder_label.pack(pady=40)

    def _build_download_section(self):
        """Audio-only download panel with MP3 bitrate picker. STRICTLY NO MP4."""
        panel = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        panel.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 16))
        panel.grid_columnconfigure(1, weight=1)

        # Selected song summary
        self.selected_label = ctk.CTkLabel(
            panel,
            text="No song selected",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
            anchor="w",
        )
        self.selected_label.grid(row=0, column=0, columnspan=3, padx=16, pady=(12, 4), sticky="w")

        # Row 1: Audio Quality (Bitrate)
        quality_row = ctk.CTkFrame(panel, fg_color="transparent")
        quality_row.grid(row=1, column=0, columnspan=3, sticky="ew", padx=16, pady=3)

        q_lbl = ctk.CTkLabel(quality_row, text="MP3 Bitrate:", font=Theme.FONT_CAPTION, text_color=Theme.TEXT_MUTED)
        q_lbl.pack(side="left", padx=(0, 8))

        self.quality_segmented = ctk.CTkSegmentedButton(
            quality_row,
            values=["320 kbps", "256 kbps", "192 kbps", "128 kbps"],
            font=Theme.FONT_CAPTION,
            height=28,
            selected_color=Theme.PRIMARY,
            command=self._handle_panel_quality_changed,
        )
        self.quality_segmented.set("320 kbps")
        self.quality_segmented.pack(side="left")

        # Row 2: Destination Row (Folder Picker with dynamic expansion)
        dest_row = ctk.CTkFrame(panel, fg_color="transparent")
        dest_row.grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=4)
        dest_row.grid_columnconfigure(1, weight=1)

        dest_lbl = ctk.CTkLabel(dest_row, text="Save to:", font=Theme.FONT_CAPTION, text_color=Theme.TEXT_MUTED)
        dest_lbl.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.folder_entry = ctk.CTkEntry(dest_row, font=Theme.FONT_CAPTION, height=28)
        self.folder_entry.grid(row=0, column=1, padx=(0, 8), sticky="ew")
        self.folder_entry.insert(0, config_manager.config.download_directory)

        browse_btn = ctk.CTkButton(
            dest_row,
            text="Browse",
            font=Theme.FONT_CAPTION,
            width=70,
            height=28,
            fg_color=Theme.BG_CARD_HOVER,
            command=self._browse_folder,
        )
        browse_btn.grid(row=0, column=2, sticky="e")

        # Row 3: Action Buttons row: [ Play Preview ] and [ Download MP3 ]
        actions_row = ctk.CTkFrame(panel, fg_color="transparent")
        actions_row.grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(8, 8))

        self.preview_btn = ctk.CTkButton(
            actions_row,
            text="▶ Play Preview (30s)",
            font=Theme.FONT_BODY_BOLD,
            height=36,
            width=170,
            fg_color=Theme.BG_CARD_HOVER,
            hover_color=Theme.PRIMARY,
            command=self._handle_play_preview,
        )
        self.preview_btn.pack(side="left", padx=(0, 12))

        self.download_mp3_btn = ctk.CTkButton(
            actions_row,
            text="⬇ Download MP3",
            font=Theme.FONT_BODY_BOLD,
            height=36,
            width=160,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._handle_start_download,
        )
        self.download_mp3_btn.pack(side="left")

        # Row 4: Progress Section (shown during download)
        self.progress_frame = ctk.CTkFrame(panel, fg_color="transparent")
        self.progress_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 12))
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.status_msg = ctk.CTkLabel(self.progress_frame, text="Ready", font=Theme.FONT_CAPTION, text_color=Theme.TEXT_MUTED)
        self.status_msg.grid(row=0, column=0, sticky="w", pady=(0, 2))

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, height=6, corner_radius=3)
        self.progress_bar.grid(row=1, column=0, sticky="ew")
        self.progress_bar.set(0.0)
        self.progress_frame.grid_remove()

    def _browse_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.folder_entry.get())
        if chosen:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, chosen)
            config_manager.update(download_directory=chosen)

    def _clear_cards(self):
        """Destroys dynamic result cards and toolbar without destroying permanent placeholder label."""
        if self._toolbar_frame and self._toolbar_frame.winfo_exists():
            try:
                self._toolbar_frame.destroy()
            except Exception:
                pass
            self._toolbar_frame = None
            self._selection_summary_lbl = None

        for card in self._cards:
            try:
                card.destroy()
            except Exception:
                pass
        self._cards.clear()
        self._card_checkboxes.clear()
        self._card_quality_menus.clear()

    def _normalize_collection_key(self, query: str) -> str:
        return query.strip().lower()

    def _handle_search(self):
        query = self.search_entry.get().strip()
        if not query:
            self.app.status_banner.show_warning("Please enter a song name or Spotify URL.")
            return

        col_key = self._normalize_collection_key(query)
        self._active_collection_key = col_key
        gen = self.next_generation()
        self._set_loading(True)
        self._clear_cards()

        if self.placeholder_label.winfo_exists():
            self.placeholder_label.configure(text=f"Searching Spotify for '{query}'...")
            self.placeholder_label.pack(pady=40)

        def _on_success(items: List[MediaItem]):
            self.safe_after(0, lambda: self._display_results(items, gen, col_key=col_key))

        def _on_error(err: Exception):
            self.safe_after(0, lambda: self._display_error(err, gen))

        self.platform_service.search_async(query, on_success=_on_success, on_error=_on_error)

    def _set_loading(self, loading: bool):
        self._is_loading = loading
        if self.search_btn.winfo_exists():
            self.search_btn.configure(state="disabled" if loading else "normal")
        if self.status_msg.winfo_exists():
            self.status_msg.configure(text="Connecting to Spotify..." if loading else "Ready")

    def _display_results(self, items: List[MediaItem], generation: int, col_key: Optional[str] = None):
        if not self.is_generation_current(generation):
            return

        self._set_loading(False)

        effective_key = col_key or self._active_collection_key
        if effective_key and effective_key in self._collection_cache:
            prev_items = self._collection_cache[effective_key]
            prev_state = {
                (it.video_id or it.url): (it.selected_for_download, it.download_quality)
                for it in prev_items
                if (it.video_id or it.url)
            }
            for it in items:
                k = it.video_id or it.url
                if k in prev_state:
                    it.selected_for_download, it.download_quality = prev_state[k]
                else:
                    it.download_format = MediaFormat.MP3
                    if not getattr(it, "download_quality", None):
                        it.download_quality = "320 kbps"
        else:
            for it in items:
                it.download_format = MediaFormat.MP3
                if not getattr(it, "download_quality", None):
                    it.download_quality = "320 kbps"

        if effective_key:
            self._collection_cache[effective_key] = items

        self._current_items = items
        self._clear_cards()

        if not items:
            if self.placeholder_label.winfo_exists():
                self.placeholder_label.configure(text="No tracks found. Try another search query or paste a Spotify track link.")
                self.placeholder_label.pack(pady=40)
            self._handle_download_selection_changed()
            return

        if self.placeholder_label.winfo_exists():
            self.placeholder_label.pack_forget()

        # Add toolbar for batch controls
        self._build_toolbar(len(items))

        for item in items:
            self._create_track_card(item, generation)

        # Auto-select the first track for preview / single-track operations
        if items:
            self._select_track(items[0])
            self.app.status_banner.show_success(f"Found {len(items)} Spotify track(s).")

        self._handle_download_selection_changed()

    def _build_toolbar(self, total_count: int):
        self._toolbar_frame = ctk.CTkFrame(self.results_container, fg_color="transparent")
        self._toolbar_frame.pack(fill="x", padx=6, pady=(4, 6))
        self._toolbar_frame.grid_columnconfigure(2, weight=1)

        select_all_btn = ctk.CTkButton(
            self._toolbar_frame,
            text="☑ Select All",
            font=Theme.FONT_CAPTION,
            width=90,
            height=28,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self.select_all,
        )
        select_all_btn.grid(row=0, column=0, padx=(0, 6), sticky="w")

        deselect_all_btn = ctk.CTkButton(
            self._toolbar_frame,
            text="☐ Deselect All",
            font=Theme.FONT_CAPTION,
            width=96,
            height=28,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self.deselect_all,
        )
        deselect_all_btn.grid(row=0, column=1, padx=(0, 12), sticky="w")

        self._selection_summary_lbl = ctk.CTkLabel(
            self._toolbar_frame,
            text=f"{total_count} tracks found • 0 selected for download",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
        )
        self._selection_summary_lbl.grid(row=0, column=2, sticky="e")

    def get_selected_download_items(self) -> List[MediaItem]:
        """Returns all tracks in the active collection checked for batch download."""
        return [it for it in self._current_items if getattr(it, "selected_for_download", False)]

    def select_all(self):
        """Checks all tracks in current collection for batch download."""
        for it in self._current_items:
            it.selected_for_download = True
        for cb in self._card_checkboxes:
            if cb.winfo_exists():
                cb.select()
        self._handle_download_selection_changed()

    def deselect_all(self):
        """Unchecks all tracks in current collection."""
        for it in self._current_items:
            it.selected_for_download = False
        for cb in self._card_checkboxes:
            if cb.winfo_exists():
                cb.deselect()
        self._handle_download_selection_changed()

    def _handle_download_selection_changed(self):
        selected_items = self.get_selected_download_items()
        count = len(selected_items)
        total = len(self._current_items)
        if self._selection_summary_lbl and self._selection_summary_lbl.winfo_exists():
            self._selection_summary_lbl.configure(
                text=f"{total} tracks found • {count} selected for download"
            )
        if hasattr(self, "download_mp3_btn") and self.download_mp3_btn.winfo_exists():
            if count > 1:
                self.download_mp3_btn.configure(text=f"⬇ Download {count} Selected Tracks")
            elif count == 1:
                self.download_mp3_btn.configure(text="⬇ Download 1 Selected Track")
            else:
                self.download_mp3_btn.configure(text="⬇ Download MP3")

    def _create_track_card(self, item: MediaItem, generation: int):
        card = ctk.CTkFrame(self.results_container, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        card.pack(fill="x", pady=4, padx=4)
        card.grid_columnconfigure(1, weight=1)
        self._cards.append(card)

        # Album Art with synchronous placeholder and safe async load
        art_label = ctk.CTkLabel(card, text="", width=64, height=64, fg_color=Theme.BG_CARD_HOVER, corner_radius=4)
        art_label.grid(row=0, column=0, rowspan=2, padx=12, pady=10)

        if item.thumbnail_url:
            def _on_art_loaded(ctk_img, c=card, lbl=art_label, gen=generation):
                if c.winfo_exists() and lbl.winfo_exists() and self.is_generation_current(gen):
                    lbl.configure(image=ctk_img, text="")

            placeholder = image_service.get_thumbnail_async(
                url=item.thumbnail_url,
                size=(64, 64),
                on_success=lambda img: self.safe_after(0, lambda: _on_art_loaded(img)),
            )
            art_label.configure(image=placeholder)
        else:
            art_label.configure(text="🎵")

        # Track Title & Artists
        title_lbl = ctk.CTkLabel(card, text=item.display_title, font=Theme.FONT_SUBHEADER, text_color=Theme.TEXT_PRIMARY, anchor="w")
        title_lbl.grid(row=0, column=1, sticky="w", padx=(4, 8), pady=(10, 0))

        artist_text = item.channel
        if item.album:
            artist_text += f"  •  {item.album}"
        if item.duration_seconds > 0:
            artist_text += f"  •  {item.duration_formatted}"

        meta_lbl = ctk.CTkLabel(card, text=artist_text, font=Theme.FONT_CAPTION, text_color=Theme.TEXT_MUTED, anchor="w")
        meta_lbl.grid(row=1, column=1, sticky="w", padx=(4, 8), pady=(0, 10))

        # Action Buttons container (Preview, Download, Select, Checkbox, Quality)
        card_actions = ctk.CTkFrame(card, fg_color="transparent")
        card_actions.grid(row=0, column=2, rowspan=2, padx=12, pady=10, sticky="e")

        card_preview_btn = ctk.CTkButton(
            card_actions,
            text="▶ Preview",
            font=Theme.FONT_CAPTION,
            width=76,
            height=30,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.ACCENT_CYAN,
            command=lambda it=item: self._handle_card_preview(it),
        )
        card_preview_btn.grid(row=0, column=0, padx=(0, 6), pady=(0, 4), sticky="w")

        card_download_btn = ctk.CTkButton(
            card_actions,
            text="⬇ Download",
            font=Theme.FONT_CAPTION,
            width=88,
            height=30,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=lambda it=item: self._handle_card_download(it),
        )
        card_download_btn.grid(row=0, column=1, padx=(0, 6), pady=(0, 4), sticky="w")

        select_btn = ctk.CTkButton(
            card_actions,
            text="Select",
            font=Theme.FONT_CAPTION,
            width=65,
            height=30,
            fg_color=Theme.BG_CARD_HOVER,
            hover_color=Theme.PRIMARY,
            command=lambda it=item: self._select_track(it),
        )
        select_btn.grid(row=0, column=2, pady=(0, 4), sticky="e")

        # Row 1: Per-track Download Checkbox & Audio Quality OptionMenu
        download_checkbox = ctk.CTkCheckBox(
            card_actions,
            text="Download",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_SECONDARY,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            checkmark_color="#FFFFFF",
            width=88,
            height=26,
            checkbox_width=18,
            checkbox_height=18,
        )
        download_checkbox.grid(row=1, column=0, columnspan=2, padx=(0, 6), pady=(2, 0), sticky="w")
        download_checkbox.configure(command=lambda it=item, cb=download_checkbox: self._on_card_checkbox_toggled(it, cb))
        if getattr(item, "selected_for_download", False):
            download_checkbox.select()
        else:
            download_checkbox.deselect()
        self._card_checkboxes.append(download_checkbox)

        initial_quality = getattr(item, "download_quality", None)
        if not initial_quality or initial_quality not in ("320 kbps", "256 kbps", "192 kbps", "128 kbps"):
            initial_quality = "320 kbps"
            item.download_quality = initial_quality

        quality_menu = ctk.CTkOptionMenu(
            card_actions,
            values=["320 kbps", "256 kbps", "192 kbps", "128 kbps"],
            font=Theme.FONT_CAPTION,
            width=96,
            height=26,
            fg_color=Theme.BG_MUTED,
            button_color=Theme.PRIMARY,
            button_hover_color=Theme.PRIMARY_HOVER,
            dropdown_fg_color=Theme.BG_CARD,
            command=lambda val, it=item: self._on_card_quality_changed(val, it),
        )
        quality_menu.set(initial_quality)
        quality_menu.grid(row=1, column=2, pady=(2, 0), sticky="e")
        self._card_quality_menus.append(quality_menu)

        # Dynamic wraplength on card resize
        def _on_card_resized(event, t=title_lbl, m=meta_lbl):
            w = event.width
            if w > 1 and t.winfo_exists():
                avail = max(140, w - 340)
                t.configure(wraplength=avail)
                if m.winfo_exists():
                    m.configure(wraplength=avail)

        card.bind("<Configure>", _on_card_resized)

    def _on_card_checkbox_toggled(self, item: MediaItem, checkbox: ctk.CTkCheckBox):
        item.selected_for_download = bool(checkbox.get())
        self._handle_download_selection_changed()

    def _on_card_quality_changed(self, val: str, item: MediaItem):
        item.download_quality = val
        if self._selected_item and (self._selected_item == item or self._selected_item.video_id == item.video_id):
            if hasattr(self, "quality_segmented") and self.quality_segmented.winfo_exists():
                self.quality_segmented.set(val)

    def _sync_card_quality_menu(self, item: MediaItem, quality: str):
        for idx, it in enumerate(self._current_items):
            if it == item or it.video_id == item.video_id:
                if idx < len(self._card_quality_menus) and self._card_quality_menus[idx].winfo_exists():
                    self._card_quality_menus[idx].set(quality)

    def _handle_panel_quality_changed(self, val: str):
        if self._selected_item:
            self._selected_item.download_quality = val
            self._sync_card_quality_menu(self._selected_item, val)

    def _handle_card_preview(self, item: MediaItem):
        """Immediately selects track and starts 30s preview playback."""
        self._select_track(item)
        self._handle_play_preview()

    def _handle_card_download(self, item: MediaItem):
        """Immediately selects track and initiates MP3 download for that single track."""
        if self._is_downloading:
            return
        if not ((item.title and item.title.strip()) or (item.url and item.url.strip())):
            self.app.status_banner.show_warning("The track does not have a usable download source.")
            return

        self._select_track(item)
        save_dir = self.folder_entry.get().strip() or config_manager.config.download_directory
        quality_str = getattr(item, "download_quality", None) or self.quality_segmented.get()
        item.download_format = MediaFormat.MP3
        item.download_quality = quality_str

        self.status_msg.configure(text=f"Starting MP3 download ({quality_str})...")
        self.progress_bar.set(0.0)
        if self.progress_frame.winfo_exists():
            self.progress_frame.grid()

        self.app._handle_start_download(
            result=item,
            media_format=MediaFormat.MP3,
            quality=quality_str,
            save_dir=save_dir,
        )

    def _select_track(self, item: MediaItem):
        self._selected_item = item
        album_str = f" ({item.album})" if item.album else ""
        if self.selected_label.winfo_exists():
            self.selected_label.configure(
                text=f"Selected: {item.display_title} — {item.channel}{album_str}",
                text_color=Theme.TEXT_PRIMARY,
            )
        if hasattr(self, "quality_segmented") and self.quality_segmented.winfo_exists():
            q = getattr(item, "download_quality", "320 kbps")
            if q in ("320 kbps", "256 kbps", "192 kbps", "128 kbps"):
                self.quality_segmented.set(q)

    def _display_error(self, err: Exception, generation: int):
        if not self.is_generation_current(generation):
            return

        self._set_loading(False)
        self._clear_cards()

        if self.placeholder_label.winfo_exists():
            self.placeholder_label.configure(text=f"Spotify search failed:\n{str(err)}")
            self.placeholder_label.pack(pady=40)

        self.app.status_banner.show_error(f"Spotify error: {str(err)}")

    def _handle_play_preview(self):
        """Plays the 30-second official preview stream via dedicated AudioPlayerModal."""
        if not self._selected_item:
            self.app.status_banner.show_warning("Please select a song first.")
            return

        self.status_msg.configure(text=f"Playing preview: {self._selected_item.display_title}...")
        self.app._handle_play_audio(self._selected_item)

    def _handle_start_download(self):
        """Dispatches audio-only MP3 download job(s) for selected tracks or active track."""
        if self._is_downloading:
            return

        selected_items = self.get_selected_download_items()

        # Scenario 1: Multi-selection exists
        if selected_items:
            valid_items: List[MediaItem] = []
            for it in selected_items:
                if (it.title and it.title.strip()) or (it.url and it.url.strip()):
                    it.download_format = MediaFormat.MP3
                    if not getattr(it, "download_quality", None):
                        it.download_quality = "320 kbps"
                    valid_items.append(it)
                else:
                    logger.warning("[Spotify] Skipping track with invalid download source: %s", it)

            if not valid_items:
                self.app.status_banner.show_warning("None of the selected tracks have a usable download source.")
                return

            save_dir = self.folder_entry.get().strip() or config_manager.config.download_directory

            self.status_msg.configure(text=f"Queueing {len(valid_items)} Spotify track(s)...")
            self.progress_bar.set(0.0)
            if self.progress_frame.winfo_exists():
                self.progress_frame.grid()

            self.app._handle_start_download(
                result=valid_items[0],
                media_format=MediaFormat.MP3,
                quality=valid_items[0].download_quality,
                save_dir=save_dir,
                batch_items=valid_items,
            )
            return

        # Scenario 2: Multi-item collection (album/playlist) with no items checked
        if len(self._current_items) > 1:
            self.app.status_banner.show_warning("Please select at least one song to download.")
            return

        # Scenario 3: Single item collection or single active track
        if self._selected_item:
            target = self._selected_item
            if not ((target.title and target.title.strip()) or (target.url and target.url.strip())):
                self.app.status_banner.show_warning("The selected track does not have a usable download source.")
                return

            save_dir = self.folder_entry.get().strip() or config_manager.config.download_directory
            bitrate_str = getattr(target, "download_quality", None) or self.quality_segmented.get()
            target.download_format = MediaFormat.MP3
            target.download_quality = bitrate_str

            self.status_msg.configure(text=f"Starting MP3 download ({bitrate_str})...")
            self.progress_bar.set(0.0)
            if self.progress_frame.winfo_exists():
                self.progress_frame.grid()

            self.app._handle_start_download(
                result=target,
                media_format=MediaFormat.MP3,
                quality=bitrate_str,
                save_dir=save_dir,
            )
            return

        self.app.status_banner.show_warning("Please select a song first.")

    def update_progress(self, prog: ProgressInfo):
        if self.progress_frame.winfo_exists() and not self.progress_frame.winfo_ismapped():
            self.progress_frame.grid()
        if self.progress_bar.winfo_exists():
            self.progress_bar.set(prog.percent / 100.0)
        if self.status_msg.winfo_exists():
            self.status_msg.configure(text=f"{prog.status_message} ({prog.percent:.1f}%)")

    def set_downloading(self, is_downloading: bool):
        self._is_downloading = is_downloading
        if self.download_mp3_btn.winfo_exists():
            self.download_mp3_btn.configure(state="disabled" if is_downloading else "normal")
        if self.preview_btn.winfo_exists():
            self.preview_btn.configure(state="disabled" if is_downloading else "normal")
