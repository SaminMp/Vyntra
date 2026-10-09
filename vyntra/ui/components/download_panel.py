"""
Download control panel with destination folder picker, live progress indicators, and batch dispatching.
Format and quality selections are managed individually on each media card.
"""

from pathlib import Path
from tkinter import filedialog
from typing import Callable, List, Optional
import customtkinter as ctk

from vyntra.config import config_manager
from vyntra.models import MediaFormat, ProgressInfo, SearchResult
from vyntra.services.search_service import search_service
from vyntra.ui.theme import Theme


class DownloadPanel(ctk.CTkFrame):
    """Panel managing download directory, batch/single download dispatch, and progress feedback."""

    def __init__(
        self,
        master,
        on_download: Callable[[SearchResult, MediaFormat, str, str], None],
        on_cancel: Callable[[], None],
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

        self.on_download = on_download
        self.on_cancel = on_cancel
        self.selected_result: Optional[SearchResult] = None
        self._batch_items: List[SearchResult] = []
        self._is_downloading = False
        self._cached_video_resolutions: List[str] = []
        self._probe_error_message: Optional[str] = None

        self.grid_columnconfigure(0, weight=1)

        # 1. Header & Selection Summary
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=16, pady=(12, 6))
        self.header_frame.grid_columnconfigure(1, weight=1)

        self.panel_title = ctk.CTkLabel(
            self.header_frame,
            text="Download Media",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_PRIMARY,
        )
        self.panel_title.grid(row=0, column=0, sticky="w")

        self.selected_title_label = ctk.CTkLabel(
            self.header_frame,
            text="No video selected",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED,
            anchor="e",
            wraplength=480,
        )
        self.selected_title_label.grid(row=0, column=1, padx=(10, 0), sticky="e")

        # 2. Destination Row (Folder Picker)
        self.folder_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.folder_frame.pack(fill="x", padx=16, pady=(4, 6))
        self.folder_frame.grid_columnconfigure(1, weight=1)

        folder_lbl = ctk.CTkLabel(
            self.folder_frame,
            text="Save to:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )
        folder_lbl.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.folder_entry = ctk.CTkEntry(
            self.folder_frame,
            font=Theme.FONT_CAPTION,
            fg_color=Theme.BG_INPUT,
            border_color=Theme.BORDER_CARD,
            height=32,
        )
        self.folder_entry.insert(0, config_manager.config.download_directory)
        self.folder_entry.grid(row=0, column=1, padx=(0, 8), sticky="ew")
        self.folder_entry.bind("<FocusOut>", lambda e: self._on_folder_entry_changed())

        self.browse_btn = ctk.CTkButton(
            self.folder_frame,
            text="Browse...",
            font=Theme.FONT_CAPTION,
            width=75,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._browse_directory,
        )
        self.browse_btn.grid(row=0, column=2, sticky="e")

        # 3. Action Buttons Row (Download & Cancel)
        self.action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.action_frame.pack(fill="x", padx=16, pady=(6, 12))
        self.action_frame.grid_columnconfigure(0, weight=1)

        self.download_btn = ctk.CTkButton(
            self.action_frame,
            text="⬇ Download Video",
            font=Theme.FONT_HEADER,
            height=40,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._handle_download,
        )
        self.download_btn.grid(row=0, column=0, sticky="ew")

        self.cancel_btn = ctk.CTkButton(
            self.action_frame,
            text="✕ Cancel",
            font=Theme.FONT_SUBHEADER,
            height=40,
            width=100,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.ERROR,
            hover_color=Theme.ERROR_BG,
            command=self._handle_cancel,
        )
        self.cancel_btn.grid(row=0, column=1, padx=(10, 0), sticky="e")
        self.cancel_btn.grid_remove()

        # 4. Progress Section (Hidden when idle)
        self.progress_frame = ctk.CTkFrame(self, fg_color=Theme.BG_MAIN, corner_radius=Theme.RADIUS_CARD)
        self.progress_frame.pack(fill="x", padx=16, pady=(0, 12))
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.status_msg_label = ctk.CTkLabel(
            self.progress_frame,
            text="Ready",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_SECONDARY,
            anchor="w",
        )
        self.status_msg_label.grid(row=0, column=0, padx=14, pady=(10, 4), sticky="w")

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            height=8,
            corner_radius=4,
            progress_color=Theme.PRIMARY,
            fg_color=Theme.BG_MUTED,
        )
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=1, column=0, padx=14, pady=4, sticky="ew")

        self.metrics_frame = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        self.metrics_frame.grid(row=2, column=0, padx=14, pady=(2, 10), sticky="ew")
        self.metrics_frame.grid_columnconfigure(1, weight=1)

        self.percent_label = ctk.CTkLabel(
            self.metrics_frame,
            text="0%",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_PRIMARY,
        )
        self.percent_label.grid(row=0, column=0, sticky="w")

        self.speed_label = ctk.CTkLabel(
            self.metrics_frame,
            text="Speed: -- KB/s",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
        )
        self.speed_label.grid(row=0, column=1, sticky="w", padx=20)

        self.eta_label = ctk.CTkLabel(
            self.metrics_frame,
            text="ETA: --:--",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
        )
        self.eta_label.grid(row=0, column=2, sticky="e")

        self.progress_frame.pack_forget()

        # Bind configure listener for responsive layout
        self.bind("<Configure>", self._on_configure)

        # Initialize button state
        self._update_download_button_text()

    def set_selected_result(self, result: Optional[SearchResult]):
        """Updates selected search result in panel and probes available resolutions for restrictions."""
        self.selected_result = result
        self._probe_error_message = None
        if result:
            self.selected_title_label.configure(
                text=f"Selected: {result.display_title}",
                text_color=Theme.TEXT_ACCENT,
            )
            self.download_btn.configure(state="normal")
            self._cached_video_resolutions = []

            # Asynchronously probe available resolutions for account restriction detection
            search_service.get_available_resolutions_async(
                result.url or result.video_id,
                self._on_resolutions_probed,
            )
        else:
            self.selected_title_label.configure(
                text="No video selected",
                text_color=Theme.TEXT_MUTED,
            )
            self._cached_video_resolutions = []

        self._update_download_button_text()

    def _on_resolutions_probed(self, resolutions: List[str], error_message: Optional[str] = None):
        """Called when video resolutions are probed asynchronously."""
        if resolutions:
            self._cached_video_resolutions = resolutions
            self._probe_error_message = None
        else:
            self._probe_error_message = error_message or "Formats unavailable"
            err_lower = self._probe_error_message.lower()
            if "account access" in err_lower or "membership" in err_lower or "private" in err_lower:
                self._cached_video_resolutions = ["[ Account Restricted ]"]
            else:
                self._cached_video_resolutions = ["[ Formats Unavailable ]"]
        self.after(0, self._refresh_video_resolutions)

    def _refresh_video_resolutions(self):
        self._update_download_button_text()

    def set_selected_format(self, media_format: MediaFormat):
        """Programmatically updates format on the selected result and refreshes UI."""
        if self.selected_result:
            self.selected_result.download_format = media_format
            self._update_download_button_text()

    def set_batch_selected_items(self, items: List[SearchResult]):
        """Updates the list of results checked for batch download."""
        self._batch_items = list(items)
        self._update_download_button_text()

    def _update_download_button_text(self):
        if self._is_downloading:
            self.download_btn.configure(text="Downloading...", state="normal")
            return

        if self._batch_items:
            count = len(self._batch_items)
            self.download_btn.configure(
                text=f"⬇ Download {count} Selected Video{'s' if count > 1 else ''}",
                state="normal",
            )
            self.selected_title_label.configure(text=f"{count} videos selected for download")
            return

        if self.selected_result:
            self.selected_title_label.configure(text=self.selected_result.display_title)
            card_fmt = getattr(self.selected_result, "download_format", MediaFormat.MP4)
            card_q = getattr(self.selected_result, "download_quality", "720p")
            fmt_str = card_fmt.value if (card_fmt and hasattr(card_fmt, "value")) else str(card_fmt)
            q_str = str(card_q).split()[0] if card_q else ""

            if self._cached_video_resolutions and self._cached_video_resolutions[0].startswith("["):
                # Format probe indicated an account error or restriction
                self.download_btn.configure(
                    text=f"⚠️ {self._cached_video_resolutions[0]}",
                    state="disabled",
                )
                return

            btn_label = f"⬇ Download Video ({fmt_str} {q_str})".strip()
            self.download_btn.configure(text=btn_label, state="normal")
        else:
            self.selected_title_label.configure(text="No video selected")
            self.download_btn.configure(text="⬇ Download Video", state="disabled")

    def _browse_directory(self):
        chosen = filedialog.askdirectory(
            initialdir=self.folder_entry.get(),
            title="Select Download Destination Folder",
        )
        if chosen:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, chosen)
            config_manager.update(download_directory=chosen)

    def _on_folder_entry_changed(self):
        val = self.folder_entry.get().strip()
        if val and Path(val).exists():
            config_manager.update(download_directory=val)

    def get_save_directory(self) -> str:
        val = self.folder_entry.get().strip()
        if not val:
            val = str(Path.home() / "Downloads" / "Vyntra")
        return val

    def get_selected_format(self) -> MediaFormat:
        if self.selected_result and hasattr(self.selected_result, "download_format"):
            fmt = self.selected_result.download_format
            if isinstance(fmt, MediaFormat):
                return fmt
            return MediaFormat.MP3 if str(fmt) == MediaFormat.MP3.value else MediaFormat.MP4
        return MediaFormat.MP3 if config_manager.config.default_format == MediaFormat.MP3.value else MediaFormat.MP4

    def get_selected_quality(self) -> str:
        if self.selected_result and getattr(self.selected_result, "download_quality", None):
            return self.selected_result.download_quality
        return config_manager.config.audio_quality

    def update_progress(self, prog: ProgressInfo):
        """Updates the progress bar and labels in real-time."""
        fraction = max(0.0, min(1.0, prog.percent / 100.0))
        self.progress_bar.set(fraction)
        self.percent_label.configure(text=f"{prog.percent:.1f}%")
        self.speed_label.configure(text=f"Speed: {prog.speed_str}")
        self.eta_label.configure(text=f"ETA: {prog.eta_str}")
        self.status_msg_label.configure(text=prog.status_message)

    def set_downloading(self, downloading: bool):
        """Toggles active download state and UI controls."""
        self._is_downloading = downloading
        if downloading:
            self.progress_frame.pack(fill="x", padx=16, pady=(0, 12))
            self.download_btn.configure(state="disabled", text="Downloading...")
            self.browse_btn.configure(state="disabled")
            self.folder_entry.configure(state="disabled")
            self.cancel_btn.grid()
        else:
            self.browse_btn.configure(state="normal")
            self.folder_entry.configure(state="normal")
            self.cancel_btn.grid_remove()
            self._update_download_button_text()

    def _handle_download(self):
        if self._is_downloading:
            return
        if not self._batch_items and not self.selected_result:
            return

        chosen_dir = self.get_save_directory()
        if chosen_dir:
            config_manager.update(download_directory=chosen_dir)
        self.set_downloading(True)

        if self.on_download:
            if self._batch_items:
                primary = self._batch_items[0]
                primary_fmt = getattr(primary, "download_format", self.get_selected_format())
                primary_q = getattr(primary, "download_quality", self.get_selected_quality())
                try:
                    self.on_download(
                        primary,
                        primary_fmt,
                        primary_q,
                        chosen_dir,
                        batch_items=self._batch_items,
                    )
                except TypeError:
                    self.on_download(
                        primary,
                        primary_fmt,
                        primary_q,
                        chosen_dir,
                    )
            else:
                card_fmt = getattr(self.selected_result, "download_format", self.get_selected_format())
                card_q = getattr(self.selected_result, "download_quality", self.get_selected_quality())
                self.on_download(
                    self.selected_result,
                    card_fmt,
                    card_q,
                    chosen_dir,
                )

    def _handle_cancel(self):
        if self.on_cancel:
            self.on_cancel()
        self.status_msg_label.configure(text="Cancelling download...")

    def _on_configure(self, event):
        """Adapts title wraplength dynamically based on panel width."""
        width = event.width
        if width <= 1:
            return

        if hasattr(self, "selected_title_label") and self.selected_title_label.winfo_exists():
            self.selected_title_label.configure(wraplength=max(180, width - 200))
