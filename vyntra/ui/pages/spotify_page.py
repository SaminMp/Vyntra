"""
Dedicated Spotify Audio-Only Platform Page for Vyntra.
Supports track search, URL parsing, official 30s audio preview streaming, and MP3 downloading.
STRICTLY NO MP4, NO video quality, and NO video player controls.
Lifecycle-safe: prevents destroyed widget TclErrors and stale callback race conditions.
"""

from pathlib import Path
from tkinter import filedialog
from typing import List, Optional
import customtkinter as ctk

from vyntra.config import config_manager
from vyntra.models import AudioQuality, DownloadTask, MediaFormat, MediaItem, ProgressInfo
from vyntra.platforms.spotify.service import spotify_platform
from vyntra.services.image_service import image_service
from vyntra.ui.components.platform_selector import PLATFORM_METADATA
from vyntra.ui.pages.base_page import BasePlatformPage
from vyntra.ui.theme import Theme


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
        self._is_loading = False

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
        """Destroys dynamic result cards without destroying the permanent placeholder label."""
        for card in self._cards:
            try:
                card.destroy()
            except Exception:
                pass
        self._cards.clear()

    def _handle_search(self):
        query = self.search_entry.get().strip()
        if not query:
            self.app.status_banner.show_warning("Please enter a song name or Spotify URL.")
            return

        gen = self.next_generation()
        self._set_loading(True)
        self._clear_cards()

        if self.placeholder_label.winfo_exists():
            self.placeholder_label.configure(text=f"Searching Spotify for '{query}'...")
            self.placeholder_label.pack(pady=40)

        def _on_success(items: List[MediaItem]):
            self.safe_after(0, lambda: self._display_results(items, gen))

        def _on_error(err: Exception):
            self.safe_after(0, lambda: self._display_error(err, gen))

        self.platform_service.search_async(query, on_success=_on_success, on_error=_on_error)

    def _set_loading(self, loading: bool):
        self._is_loading = loading
        if self.search_btn.winfo_exists():
            self.search_btn.configure(state="disabled" if loading else "normal")
        if self.status_msg.winfo_exists():
            self.status_msg.configure(text="Connecting to Spotify..." if loading else "Ready")

    def _display_results(self, items: List[MediaItem], generation: int):
        if not self.is_generation_current(generation):
            return

        self._set_loading(False)
        self._current_items = items
        self._clear_cards()

        if not items:
            if self.placeholder_label.winfo_exists():
                self.placeholder_label.configure(text="No tracks found. Try another search query or paste a Spotify track link.")
                self.placeholder_label.pack(pady=40)
            return

        if self.placeholder_label.winfo_exists():
            self.placeholder_label.pack_forget()

        for item in items:
            self._create_track_card(item, generation)

        # Auto-select the first track
        if items:
            self._select_track(items[0])
            self.app.status_banner.show_success(f"Found {len(items)} Spotify track(s).")

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

        # Action Buttons container (Preview, Download, Select)
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
        card_preview_btn.pack(side="left", padx=(0, 6))

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
        card_download_btn.pack(side="left", padx=(0, 6))

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
        select_btn.pack(side="left")

        # Dynamic wraplength on card resize
        def _on_card_resized(event, t=title_lbl, m=meta_lbl):
            w = event.width
            if w > 1 and t.winfo_exists():
                avail = max(140, w - 340)
                t.configure(wraplength=avail)
                if m.winfo_exists():
                    m.configure(wraplength=avail)

        card.bind("<Configure>", _on_card_resized)

    def _handle_card_preview(self, item: MediaItem):
        """Immediately selects track and starts 30s preview playback."""
        self._select_track(item)
        self._handle_play_preview()

    def _handle_card_download(self, item: MediaItem):
        """Immediately selects track and initiates MP3 download."""
        self._select_track(item)
        self._handle_start_download()

    def _select_track(self, item: MediaItem):
        self._selected_item = item
        album_str = f" ({item.album})" if item.album else ""
        if self.selected_label.winfo_exists():
            self.selected_label.configure(
                text=f"Selected: {item.display_title} — {item.channel}{album_str}",
                text_color=Theme.TEXT_PRIMARY,
            )

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
        """Dispatches audio-only MP3 download job."""
        if not self._selected_item:
            self.app.status_banner.show_warning("Please select a song first.")
            return

        save_dir = self.folder_entry.get().strip() or config_manager.config.download_directory
        bitrate_str = self.quality_segmented.get().split()[0]  # e.g. "320"

        audio_q = AudioQuality.BEST
        if bitrate_str == "192":
            audio_q = AudioQuality.STANDARD
        elif bitrate_str == "256":
            audio_q = AudioQuality.HIGH

        self.status_msg.configure(text=f"Starting MP3 download ({bitrate_str} kbps)...")
        self.progress_bar.set(0.0)
        if self.progress_frame.winfo_exists():
            self.progress_frame.grid()

        self.app._handle_start_download(
            result=self._selected_item,
            media_format=MediaFormat.MP3,
            quality=bitrate_str,
            save_dir=save_dir,
        )

    def update_progress(self, prog: ProgressInfo):
        if self.progress_frame.winfo_exists() and not self.progress_frame.winfo_ismapped():
            self.progress_frame.grid()
        if self.progress_bar.winfo_exists():
            self.progress_bar.set(prog.percent / 100.0)
        if self.status_msg.winfo_exists():
            self.status_msg.configure(text=f"{prog.status_message} ({prog.percent:.1f}%)")

    def set_downloading(self, is_downloading: bool):
        if self.download_mp3_btn.winfo_exists():
            self.download_mp3_btn.configure(state="disabled" if is_downloading else "normal")
        if self.preview_btn.winfo_exists():
            self.preview_btn.configure(state="disabled" if is_downloading else "normal")
