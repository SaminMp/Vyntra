"""
Download control panel with dynamic format selection, quality picker, folder picker, and live progress indicators.
"""

from pathlib import Path
from tkinter import filedialog
from typing import Callable, List, Optional
import customtkinter as ctk

from vyntra.config import config_manager
from vyntra.models import AudioQuality, DownloadStatus, MediaFormat, ProgressInfo, SearchResult, VideoQuality
from vyntra.services.search_service import search_service
from vyntra.ui.theme import Theme

AUDIO_QUALITY_OPTIONS = [
    "Best (320 kbps)",
    "320 kbps",
    "256 kbps",
    "192 kbps",
    "128 kbps",
]

DEFAULT_VIDEO_QUALITY_OPTIONS = [
    "Best (Auto)",
    "1080p",
    "720p",
    "480p",
    "360p",
]


class DownloadPanel(ctk.CTkFrame):
    """Panel managing media format, dynamic video/audio quality, download directory, and progress feedback."""

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
        self._is_downloading = False
        self._cached_video_resolutions: List[str] = list(DEFAULT_VIDEO_QUALITY_OPTIONS)
        self._probe_error_message: Optional[str] = None
        self._is_compact_layout: Optional[bool] = None

        self.grid_columnconfigure(0, weight=1)

        # 1. Header & Selection Summary
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=16, pady=(14, 6))
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

        # 2. Options Row: Format & Quality (Adaptive Grid)
        self.options_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.options_frame.pack(fill="x", padx=16, pady=(2, 6))

        # Format Segmented Button
        self.fmt_label = ctk.CTkLabel(
            self.options_frame,
            text="Format:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )

        self.format_segmented = ctk.CTkSegmentedButton(
            self.options_frame,
            values=[MediaFormat.MP3.value, MediaFormat.MP4.value],
            font=Theme.FONT_SUBHEADER,
            selected_color=Theme.PRIMARY,
            selected_hover_color=Theme.PRIMARY_HOVER,
            unselected_color=Theme.BG_MUTED,
            unselected_hover_color=Theme.BG_CARD_HOVER,
            command=self._on_format_changed,
        )
        self.format_segmented.set(config_manager.config.default_format)

        # Dynamic Quality Selector (Audio bitrate for MP3 / Video resolution for MP4)
        self.quality_label = ctk.CTkLabel(
            self.options_frame,
            text="Audio Quality:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )

        self.quality_option = ctk.CTkOptionMenu(
            self.options_frame,
            values=AUDIO_QUALITY_OPTIONS,
            font=Theme.FONT_BODY,
            fg_color=Theme.BG_MUTED,
            button_color=Theme.PRIMARY,
            button_hover_color=Theme.PRIMARY_HOVER,
            dropdown_fg_color=Theme.BG_CARD,
            command=self._on_quality_changed,
        )
        self.quality_option.set(AUDIO_QUALITY_OPTIONS[0])

        self._regrid_options(is_compact=False)

        # Bind configure listener for responsive layout
        self.bind("<Configure>", self._on_configure)

        # 3. Destination Row (Folder Picker)
        self.folder_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.folder_frame.pack(fill="x", padx=16, pady=(2, 6))
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

        # 4. Action Buttons Row (Download & Cancel)
        self.action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.action_frame.pack(fill="x", padx=16, pady=(8, 12))
        self.action_frame.grid_columnconfigure(0, weight=1)

        self.download_btn = ctk.CTkButton(
            self.action_frame,
            text="⬇ Download",
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

        # 5. Progress Section (Hidden when idle)
        self.progress_frame = ctk.CTkFrame(self, fg_color=Theme.BG_MAIN, corner_radius=Theme.RADIUS_CARD)
        self.progress_frame.pack(fill="x", padx=16, pady=(0, 14))
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

        # Initialize labels based on current format
        self._update_quality_ui()

    def set_selected_result(self, result: Optional[SearchResult]):
        """Updates selected search result in panel and probes available resolutions."""
        self.selected_result = result
        self._probe_error_message = None
        if result:
            self.selected_title_label.configure(
                text=f"Selected: {result.display_title}",
                text_color=Theme.TEXT_ACCENT,
            )
            self.download_btn.configure(state="normal")

            # Reset cached resolutions while probing new video to avoid showing stale values
            self._cached_video_resolutions = ["Probing formats..."]
            if self.format_segmented.get() == MediaFormat.MP4.value:
                self.quality_option.configure(values=self._cached_video_resolutions)
                self.quality_option.set("Probing formats...")

            # Asynchronously probe available resolutions for this specific video
            search_service.get_available_resolutions_async(
                result.url or result.video_id,
                self._on_resolutions_probed,
            )
        else:
            self.selected_title_label.configure(
                text="No video selected",
                text_color=Theme.TEXT_MUTED,
            )
            self._cached_video_resolutions = list(DEFAULT_VIDEO_QUALITY_OPTIONS)
            if self.format_segmented.get() == MediaFormat.MP4.value:
                self.quality_option.configure(values=self._cached_video_resolutions)
                self.quality_option.set(self._cached_video_resolutions[0])

        self._update_download_button_text()

    def _on_resolutions_probed(self, resolutions: List[str], error_message: Optional[str] = None):
        """Called when video resolutions are probed asynchronously."""
        if resolutions:
            self._cached_video_resolutions = resolutions
            self._probe_error_message = None
        else:
            self._probe_error_message = error_message or "Formats unavailable"
            if "cookies" in self._probe_error_message.lower() or "verification" in self._probe_error_message.lower() or "bot" in self._probe_error_message.lower():
                self._cached_video_resolutions = ["[ Verification Required ]"]
            else:
                self._cached_video_resolutions = ["[ Formats Unavailable ]"]
        self.after(0, self._refresh_video_resolutions)

    def _refresh_video_resolutions(self):
        if self.format_segmented.get() == MediaFormat.MP4.value:
            current = self.quality_option.get()
            self.quality_option.configure(values=self._cached_video_resolutions)
            if current not in self._cached_video_resolutions:
                self.quality_option.set(self._cached_video_resolutions[0])
            self._update_download_button_text()

    def _on_format_changed(self, value: str):
        config_manager.update(default_format=value)
        self._update_quality_ui()

    def set_selected_format(self, media_format: MediaFormat):
        """Programmatically sets format segmented button and updates quality UI."""
        self.format_segmented.set(media_format.value)
        self._on_format_changed(media_format.value)

    def _update_quality_ui(self):
        fmt = self.format_segmented.get()
        if fmt == MediaFormat.MP3.value:
            self.quality_label.configure(text="Audio Quality:")
            self.quality_option.configure(values=AUDIO_QUALITY_OPTIONS)
            current_q = config_manager.config.audio_quality
            matched = [opt for opt in AUDIO_QUALITY_OPTIONS if current_q in opt]
            self.quality_option.set(matched[0] if matched else AUDIO_QUALITY_OPTIONS[0])
        else:
            self.quality_label.configure(text="Video Quality:")
            self.quality_option.configure(values=self._cached_video_resolutions)
            self.quality_option.set(self._cached_video_resolutions[0])

        self._update_download_button_text()

    def _on_quality_changed(self, value: str):
        self._update_download_button_text()

    def _update_download_button_text(self):
        if self._is_downloading:
            self.download_btn.configure(text="Downloading...", state="normal")
            return

        fmt = self.format_segmented.get()
        q = self.quality_option.get()

        if fmt == MediaFormat.MP4.value and self._cached_video_resolutions and self._cached_video_resolutions[0].startswith("["):
            # Format probe indicated an honest error or restriction (NO fake fallbacks)
            self.download_btn.configure(
                text=f"⚠️ {self._cached_video_resolutions[0]}",
                state="disabled",
            )
            return

        self.download_btn.configure(state="normal" if self.selected_result else "disabled")
        q_preview = q.split()[0] if q else ""
        self.download_btn.configure(text=f"⬇ Download {fmt} ({q_preview})")

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
        val = self.format_segmented.get()
        return MediaFormat.MP3 if val == MediaFormat.MP3.value else MediaFormat.MP4

    def get_selected_quality(self) -> str:
        return self.quality_option.get()

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
            self.quality_option.configure(state="disabled")
            self.browse_btn.configure(state="disabled")
            self.folder_entry.configure(state="disabled")
            self.cancel_btn.grid()
        else:
            self.format_segmented.configure(state="normal")
            self.quality_option.configure(state="normal")
            self.browse_btn.configure(state="normal")
            self.folder_entry.configure(state="normal")
            self.cancel_btn.grid_remove()
            self._update_download_button_text()

    def _handle_download(self):
        if self._is_downloading or not self.selected_result:
            return
        chosen_dir = self.get_save_directory()
        if chosen_dir:
            config_manager.update(download_directory=chosen_dir)
        self.set_downloading(True)
        if self.on_download:
            self.on_download(
                self.selected_result,
                self.get_selected_format(),
                self.get_selected_quality(),
                chosen_dir,
            )

    def _handle_cancel(self):
        if self.on_cancel:
            self.on_cancel()
        self.status_msg_label.configure(text="Cancelling download...")

    def _on_configure(self, event):
        """Adapts options row and title wraplength dynamically based on panel width."""
        width = event.width
        if width <= 1:
            return

        if hasattr(self, "selected_title_label") and self.selected_title_label.winfo_exists():
            self.selected_title_label.configure(wraplength=max(180, width - 200))

        is_compact = width < 660
        if is_compact != self._is_compact_layout:
            self._is_compact_layout = is_compact
            self._regrid_options(is_compact)

    def _regrid_options(self, is_compact: bool):
        """Arranges format and quality controls into single row (wide) or 2 rows (compact)."""
        if is_compact:
            self.options_frame.grid_columnconfigure((0, 1), weight=0)
            self.options_frame.grid_columnconfigure((2, 3), weight=0)
            self.fmt_label.grid(row=0, column=0, padx=(0, 8), pady=3, sticky="w")
            self.format_segmented.grid(row=0, column=1, padx=(0, 8), pady=3, sticky="w")
            self.quality_label.grid(row=1, column=0, padx=(0, 8), pady=3, sticky="w")
            self.quality_option.grid(row=1, column=1, padx=(0, 8), pady=3, sticky="w")
        else:
            self.options_frame.grid_columnconfigure((0, 1, 2, 3), weight=0)
            self.fmt_label.grid(row=0, column=0, padx=(0, 8), pady=2, sticky="w")
            self.format_segmented.grid(row=0, column=1, padx=(0, 20), pady=2, sticky="w")
            self.quality_label.grid(row=0, column=2, padx=(0, 8), pady=2, sticky="w")
            self.quality_option.grid(row=0, column=3, pady=2, sticky="w")

