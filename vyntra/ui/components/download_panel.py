"""
Download control panel with format selection, folder picker, and live progress indicators.
"""

from pathlib import Path
from tkinter import filedialog
from typing import Callable, Optional
import customtkinter as ctk

from vyntra.config import config_manager
from vyntra.models import AudioQuality, DownloadStatus, MediaFormat, ProgressInfo, SearchResult, VideoQuality
from vyntra.ui.theme import Theme


class DownloadPanel(ctk.CTkFrame):
    """Panel managing media format, download directory, and progress feedback."""

    def __init__(
        self,
        master,
        on_download: Callable[[SearchResult, MediaFormat, str], None],
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
        self._is_downloading = False

        self.grid_columnconfigure(0, weight=1)

        # 1. Header & Selection Summary
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=16, pady=(14, 8))
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
            wraplength=450,
        )
        self.selected_title_label.grid(row=0, column=1, padx=(10, 0), sticky="e")

        # 2. Controls Row (Format Selector + Folder Picker)
        self.controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.controls_frame.pack(fill="x", padx=16, pady=6)
        self.controls_frame.grid_columnconfigure(1, weight=1)

        # Format Segmented Button
        self.format_label = ctk.CTkLabel(
            self.controls_frame,
            text="Format:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )
        self.format_label.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.format_segmented = ctk.CTkSegmentedButton(
            self.controls_frame,
            values=[MediaFormat.MP3.value, MediaFormat.MP4.value],
            font=Theme.FONT_SUBHEADER,
            selected_color=Theme.PRIMARY,
            selected_hover_color=Theme.PRIMARY_HOVER,
            unselected_color=Theme.BG_MUTED,
            unselected_hover_color=Theme.BG_CARD_HOVER,
            command=self._on_format_changed,
        )
        self.format_segmented.set(config_manager.config.default_format)
        self.format_segmented.grid(row=0, column=1, padx=(0, 20), sticky="w")

        # Folder Picker
        self.folder_label = ctk.CTkLabel(
            self.controls_frame,
            text="Save to:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )
        self.folder_label.grid(row=0, column=2, padx=(0, 8), sticky="w")

        self.folder_entry = ctk.CTkEntry(
            self.controls_frame,
            font=Theme.FONT_CAPTION,
            fg_color=Theme.BG_INPUT,
            border_color=Theme.BORDER_CARD,
            height=32,
            width=260,
        )
        self.folder_entry.insert(0, config_manager.config.download_directory)
        self.folder_entry.grid(row=0, column=3, padx=(0, 8), sticky="ew")

        self.browse_btn = ctk.CTkButton(
            self.controls_frame,
            text="Browse...",
            font=Theme.FONT_CAPTION,
            width=75,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._browse_directory,
        )
        self.browse_btn.grid(row=0, column=4, sticky="e")

        # 3. Action Buttons Row (Download & Cancel)
        self.action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.action_frame.pack(fill="x", padx=16, pady=(8, 12))
        self.action_frame.grid_columnconfigure(0, weight=1)

        self.download_btn = ctk.CTkButton(
            self.action_frame,
            text=f"⬇ Download {self.format_segmented.get()}",
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
        # Cancel button is hidden by default
        self.cancel_btn.grid(row=0, column=1, padx=(10, 0), sticky="e")
        self.cancel_btn.grid_remove()

        # 4. Progress Section (Hidden when idle)
        self.progress_frame = ctk.CTkFrame(self, fg_color=Theme.BG_MAIN, corner_radius=Theme.RADIUS_CARD)
        self.progress_frame.pack(fill="x", padx=16, pady=(0, 14))
        self.progress_frame.grid_columnconfigure(0, weight=1)

        # Status text & filename
        self.status_msg_label = ctk.CTkLabel(
            self.progress_frame,
            text="Ready",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_SECONDARY,
            anchor="w",
        )
        self.status_msg_label.grid(row=0, column=0, padx=14, pady=(10, 4), sticky="w")

        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            height=8,
            corner_radius=4,
            progress_color=Theme.PRIMARY,
            fg_color=Theme.BG_MUTED,
        )
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=1, column=0, padx=14, pady=4, sticky="ew")

        # Metrics Row (Percentage, Speed, ETA)
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

    def set_selected_result(self, result: Optional[SearchResult]):
        """Updates selected search result in panel."""
        self.selected_result = result
        if result:
            self.selected_title_label.configure(
                text=f"Selected: {result.display_title}",
                text_color=Theme.TEXT_ACCENT,
            )
            self.download_btn.configure(state="normal")
        else:
            self.selected_title_label.configure(
                text="No video selected",
                text_color=Theme.TEXT_MUTED,
            )

    def _on_format_changed(self, value: str):
        self.download_btn.configure(text=f"⬇ Download {value}")
        config_manager.update(default_format=value)

    def _browse_directory(self):
        chosen = filedialog.askdirectory(
            initialdir=self.folder_entry.get(),
            title="Select Download Destination Folder",
        )
        if chosen:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, chosen)
            config_manager.update(download_directory=chosen)

    def get_save_directory(self) -> str:
        val = self.folder_entry.get().strip()
        if not val:
            val = str(Path.home() / "Downloads" / "Vyntra")
        return val

    def get_selected_format(self) -> MediaFormat:
        val = self.format_segmented.get()
        return MediaFormat.MP3 if val == MediaFormat.MP3.value else MediaFormat.MP4

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
            self.progress_frame.pack(fill="x", padx=16, pady=(0, 14))
            self.download_btn.configure(state="disabled", text="Downloading...")
            self.format_segmented.configure(state="disabled")
            self.browse_btn.configure(state="disabled")
            self.folder_entry.configure(state="disabled")
            self.cancel_btn.grid()
        else:
            self.download_btn.configure(state="normal", text=f"⬇ Download {self.format_segmented.get()}")
            self.format_segmented.configure(state="normal")
            self.browse_btn.configure(state="normal")
            self.folder_entry.configure(state="normal")
            self.cancel_btn.grid_remove()

    def _handle_download(self):
        if self._is_downloading or not self.selected_result:
            return
        self.set_downloading(True)
        if self.on_download:
            self.on_download(self.selected_result, self.get_selected_format(), self.get_save_directory())

    def _handle_cancel(self):
        if self.on_cancel:
            self.on_cancel()
        self.status_msg_label.configure(text="Cancelling download...")
