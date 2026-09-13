"""
Update notification and progress modal dialog for Vyntra.
Displays release notes, package details, real-time download progress,
and triggers detached platform installation and application restart.
"""

from typing import Optional
import customtkinter as ctk

from vyntra.ui.theme import Theme
from vyntra.updater.manager import update_manager
from vyntra.updater.models import DownloadProgress, UpdateCheckResult
from vyntra.utils.logger import logger


class UpdateModal(ctk.CTkToplevel):
    """Interactive dialog presenting new release details and download lifecycle."""

    def __init__(self, master, check_result: UpdateCheckResult, **kwargs):
        super().__init__(master, **kwargs)

        self.check_result = check_result
        self.release_info = check_result.latest_release
        self.target_asset = check_result.target_asset

        target_version = self.release_info.version if self.release_info else "Unknown"
        self.title(f"Vyntra Update - v{target_version} Available")
        self.geometry("560x520")
        self.minsize(500, 440)
        self.configure(fg_color=Theme.BG_MAIN)

        try:
            self.transient(master)
            if master and master.winfo_ismapped():
                self.grab_set()
        except Exception:
            pass

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # 1. Header Banner
        header_frame = ctk.CTkFrame(self, fg_color=Theme.BG_SIDEBAR, height=64, corner_radius=0)
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        title_label = ctk.CTkLabel(
            header_frame,
            text="🚀  New Version Available",
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_PRIMARY,
        )
        title_label.grid(row=0, column=0, padx=20, pady=16, sticky="w")

        # 2. Version Comparison Box
        version_box = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        version_box.grid(row=1, column=0, sticky="ew", padx=20, pady=(16, 10))
        version_box.grid_columnconfigure((0, 1, 2), weight=1)

        curr_ver = check_result.current_version
        new_ver = target_version
        size_mb = self.target_asset.size_mb if self.target_asset else 0.0

        ctk.CTkLabel(
            version_box,
            text=f"Installed Version:\nv{curr_ver}",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED,
            justify="center",
        ).grid(row=0, column=0, padx=12, pady=12)

        ctk.CTkLabel(
            version_box,
            text="➜",
            font=(Theme.FONT_FAMILY, 20, "bold"),
            text_color=Theme.PRIMARY,
        ).grid(row=0, column=1, pady=12)

        ctk.CTkLabel(
            version_box,
            text=f"Latest Release:\nv{new_ver}  ({size_mb:.1f} MB)",
            font=(Theme.FONT_FAMILY, 13, "bold"),
            text_color=Theme.SUCCESS,
            justify="center",
        ).grid(row=0, column=2, padx=12, pady=12)

        # 3. Release Notes Container
        notes_frame = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        notes_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 14))
        notes_frame.grid_columnconfigure(0, weight=1)
        notes_frame.grid_rowconfigure(1, weight=1)

        notes_title = ctk.CTkLabel(
            notes_frame,
            text="What's New in this Release:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )
        notes_title.grid(row=0, column=0, padx=14, pady=(10, 4), sticky="w")

        self.notes_box = ctk.CTkTextbox(
            notes_frame,
            fg_color="#070B12",
            text_color=Theme.TEXT_PRIMARY,
            font=Theme.FONT_CAPTION,
            wrap="word",
            corner_radius=6,
        )
        self.notes_box.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 12))

        notes_text = self.release_info.release_notes if self.release_info else "No release notes available."
        self.notes_box.insert("1.0", notes_text)
        self.notes_box.configure(state="disabled")

        # 4. Download Progress Section (initially hidden)
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            height=10,
            corner_radius=5,
            progress_color=Theme.PRIMARY,
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            self.progress_frame,
            text="Ready to update.",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
        )
        self.status_label.grid(row=1, column=0, sticky="w")
        self.progress_frame.grid_remove()

        # 5. Bottom Actions
        self.actions_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.actions_frame.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 16))
        self.actions_frame.grid_columnconfigure(0, weight=1)

        self.later_btn = ctk.CTkButton(
            self.actions_frame,
            text="Later",
            font=Theme.FONT_BODY,
            width=90,
            height=34,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            text_color=Theme.TEXT_SECONDARY,
            command=self.destroy,
        )
        self.later_btn.pack(side="right", padx=(8, 0))

        self.update_btn = ctk.CTkButton(
            self.actions_frame,
            text="Update Vyntra Now",
            font=(Theme.FONT_FAMILY, 13, "bold"),
            width=160,
            height=34,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._start_update_download,
        )
        self.update_btn.pack(side="right")

    def _start_update_download(self):
        """Disables buttons, displays progress bar, and starts download process."""
        self.update_btn.configure(state="disabled", text="Downloading...")
        self.later_btn.configure(state="disabled")
        self.progress_frame.grid()
        self.status_label.configure(text="Connecting to GitHub...", text_color=Theme.TEXT_MUTED)

        update_manager.download_and_install_update(
            on_progress=self._on_download_progress,
            on_error=self._on_download_error,
        )

    def _on_download_progress(self, prog: DownloadProgress):
        """Thread-safe UI update for download progress."""
        if not self.winfo_exists():
            return

        def update():
            if not self.winfo_exists():
                return
            self.progress_bar.set(prog.percent / 100.0)
            if prog.is_complete:
                self.status_label.configure(text=prog.status_text, text_color=Theme.SUCCESS)
                self.update_btn.configure(text="Installing...")
            else:
                speed_str = f" | {prog.speed_mbps:.1f} MB/s" if prog.speed_mbps > 0 else ""
                self.status_label.configure(
                    text=f"{prog.status_text} ({prog.percent:.0f}%{speed_str})",
                    text_color=Theme.TEXT_PRIMARY,
                )

        self.after(0, update)

    def _on_download_error(self, err_msg: str):
        """Thread-safe UI update on download or verification error."""
        if not self.winfo_exists():
            return

        def show_err():
            if not self.winfo_exists():
                return
            self.status_label.configure(text=f"Error: {err_msg}", text_color=Theme.ERROR)
            self.update_btn.configure(state="normal", text="Retry Update")
            self.later_btn.configure(state="normal", text="Close")

        self.after(0, show_err)
