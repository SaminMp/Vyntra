"""
Settings and preferences modal dialog for Vyntra.
Provides user-facing preferences for downloads, Google Account sign-in,
application updates, and software information.
"""

from pathlib import Path
from tkinter import filedialog
from typing import Callable, Optional
import customtkinter as ctk

from vyntra import __app_name__, __version__
from vyntra.config import config_manager
from vyntra.models import MediaFormat
from vyntra.services.auth_service import auth_service
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.ui.theme import Theme
from vyntra.ui.views.donation_modal import DonationModal
from vyntra.ui.views.update_modal import UpdateModal
from vyntra.updater.manager import update_manager


class SettingsModal(ctk.CTkToplevel):
    """Configuration dialog for application preferences, Google account, and software updates."""

    def __init__(self, master, on_saved: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(master, **kwargs)

        self.on_saved = on_saved
        self.title(f"Vyntra Settings - v{__version__}")
        self.geometry("620x660")
        self.minsize(540, 520)
        self.configure(fg_color=Theme.BG_MAIN)

        try:
            if master and master.winfo_ismapped():
                self.transient(master)
                self.grab_set()
        except Exception:
            pass

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header Title
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))

        title_label = ctk.CTkLabel(
            header_frame,
            text="⚙️ Preferences & Account",
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_PRIMARY,
        )
        title_label.pack(anchor="w")

        # Scrollable Settings Container
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=Theme.BG_CARD,
            corner_radius=Theme.RADIUS_CARD,
        )
        self.scroll_frame.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 14))
        self.scroll_frame.grid_columnconfigure(1, weight=1)

        self._build_general_settings()
        self._build_account_settings()
        self._build_updates_section()
        self._build_donation_section()
        self._build_about_section()
        self._build_action_buttons()

    # -------------------------------------------------------------------------
    # 1. General Download Preferences
    # -------------------------------------------------------------------------
    def _build_general_settings(self):
        """General download destination, format, and search preferences."""
        row = 0

        sec_label = ctk.CTkLabel(
            self.scroll_frame,
            text="📁 Download Preferences",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_ACCENT,
        )
        sec_label.grid(row=row, column=0, columnspan=2, padx=16, pady=(12, 8), sticky="w")
        row += 1

        # 1. Download Directory
        dir_label = ctk.CTkLabel(
            self.scroll_frame,
            text="Save Destination:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )
        dir_label.grid(row=row, column=0, columnspan=2, padx=16, pady=(4, 2), sticky="w")
        row += 1

        self.dir_entry = ctk.CTkEntry(
            self.scroll_frame,
            font=Theme.FONT_CAPTION,
            fg_color=Theme.BG_INPUT,
            border_color=Theme.BORDER_CARD,
            height=32,
        )
        self.dir_entry.insert(0, config_manager.config.download_directory)
        self.dir_entry.grid(row=row, column=0, padx=(16, 8), pady=(0, 10), sticky="ew")

        browse_btn = ctk.CTkButton(
            self.scroll_frame,
            text="Browse",
            font=Theme.FONT_CAPTION,
            width=70,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._browse_folder,
        )
        browse_btn.grid(row=row, column=1, padx=(0, 16), pady=(0, 10), sticky="e")
        row += 1

        # 2. Default Format
        fmt_label = ctk.CTkLabel(
            self.scroll_frame,
            text="Default Format:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )
        fmt_label.grid(row=row, column=0, padx=16, pady=4, sticky="w")

        self.fmt_segmented = ctk.CTkSegmentedButton(
            self.scroll_frame,
            values=[MediaFormat.MP3.value, MediaFormat.MP4.value],
            font=Theme.FONT_BODY,
            selected_color=Theme.PRIMARY,
            command=self._on_format_toggled,
        )
        self.fmt_segmented.set(config_manager.config.default_format)
        self.fmt_segmented.grid(row=row, column=1, padx=16, pady=4, sticky="e")
        row += 1

        # 3. Dynamic Quality Setting
        self.quality_label = ctk.CTkLabel(
            self.scroll_frame,
            text="Default Quality:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )
        self.quality_label.grid(row=row, column=0, padx=16, pady=4, sticky="w")

        self.quality_option = ctk.CTkOptionMenu(
            self.scroll_frame,
            values=["320 kbps (Best)", "256 kbps (High)", "192 kbps (Standard)", "128 kbps"],
            font=Theme.FONT_BODY,
            fg_color=Theme.BG_MUTED,
            button_color=Theme.PRIMARY,
            button_hover_color=Theme.PRIMARY_HOVER,
            dropdown_fg_color=Theme.BG_CARD,
        )
        self.quality_option.grid(row=row, column=1, padx=16, pady=4, sticky="e")
        self._on_format_toggled(config_manager.config.default_format)
        row += 1

        # 4. Search Results Limit
        limit_label = ctk.CTkLabel(
            self.scroll_frame,
            text="Max Search Results:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )
        limit_label.grid(row=row, column=0, padx=16, pady=(4, 14), sticky="w")

        self.limit_option = ctk.CTkOptionMenu(
            self.scroll_frame,
            values=["8", "12", "16", "20", "25"],
            font=Theme.FONT_BODY,
            fg_color=Theme.BG_MUTED,
            button_color=Theme.PRIMARY,
            button_hover_color=Theme.PRIMARY_HOVER,
            dropdown_fg_color=Theme.BG_CARD,
        )
        self.limit_option.set(str(config_manager.config.max_search_results))
        self.limit_option.grid(row=row, column=1, padx=16, pady=(4, 14), sticky="e")
        self._next_row = row + 1

    # -------------------------------------------------------------------------
    # 2. Account Settings (Google Sign-In)
    # -------------------------------------------------------------------------
    def _build_account_settings(self):
        """In-app Google Account identity management."""
        row = self._next_row

        divider = ctk.CTkFrame(self.scroll_frame, height=1, fg_color=Theme.BORDER_CARD)
        divider.grid(row=row, column=0, columnspan=2, padx=16, pady=10, sticky="ew")
        row += 1

        auth_header = ctk.CTkLabel(
            self.scroll_frame,
            text="👤 Google Account",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_ACCENT,
        )
        auth_header.grid(row=row, column=0, columnspan=2, padx=16, pady=(12, 2), sticky="w")
        row += 1

        auth_sub = ctk.CTkLabel(
            self.scroll_frame,
            text="Sign in to access your YouTube playlists, subscriptions, and account metadata.",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
        )
        auth_sub.grid(row=row, column=0, columnspan=2, padx=16, pady=(0, 6), sticky="w")
        row += 1

        auth_box = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_MAIN, corner_radius=Theme.RADIUS_BUTTON)
        auth_box.grid(row=row, column=0, columnspan=2, padx=16, pady=(2, 10), sticky="ew")
        auth_box.grid_columnconfigure(0, weight=1)

        status_key, label, msg = auth_service.get_connection_status()
        status_color = Theme.SUCCESS if status_key == "connected" else Theme.TEXT_MUTED

        self.account_status_lbl = ctk.CTkLabel(
            auth_box,
            text=f"{label}  —  {msg}",
            font=Theme.FONT_CAPTION,
            text_color=status_color,
            wraplength=480,
            justify="left",
        )
        self.account_status_lbl.pack(padx=14, pady=(10, 8), anchor="w")

        btn_row = ctk.CTkFrame(auth_box, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 10))

        self.signin_btn = ctk.CTkButton(
            btn_row,
            text="🌐 Sign in with Google",
            font=Theme.FONT_CAPTION,
            height=30,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.ACCENT_CYAN,
            hover_color=Theme.ACCENT_CYAN_HOVER,
            command=self._run_signin,
        )
        self.signin_btn.pack(side="left", padx=(0, 8))

        self.signout_btn = ctk.CTkButton(
            btn_row,
            text="Sign Out",
            font=Theme.FONT_CAPTION,
            height=30,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.ERROR_BG,
            command=self._run_signout,
        )
        self.signout_btn.pack(side="left")

        row += 1
        self._next_row = row

    # -------------------------------------------------------------------------
    # 3. Application Updates
    # -------------------------------------------------------------------------
    def _build_updates_section(self):
        """Clean software update status and check trigger."""
        row = self._next_row

        divider = ctk.CTkFrame(self.scroll_frame, height=1, fg_color=Theme.BORDER_CARD)
        divider.grid(row=row, column=0, columnspan=2, padx=16, pady=10, sticky="ew")
        row += 1

        sec_label = ctk.CTkLabel(
            self.scroll_frame,
            text="Application Updates",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_ACCENT,
        )
        sec_label.grid(row=row, column=0, columnspan=2, padx=16, pady=(12, 6), sticky="w")
        row += 1

        info_box = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_INPUT, corner_radius=6)
        info_box.grid(row=row, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="ew")
        info_box.grid_columnconfigure(0, weight=1)

        self.updater_ver_lbl = ctk.CTkLabel(
            info_box,
            text=f"Installed Version: v{__version__}  |  Channel: Stable",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_PRIMARY,
        )
        self.updater_ver_lbl.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        self.updater_status_lbl = ctk.CTkLabel(
            info_box,
            text="Vyntra checks for new releases automatically in the background.",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            wraplength=480,
            justify="left",
        )
        self.updater_status_lbl.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")

        btn_bar = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        btn_bar.grid(row=row + 1, column=0, columnspan=2, padx=16, pady=(0, 8), sticky="ew")

        self.check_updates_btn = ctk.CTkButton(
            btn_bar,
            text="Check for Updates",
            font=Theme.FONT_CAPTION,
            height=30,
            width=140,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._on_check_updates_clicked,
        )
        self.check_updates_btn.pack(side="left")

        self.install_update_btn = ctk.CTkButton(
            btn_bar,
            text="Update Vyntra Now",
            font=(Theme.FONT_FAMILY, 11, "bold"),
            height=30,
            width=140,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.SUCCESS,
            hover_color="#059669",
            command=self._on_open_update_modal_clicked,
        )
        self.install_update_btn.pack(side="left", padx=10)
        self.install_update_btn.pack_forget()

        # If an update is already discovered, show the install button immediately
        if update_manager.last_result and update_manager.last_result.has_update:
            self.install_update_btn.pack(side="left", padx=10)
            v = update_manager.last_result.latest_release.version if update_manager.last_result.latest_release else ""
            self.updater_status_lbl.configure(text=f"New version v{v} is available!", text_color=Theme.SUCCESS)

        self._next_row = row + 2

    # -------------------------------------------------------------------------
    # 4. Donation & Support
    # -------------------------------------------------------------------------
    def _build_donation_section(self):
        """Support Vyntra development and prompt preferences."""
        row = self._next_row

        divider = ctk.CTkFrame(self.scroll_frame, height=1, fg_color=Theme.BORDER_CARD)
        divider.grid(row=row, column=0, columnspan=2, padx=16, pady=10, sticky="ew")
        row += 1

        sec_label = ctk.CTkLabel(
            self.scroll_frame,
            text="💖 Support Vyntra",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_ACCENT,
        )
        sec_label.grid(row=row, column=0, columnspan=2, padx=16, pady=(12, 6), sticky="w")
        row += 1

        info_box = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_INPUT, corner_radius=6)
        info_box.grid(row=row, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="ew")
        info_box.grid_columnconfigure(0, weight=1)

        desc_lbl = ctk.CTkLabel(
            info_box,
            text="Vyntra is free and open-source. Consider supporting development with a USDT contribution.",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            justify="left",
        )
        desc_lbl.grid(row=0, column=0, padx=12, pady=(10, 8), sticky="w")

        btn_bar = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        btn_bar.grid(row=row + 1, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="ew")

        self.donate_btn = ctk.CTkButton(
            btn_bar,
            text="Support with USDT",
            font=(Theme.FONT_FAMILY, 11, "bold"),
            height=30,
            width=160,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._on_donate_clicked,
        )
        self.donate_btn.pack(side="left", padx=(0, 14))

        self.donation_prompt_var = ctk.BooleanVar(value=not config_manager.config.donation_prompt_dismissed)
        self.donation_prompt_chk = ctk.CTkCheckBox(
            btn_bar,
            text="Show prompt after downloads",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_SECONDARY,
            variable=self.donation_prompt_var,
            checkbox_width=18,
            checkbox_height=18,
            corner_radius=4,
        )
        self.donation_prompt_chk.pack(side="left")

        self._next_row = row + 2

    def _on_donate_clicked(self):
        DonationModal(self)

    # -------------------------------------------------------------------------
    # 5. About Vyntra
    # -------------------------------------------------------------------------
    def _build_about_section(self):
        """Information about Vyntra and system dependencies."""
        row = self._next_row

        divider = ctk.CTkFrame(self.scroll_frame, height=1, fg_color=Theme.BORDER_CARD)
        divider.grid(row=row, column=0, columnspan=2, padx=16, pady=10, sticky="ew")
        row += 1

        about_header = ctk.CTkLabel(
            self.scroll_frame,
            text="ℹ️ About Vyntra",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_ACCENT,
        )
        about_header.grid(row=row, column=0, columnspan=2, padx=16, pady=(12, 6), sticky="w")
        row += 1

        about_box = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_INPUT, corner_radius=6)
        about_box.grid(row=row, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="ew")

        about_text = ctk.CTkLabel(
            about_box,
            text=f"{__app_name__} — Desktop Multi-Platform Media Downloader & Player\nVersion: v{__version__}",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_PRIMARY,
            justify="left",
        )
        about_text.pack(anchor="w", padx=12, pady=(10, 4))

        status = ffmpeg_service.get_status()
        ffmpeg_text = f"✓ Audio Engine (FFmpeg): Available" if status.is_available else "⚠️ Audio Engine: FFmpeg not detected"
        ffmpeg_color = Theme.SUCCESS if status.is_available else Theme.WARNING

        ffmpeg_lbl = ctk.CTkLabel(
            about_box,
            text=ffmpeg_text,
            font=Theme.FONT_CAPTION,
            text_color=ffmpeg_color,
            justify="left",
        )
        ffmpeg_lbl.pack(anchor="w", padx=12, pady=(0, 10))

        self._next_row = row + 1

    # -------------------------------------------------------------------------
    # Actions and Event Handlers
    # -------------------------------------------------------------------------
    def _browse_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.dir_entry.get())
        if chosen:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, chosen)

    def _on_format_toggled(self, value: str):
        if value == MediaFormat.MP3.value:
            self.quality_label.configure(text="Default Audio Quality:")
            self.quality_option.configure(values=["320 kbps (Best)", "256 kbps (High)", "192 kbps (Standard)", "128 kbps"])
            curr = config_manager.config.audio_quality
            matched = [opt for opt in ["320 kbps (Best)", "256 kbps (High)", "192 kbps (Standard)", "128 kbps"] if curr in opt]
            self.quality_option.set(matched[0] if matched else "320 kbps (Best)")
        else:
            self.quality_label.configure(text="Default Video Quality:")
            self.quality_option.configure(values=["Best (Auto)", "1080p (FHD)", "720p (HD)", "480p (SD)", "360p"])
            curr = config_manager.config.video_quality
            matched = [opt for opt in ["Best (Auto)", "1080p (FHD)", "720p (HD)", "480p (SD)", "360p"] if curr in opt.lower()]
            self.quality_option.set(matched[0] if matched else "Best (Auto)")

    def _run_signin(self):
        self.signin_btn.configure(state="disabled", text="Opening Browser...")
        self.account_status_lbl.configure(text="Complete sign-in in your browser...", text_color=Theme.TEXT_MUTED)

        def _on_done(success: bool, msg: str):
            self.after(0, lambda: self._on_signin_done(success, msg))

        auth_service.launch_google_signin(_on_done)

    def _on_signin_done(self, success: bool, msg: str):
        self.signin_btn.configure(state="normal", text="🌐 Sign in with Google")
        status_key, label, details = auth_service.get_connection_status()
        if success:
            self.account_status_lbl.configure(
                text=f"{label}  —  {msg}",
                text_color=Theme.SUCCESS,
            )
        else:
            self.account_status_lbl.configure(
                text=f"⚠️ Google Sign-In Failed: {msg}",
                text_color=Theme.WARNING,
            )

    def _run_signout(self):
        auth_service.disconnect()
        status_key, label, details = auth_service.get_connection_status()
        self.account_status_lbl.configure(text=f"{label}  —  {details}", text_color=Theme.TEXT_MUTED)

    def _on_check_updates_clicked(self):
        self.check_updates_btn.configure(state="disabled", text="Checking...")
        self.updater_status_lbl.configure(text="Checking for latest release...", text_color=Theme.TEXT_MUTED)

        def _on_done(result):
            def update():
                if not self.winfo_exists():
                    return
                self.check_updates_btn.configure(state="normal", text="Check for Updates")
                if result.status == "available":
                    v = result.latest_release.version if result.latest_release else ""
                    self.updater_status_lbl.configure(
                        text=f"New version v{v} is available!",
                        text_color=Theme.SUCCESS,
                    )
                    self.install_update_btn.pack(side="left", padx=10)
                elif result.status == "up_to_date":
                    self.updater_status_lbl.configure(
                        text=f"You're up to date. Vyntra v{__version__} is the latest version.",
                        text_color=Theme.TEXT_PRIMARY,
                    )
                    self.install_update_btn.pack_forget()
                elif result.status == "auth_required":
                    self.updater_status_lbl.configure(
                        text=result.error_message or "GitHub access token required to check private repository releases.",
                        text_color=Theme.WARNING,
                    )
                    self.install_update_btn.pack_forget()
                elif result.status == "no_asset":
                    self.updater_status_lbl.configure(
                        text=result.error_message or "New release found, but no compatible package for this OS.",
                        text_color=Theme.WARNING,
                    )
                    self.install_update_btn.pack_forget()
                elif result.status == "error":
                    self.updater_status_lbl.configure(
                        text=f"Update check error: {result.error_message}",
                        text_color=Theme.ERROR,
                    )
                    self.install_update_btn.pack_forget()
                else:
                    self.updater_status_lbl.configure(
                        text="You're running the current version of Vyntra.",
                        text_color=Theme.TEXT_MUTED,
                    )
                    self.install_update_btn.pack_forget()
            if self.winfo_exists():
                self.after(0, lambda: update() if self.winfo_exists() else None)

        update_manager.check_for_updates(callback=_on_done, background=False)

    def _on_open_update_modal_clicked(self):
        if update_manager.last_result and update_manager.last_result.has_update:
            UpdateModal(self, check_result=update_manager.last_result)

    def _build_action_buttons(self):
        """Save and Close buttons."""
        actions_frame = ctk.CTkFrame(self, fg_color="transparent")
        actions_frame.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 16))

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

    def _save_settings(self):
        dir_val = self.dir_entry.get().strip() or str(Path.home() / "Downloads" / "Vyntra")
        fmt_val = self.fmt_segmented.get()
        q_str = self.quality_option.get()

        update_kwargs = {
            "download_directory": dir_val,
            "default_format": fmt_val,
            "max_search_results": int(self.limit_option.get()),
        }

        if fmt_val == MediaFormat.MP3.value:
            bitrate_val = "320"
            if "192" in q_str:
                bitrate_val = "192"
            elif "256" in q_str:
                bitrate_val = "256"
            elif "128" in q_str:
                bitrate_val = "128"
            update_kwargs["audio_quality"] = bitrate_val
        else:
            v_val = "best"
            for res in ["1080p", "720p", "480p", "360p"]:
                if res in q_str.lower():
                    v_val = res
                    break
        if hasattr(self, "donation_prompt_var"):
            update_kwargs["donation_prompt_dismissed"] = not bool(self.donation_prompt_var.get())

        config_manager.update(**update_kwargs)

        if self.on_saved:
            self.on_saved()

        self.destroy()

    def destroy(self):
        try:
            for aid in self.tk.splitlist(self.tk.eval("after info")):
                try:
                    self.tk.eval(f"after cancel {aid}")
                except Exception:
                    pass
        except Exception:
            pass
        try:
            super().destroy()
        except Exception:
            pass
