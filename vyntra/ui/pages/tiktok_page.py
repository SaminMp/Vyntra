"""
Dedicated TikTok Platform Page for Vyntra.
Supports TikTok video URL extraction, preview playback, and MP4/MP3 downloading.
"""

from pathlib import Path
from tkinter import filedialog
from typing import Optional
import customtkinter as ctk

from vyntra.config import config_manager
from vyntra.models import DownloadTask, MediaFormat, MediaItem, ProgressInfo
from vyntra.platforms.tiktok.service import tiktok_platform
from vyntra.services.image_service import image_service
from vyntra.ui.components.platform_selector import PLATFORM_METADATA
from vyntra.ui.pages.base_page import BasePlatformPage
from vyntra.ui.theme import Theme


class TikTokPage(BasePlatformPage):
    """
    Dedicated view for TikTok Videos.
    Provides direct URL-based media extraction, preview streaming, and downloading.
    """

    def __init__(self, master, app, **kwargs):
        super().__init__(master, app, platform_service=tiktok_platform, **kwargs)

        self._current_item: Optional[MediaItem] = None
        self._is_loading = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # Preview area expands

        self._build_header()
        self._build_url_section()
        self._build_preview_card_section()
        self._build_download_section()

    def _build_header(self):
        """Prominent platform branding banner with title and capability subtitle."""
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))

        meta = PLATFORM_METADATA.get("tiktok")
        icon = meta.icon if meta else "♪"
        subtitle_text = meta.subtitle if meta else "Watch and download high-quality videos without watermarks"

        title = ctk.CTkLabel(
            header_frame,
            text=f"{icon}  TikTok",
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

    def _build_url_section(self):
        input_card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        input_card.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        input_card.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            input_card,
            placeholder_text="https://www.tiktok.com/@user/video/... or https://vm.tiktok.com/...",
            font=Theme.FONT_BODY,
            height=40,
            border_width=1,
            border_color=Theme.BORDER_CARD,
        )
        self.url_entry.grid(row=0, column=0, padx=(12, 8), pady=12, sticky="ew")
        self.url_entry.bind("<Return>", lambda e: self._handle_fetch())

        self.fetch_btn = ctk.CTkButton(
            input_card,
            text="Fetch Video",
            font=Theme.FONT_BODY_BOLD,
            height=40,
            width=115,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._handle_fetch,
        )
        self.fetch_btn.grid(row=0, column=1, padx=(0, 6), pady=12)

        self.diag_btn = ctk.CTkButton(
            input_card,
            text="📋 Diagnostics",
            font=Theme.FONT_CAPTION,
            height=40,
            width=100,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._handle_diagnostics,
        )
        self.diag_btn.grid(row=0, column=2, padx=(0, 12), pady=12)

    def _build_preview_card_section(self):
        self.preview_container = ctk.CTkFrame(self, fg_color="transparent")
        self.preview_container.grid(row=2, column=0, sticky="nsew", padx=16, pady=4)
        self.preview_container.grid_columnconfigure(0, weight=1)
        self.preview_container.grid_rowconfigure(0, weight=1)

        self.placeholder_label = ctk.CTkLabel(
            self.preview_container,
            text="Paste a TikTok video link above and click 'Fetch Video' to preview or download.",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED,
        )
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor="center")

        # Media Info Card (Initially Hidden)
        self.card_content = ctk.CTkFrame(self.preview_container, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        self.card_content.grid_columnconfigure(1, weight=1)

        # Thumbnail / Poster
        self.thumb_label = ctk.CTkLabel(self.card_content, text="", width=160, height=110, fg_color=Theme.BG_CARD_HOVER, corner_radius=8)
        self.thumb_label.grid(row=0, column=0, rowspan=4, padx=16, pady=16)

        # Title & Author
        self.title_label = ctk.CTkLabel(self.card_content, text="Video Title", font=Theme.FONT_HEADER, text_color=Theme.TEXT_PRIMARY, anchor="w")
        self.title_label.grid(row=0, column=1, sticky="w", padx=(0, 16), pady=(16, 4))

        self.creator_label = ctk.CTkLabel(self.card_content, text="@creator", font=Theme.FONT_BODY_BOLD, text_color=Theme.TEXT_SECONDARY, anchor="w")
        self.creator_label.grid(row=1, column=1, sticky="w", padx=(0, 16), pady=2)

        self.meta_label = ctk.CTkLabel(self.card_content, text="TikTok • MP4", font=Theme.FONT_CAPTION, text_color=Theme.TEXT_MUTED, anchor="w")
        self.meta_label.grid(row=2, column=1, sticky="w", padx=(0, 16), pady=2)

        # Action Buttons in Card
        btn_box = ctk.CTkFrame(self.card_content, fg_color="transparent")
        btn_box.grid(row=3, column=1, sticky="w", padx=(0, 16), pady=(8, 16))

        self.watch_btn = ctk.CTkButton(
            btn_box,
            text="▶ Watch / Preview",
            font=Theme.FONT_BODY_BOLD,
            height=34,
            width=140,
            fg_color=Theme.BG_CARD_HOVER,
            hover_color=Theme.PRIMARY,
            command=self._handle_watch,
        )
        self.watch_btn.pack(side="left", padx=(0, 8))

        # Dynamic wraplength on card resize
        def _on_card_configure(event):
            w = event.width
            if w > 1 and self.title_label.winfo_exists():
                avail = max(180, w - 210)
                self.title_label.configure(wraplength=avail)

        self.card_content.bind("<Configure>", _on_card_configure)

    def _build_download_section(self):
        panel = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        panel.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 16))
        panel.grid_columnconfigure(0, weight=1)

        # Row 0: Destination folder row (Responsive Grid)
        dest_row = ctk.CTkFrame(panel, fg_color="transparent")
        dest_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        dest_row.grid_columnconfigure(1, weight=1)

        dest_lbl = ctk.CTkLabel(dest_row, text="Save Destination:", font=Theme.FONT_CAPTION, text_color=Theme.TEXT_MUTED)
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

        # Row 1: Action Buttons row
        actions_row = ctk.CTkFrame(panel, fg_color="transparent")
        actions_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 10))

        self.download_mp4_btn = ctk.CTkButton(
            actions_row,
            text="⬇ Download MP4",
            font=Theme.FONT_BODY_BOLD,
            height=32,
            width=140,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=lambda: self._handle_download(MediaFormat.MP4),
        )
        self.download_mp4_btn.pack(side="left", padx=(0, 10))

        self.download_mp3_btn = ctk.CTkButton(
            actions_row,
            text="🎵 Audio (MP3)",
            font=Theme.FONT_BODY,
            height=32,
            width=120,
            fg_color=Theme.BG_CARD_HOVER,
            hover_color=Theme.PRIMARY,
            command=lambda: self._handle_download(MediaFormat.MP3),
        )
        self.download_mp3_btn.pack(side="left")

        # Row 2: Progress bar
        self.progress_frame = ctk.CTkFrame(panel, fg_color="transparent")
        self.progress_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.status_msg = ctk.CTkLabel(self.progress_frame, text="Ready", font=Theme.FONT_CAPTION, text_color=Theme.TEXT_MUTED)
        self.status_msg.grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, height=8, corner_radius=4)
        self.progress_bar.grid(row=1, column=0, sticky="ew")
        self.progress_bar.set(0.0)

    def _browse_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.folder_entry.get())
        if chosen:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, chosen)
            config_manager.update(download_directory=chosen)

    def _handle_fetch(self):
        url = self.url_entry.get().strip()
        if not url:
            self.app.status_banner.show_warning("Please paste a TikTok video URL.")
            return

        if not self.platform_service.can_handle_url(url):
            self.app.status_banner.show_warning("Invalid TikTok URL. Expected https://www.tiktok.com/@user/video/... or vm.tiktok.com/...")
            return

        gen = self.next_generation()
        self._set_loading(True)
        if self.placeholder_label.winfo_exists():
            self.placeholder_label.configure(text="Extracting TikTok video metadata...")

        def _on_success(item: MediaItem):
            self.safe_after(0, lambda: self._display_item(item, gen))

        def _on_error(err: Exception):
            self.safe_after(0, lambda: self._display_error(err, gen))

        self.platform_service.extract_from_url_async(url, on_success=_on_success, on_error=_on_error)

    def _set_loading(self, loading: bool):
        self._is_loading = loading
        if self.fetch_btn.winfo_exists():
            self.fetch_btn.configure(state="disabled" if loading else "normal")
        if self.status_msg.winfo_exists():
            self.status_msg.configure(text="Connecting to TikTok..." if loading else "Ready")

    def _display_item(self, item: MediaItem, generation: int):
        if not self.is_generation_current(generation):
            return

        self._set_loading(False)
        self._current_item = item
        if self.placeholder_label.winfo_exists():
            self.placeholder_label.place_forget()
        if self.card_content.winfo_exists():
            self.card_content.pack(fill="both", expand=True)

        if self.title_label.winfo_exists():
            self.title_label.configure(text=item.display_title)
        if self.creator_label.winfo_exists():
            self.creator_label.configure(text=item.channel)
        dur_text = f"Duration: {item.duration_formatted}" if item.duration_seconds > 0 else "Video"
        if self.meta_label.winfo_exists():
            self.meta_label.configure(text=f"{dur_text}  •  TikTok Original")

        # Load thumbnail safely
        if item.thumbnail_url:
            def _on_thumb(ctk_img, gen=generation):
                if self.thumb_label.winfo_exists() and self.is_generation_current(gen):
                    self.thumb_label.configure(image=ctk_img)

            placeholder = image_service.get_thumbnail_async(
                url=item.thumbnail_url,
                size=(160, 110),
                on_success=lambda img: self.safe_after(0, lambda: _on_thumb(img)),
            )
            if self.thumb_label.winfo_exists():
                self.thumb_label.configure(image=placeholder)

        self.app.status_banner.show_success(f"Loaded: {item.display_title}")

    def _display_error(self, err: Exception, generation: int):
        if not self.is_generation_current(generation):
            return

        self._set_loading(False)
        clean_msg = str(err)
        if self.placeholder_label.winfo_exists():
            self.placeholder_label.configure(
                text=f"⚠️ {clean_msg}\n\nTip: Click '📋 Diagnostics' to inspect network/environment capabilities."
            )
            self.placeholder_label.place(relx=0.5, rely=0.5, anchor="center")
        if self.card_content.winfo_exists():
            self.card_content.pack_forget()
        self.app.status_banner.show_error(clean_msg)

    def _handle_diagnostics(self):
        """Runs safe TikTok diagnostics in a background thread and presents modal."""
        import threading
        url = self.url_entry.get().strip()
        if self.diag_btn.winfo_exists():
            self.diag_btn.configure(state="disabled", text="Testing...")

        def _worker():
            report = tiktok_platform.diagnose(url)
            self.safe_after(0, lambda: self._on_diagnostics_done(report))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_diagnostics_done(self, report: str):
        if self.diag_btn.winfo_exists():
            self.diag_btn.configure(state="normal", text="📋 Diagnostics")
        self._show_diagnostics_modal(report)

    def _show_diagnostics_modal(self, report: str):
        diag_win = ctk.CTkToplevel(self)
        diag_win.title("Vyntra TikTok Diagnostics")
        diag_win.geometry("560x520")
        diag_win.minsize(480, 380)
        diag_win.configure(fg_color=Theme.BG_MAIN)
        diag_win.transient(self)
        diag_win.grab_set()

        header = ctk.CTkLabel(
            diag_win,
            text="📋 TikTok Diagnostics Report",
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_PRIMARY,
        )
        header.pack(anchor="w", padx=20, pady=(16, 8))

        textbox = ctk.CTkTextbox(
            diag_win,
            font=("Consolas", 12),
            fg_color=Theme.BG_CARD,
            text_color=Theme.TEXT_MAIN,
            border_color=Theme.BORDER_CARD,
            border_width=1,
            corner_radius=Theme.RADIUS_CARD,
        )
        textbox.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        textbox.insert("1.0", report)
        textbox.configure(state="disabled")

        btn_row = ctk.CTkFrame(diag_win, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))

        def _copy():
            diag_win.clipboard_clear()
            diag_win.clipboard_append(report)
            copy_btn.configure(text="✓ Copied!")
            diag_win.after(1500, lambda: copy_btn.configure(text="Copy Report"))

        copy_btn = ctk.CTkButton(
            btn_row,
            text="Copy Report",
            font=Theme.FONT_BODY,
            height=34,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=_copy,
        )
        copy_btn.pack(side="left")

        close_btn = ctk.CTkButton(
            btn_row,
            text="Close",
            font=Theme.FONT_BODY,
            height=34,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=diag_win.destroy,
        )
        close_btn.pack(side="right")

    def _handle_watch(self):
        if self._current_item:
            self.app._handle_play_video(self._current_item)

    def _handle_download(self, fmt: MediaFormat):
        if not self._current_item:
            return

        save_dir = self.folder_entry.get().strip() or config_manager.config.download_directory
        if self.status_msg.winfo_exists():
            self.status_msg.configure(text=f"Starting {fmt.value} download...")
        if self.progress_bar.winfo_exists():
            self.progress_bar.set(0.0)

        self.app._handle_start_download(
            result=self._current_item,
            media_format=fmt,
            quality="best",
            save_dir=save_dir,
        )

    def update_progress(self, prog: ProgressInfo):
        if self.progress_bar.winfo_exists():
            self.progress_bar.set(prog.percent / 100.0)
        if self.status_msg.winfo_exists():
            self.status_msg.configure(text=f"{prog.status_message} ({prog.percent:.1f}%)")

    def set_downloading(self, is_downloading: bool):
        if self.download_mp4_btn.winfo_exists():
            self.download_mp4_btn.configure(state="disabled" if is_downloading else "normal")
        if self.download_mp3_btn.winfo_exists():
            self.download_mp3_btn.configure(state="disabled" if is_downloading else "normal")
