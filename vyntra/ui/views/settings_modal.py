"""
Settings and preferences modal dialog for Vyntra.
"""

from pathlib import Path
from tkinter import filedialog
from typing import Callable, Optional
import customtkinter as ctk

from vyntra.config import config_manager
from vyntra.models import AudioQuality, MediaFormat
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.ui.theme import Theme


class SettingsModal(ctk.CTkToplevel):
    """Configuration dialog for application preferences and diagnostics."""

    def __init__(self, master, on_saved: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(master, **kwargs)

        self.on_saved = on_saved
        self.title("Vyntra Settings")
        self.geometry("540x520")
        self.resizable(False, False)
        self.configure(fg_color=Theme.BG_MAIN)

        # Center modal on parent window
        self.transient(master)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)

        # Header Title
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=24, pady=(20, 14))

        title_label = ctk.CTkLabel(
            header_frame,
            text="⚙️ Preferences",
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_PRIMARY,
        )
        title_label.pack(anchor="w")

        # Scrollable Settings Container
        content_frame = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        content_frame.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        content_frame.grid_columnconfigure(1, weight=1)

        row = 0

        # 1. Default Download Directory
        dir_label = ctk.CTkLabel(
            content_frame,
            text="Default Download Directory:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )
        dir_label.grid(row=row, column=0, columnspan=2, padx=16, pady=(16, 4), sticky="w")
        row += 1

        self.dir_entry = ctk.CTkEntry(
            content_frame,
            font=Theme.FONT_CAPTION,
            fg_color=Theme.BG_INPUT,
            border_color=Theme.BORDER_CARD,
            height=32,
        )
        self.dir_entry.insert(0, config_manager.config.download_directory)
        self.dir_entry.grid(row=row, column=0, padx=(16, 8), pady=(0, 14), sticky="ew")

        browse_btn = ctk.CTkButton(
            content_frame,
            text="Browse",
            font=Theme.FONT_CAPTION,
            width=70,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._browse_folder,
        )
        browse_btn.grid(row=row, column=1, padx=(0, 16), pady=(0, 14), sticky="e")
        row += 1

        # 2. Default Format
        fmt_label = ctk.CTkLabel(
            content_frame,
            text="Default Format:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )
        fmt_label.grid(row=row, column=0, padx=16, pady=4, sticky="w")

        self.fmt_segmented = ctk.CTkSegmentedButton(
            content_frame,
            values=[MediaFormat.MP3.value, MediaFormat.MP4.value],
            font=Theme.FONT_BODY,
            selected_color=Theme.PRIMARY,
        )
        self.fmt_segmented.set(config_manager.config.default_format)
        self.fmt_segmented.grid(row=row, column=1, padx=16, pady=4, sticky="e")
        row += 1

        # 3. Audio Bitrate Quality
        bitrate_label = ctk.CTkLabel(
            content_frame,
            text="MP3 Audio Quality:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )
        bitrate_label.grid(row=row, column=0, padx=16, pady=4, sticky="w")

        self.bitrate_option = ctk.CTkOptionMenu(
            content_frame,
            values=["192 kbps (Standard)", "256 kbps (High)", "320 kbps (Best)"],
            font=Theme.FONT_BODY,
            fg_color=Theme.BG_MUTED,
            button_color=Theme.PRIMARY,
            button_hover_color=Theme.PRIMARY_HOVER,
            dropdown_fg_color=Theme.BG_CARD,
        )
        current_bitrate = config_manager.config.audio_quality
        if current_bitrate == "192":
            self.bitrate_option.set("192 kbps (Standard)")
        elif current_bitrate == "256":
            self.bitrate_option.set("256 kbps (High)")
        else:
            self.bitrate_option.set("320 kbps (Best)")
        self.bitrate_option.grid(row=row, column=1, padx=16, pady=4, sticky="e")
        row += 1

        # 4. Search Results Limit
        limit_label = ctk.CTkLabel(
            content_frame,
            text="Max Search Results:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )
        limit_label.grid(row=row, column=0, padx=16, pady=4, sticky="w")

        self.limit_option = ctk.CTkOptionMenu(
            content_frame,
            values=["8", "12", "16", "20", "25"],
            font=Theme.FONT_BODY,
            fg_color=Theme.BG_MUTED,
            button_color=Theme.PRIMARY,
            button_hover_color=Theme.PRIMARY_HOVER,
            dropdown_fg_color=Theme.BG_CARD,
        )
        self.limit_option.set(str(config_manager.config.max_search_results))
        self.limit_option.grid(row=row, column=1, padx=16, pady=4, sticky="e")
        row += 1

        # 5. FFmpeg Status / Diagnostics
        ffmpeg_box = ctk.CTkFrame(content_frame, fg_color=Theme.BG_MAIN, corner_radius=Theme.RADIUS_BUTTON)
        ffmpeg_box.grid(row=row, column=0, columnspan=2, padx=16, pady=12, sticky="ew")
        ffmpeg_box.grid_columnconfigure(0, weight=1)

        status = ffmpeg_service.get_status()
        status_text = f"✓ FFmpeg: Installed ({status.ffmpeg_path})" if status.is_available else "⚠️ FFmpeg: Not Found (Audio conversion will use native fallback)"
        status_color = Theme.SUCCESS if status.is_available else Theme.WARNING

        ffmpeg_info = ctk.CTkLabel(
            ffmpeg_box,
            text=status_text,
            font=Theme.FONT_CAPTION,
            text_color=status_color,
            justify="left",
            wraplength=450,
        )
        ffmpeg_info.pack(padx=12, pady=8, anchor="w")
        row += 1

        # Action Buttons (Save / Cancel)
        actions_frame = ctk.CTkFrame(self, fg_color="transparent")
        actions_frame.pack(fill="x", padx=24, pady=(0, 20))

        save_btn = ctk.CTkButton(
            actions_frame,
            text="Save Settings",
            font=Theme.FONT_SUBHEADER,
            height=36,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._save_settings,
        )
        save_btn.pack(side="right", padx=(8, 0))

        cancel_btn = ctk.CTkButton(
            actions_frame,
            text="Close",
            font=Theme.FONT_BODY,
            height=36,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self.destroy,
        )
        cancel_btn.pack(side="right")

    def _browse_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.dir_entry.get())
        if chosen:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, chosen)

    def _save_settings(self):
        dir_val = self.dir_entry.get().strip() or str(Path.home() / "Downloads" / "Vyntra")
        fmt_val = self.fmt_segmented.get()

        bitrate_str = self.bitrate_option.get()
        bitrate_val = "320"
        if "192" in bitrate_str:
            bitrate_val = "192"
        elif "256" in bitrate_str:
            bitrate_val = "256"

        limit_val = int(self.limit_option.get())

        config_manager.update(
            download_directory=dir_val,
            default_format=fmt_val,
            audio_quality=bitrate_val,
            max_search_results=limit_val,
        )

        if self.on_saved:
            self.on_saved()

        self.destroy()
