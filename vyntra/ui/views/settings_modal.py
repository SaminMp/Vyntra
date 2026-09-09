"""
Settings and preferences modal dialog with YouTube Authentication configuration.
"""

from pathlib import Path
import threading
from tkinter import filedialog
from typing import Callable, Optional
import customtkinter as ctk

from vyntra.config import config_manager
from vyntra.models import AudioQuality, MediaFormat
from vyntra.services.auth_service import auth_service
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.ui.theme import Theme


class SettingsModal(ctk.CTkToplevel):
    """Configuration dialog for application preferences and in-app YouTube authentication."""

    def __init__(self, master, on_saved: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(master, **kwargs)

        self.on_saved = on_saved
        self.title("Vyntra Settings")
        self.geometry("600x620")
        self.minsize(560, 580)
        self.configure(fg_color=Theme.BG_MAIN)

        self.transient(master)
        self.grab_set()

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
        self._build_auth_settings()
        self._build_diagnostics_section()
        self._build_action_buttons()

    def _build_general_settings(self):
        """General download and search preferences."""
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

        # 3. Dynamic Quality Setting (Audio bitrate or Video resolution)
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

    def _build_auth_settings(self):
        """Clean in-app YouTube account and Google authentication section."""
        row = self._next_row

        # Divider
        divider = ctk.CTkFrame(self.scroll_frame, height=1, fg_color=Theme.BORDER_CARD)
        divider.grid(row=row, column=0, columnspan=2, padx=16, pady=10, sticky="ew")
        row += 1

        # 1. Google Identity Header
        auth_header = ctk.CTkLabel(
            self.scroll_frame,
            text="🔐 Google Account (Identity)",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_ACCENT,
        )
        auth_header.grid(row=row, column=0, columnspan=2, padx=16, pady=(12, 2), sticky="w")
        row += 1

        auth_sub = ctk.CTkLabel(
            self.scroll_frame,
            text="Connect your Google account for YouTube Data API, playlists, and account metadata.",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
        )
        auth_sub.grid(row=row, column=0, columnspan=2, padx=16, pady=(0, 6), sticky="w")
        row += 1

        # Google Account Status Box
        auth_box = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_MAIN, corner_radius=Theme.RADIUS_BUTTON)
        auth_box.grid(row=row, column=0, columnspan=2, padx=16, pady=(2, 10), sticky="ew")
        auth_box.grid_columnconfigure(0, weight=1)

        status_key, label, msg = auth_service.get_connection_status()
        status_color = Theme.SUCCESS if status_key == "connected" else Theme.TEXT_MUTED

        self.auth_status_lbl = ctk.CTkLabel(
            auth_box,
            text=f"{label}  —  {msg}",
            font=Theme.FONT_CAPTION,
            text_color=status_color,
            wraplength=480,
            justify="left",
        )
        self.auth_status_lbl.pack(padx=14, pady=(10, 8), anchor="w")

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

        # 2. YouTube Media Access Header
        media_header = ctk.CTkLabel(
            self.scroll_frame,
            text="🎬 YouTube Media Access (Playback & Downloads)",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_ACCENT,
        )
        media_header.grid(row=row, column=0, columnspan=2, padx=16, pady=(12, 2), sticky="w")
        row += 1

        media_sub = ctk.CTkLabel(
            self.scroll_frame,
            text="Used by the player and downloader when YouTube enforces bot-verification or account-restricted streams.",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            wraplength=480,
            justify="left",
        )
        media_sub.grid(row=row, column=0, columnspan=2, padx=16, pady=(0, 6), sticky="w")
        row += 1

        # Media Access Configuration Box
        media_box = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_MAIN, corner_radius=Theme.RADIUS_BUTTON)
        media_box.grid(row=row, column=0, columnspan=2, padx=16, pady=(2, 12), sticky="ew")
        media_box.grid_columnconfigure(1, weight=1)

        # Status row
        _, media_label, media_detail = auth_service.get_media_access_status()
        self.media_status_lbl = ctk.CTkLabel(
            media_box,
            text=f"{media_label}  —  {media_detail}",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            wraplength=480,
            justify="left",
        )
        self.media_status_lbl.pack(padx=14, pady=(10, 6), anchor="w")

        # Browser Selection Row
        sel_row = ctk.CTkFrame(media_box, fg_color="transparent")
        sel_row.pack(fill="x", padx=14, pady=(2, 6))

        sel_lbl = ctk.CTkLabel(
            sel_row,
            text="Session Provider:",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MAIN,
        )
        sel_lbl.pack(side="left", padx=(0, 10))

        browser_options = [
            "Guest (No Session)",
            "Firefox Session",
            "Chrome Session",
            "Edge Session",
            "Brave Session",
            "Custom Cookie File",
        ]
        curr_mode = getattr(config_manager.config, "youtube_media_auth_mode", "none")
        curr_browser = getattr(config_manager.config, "youtube_media_browser", "firefox").lower()

        default_sel = "Guest (No Session)"
        if curr_mode == "browser":
            for opt in browser_options:
                if curr_browser in opt.lower():
                    default_sel = opt
                    break
        elif curr_mode == "cookie_file":
            default_sel = "Custom Cookie File"

        self.media_browser_option = ctk.CTkOptionMenu(
            sel_row,
            values=browser_options,
            font=Theme.FONT_BODY,
            height=30,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            button_color=Theme.PRIMARY,
            button_hover_color=Theme.PRIMARY_HOVER,
            command=self._on_media_provider_changed,
        )
        self.media_browser_option.set(default_sel)
        self.media_browser_option.pack(side="left")

        # Cookie File Path row (shown if Custom Cookie File selected)
        self.cookie_file_frame = ctk.CTkFrame(media_box, fg_color="transparent")
        cookie_lbl = ctk.CTkLabel(self.cookie_file_frame, text="Cookie File:", font=Theme.FONT_CAPTION, text_color=Theme.TEXT_MUTED)
        cookie_lbl.pack(side="left", padx=(0, 8))
        self.cookie_entry = ctk.CTkEntry(self.cookie_file_frame, font=Theme.FONT_CAPTION, height=28, width=260)
        curr_cookie_path = getattr(config_manager.config, "youtube_media_custom_cookie_path", "")
        self.cookie_entry.insert(0, curr_cookie_path)
        self.cookie_entry.pack(side="left", padx=(0, 6))
        cookie_browse_btn = ctk.CTkButton(
            self.cookie_file_frame,
            text="Browse...",
            font=Theme.FONT_CAPTION,
            height=28,
            width=65,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._browse_cookie_file,
        )
        cookie_browse_btn.pack(side="left")

        if default_sel == "Custom Cookie File":
            self.cookie_file_frame.pack(fill="x", padx=14, pady=(2, 6))

        # Privacy / Consent note
        self.consent_notice_lbl = ctk.CTkLabel(
            media_box,
            text="🔒 Vyntra will use your existing YouTube browser session in-memory to authenticate media requests. Your Google password is never collected or stored.",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            wraplength=470,
            justify="left",
        )
        self.consent_notice_lbl.pack(padx=14, pady=(2, 8), anchor="w")

        # Test Media Access Button row
        test_media_row = ctk.CTkFrame(media_box, fg_color="transparent")
        test_media_row.pack(fill="x", padx=14, pady=(0, 10))

        self.test_btn = ctk.CTkButton(
            test_media_row,
            text="🧪 Test Connection & Media Access",
            font=Theme.FONT_CAPTION,
            height=30,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._run_test,
        )
        self.test_btn.pack(side="left")

        row += 1
        self._next_row = row

    def _on_media_provider_changed(self, choice: str):
        if choice == "Custom Cookie File":
            self.cookie_file_frame.pack(fill="x", padx=14, pady=(2, 6))
        else:
            self.cookie_file_frame.pack_forget()

    def _browse_cookie_file(self):
        chosen = filedialog.askopenfilename(
            title="Select Cookie File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if chosen:
            self.cookie_entry.delete(0, "end")
            self.cookie_entry.insert(0, chosen)

    def _build_diagnostics_section(self):
        """System diagnostics section."""
        row = self._next_row

        ffmpeg_box = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_MAIN, corner_radius=Theme.RADIUS_BUTTON)
        ffmpeg_box.grid(row=row, column=0, columnspan=2, padx=16, pady=(6, 12), sticky="ew")
        ffmpeg_box.grid_columnconfigure(0, weight=1)

        status = ffmpeg_service.get_status()
        status_text = f"✓ FFmpeg: Detected ({status.ffmpeg_path})" if status.is_available else "⚠️ FFmpeg: Not Found"
        status_color = Theme.SUCCESS if status.is_available else Theme.WARNING

        ffmpeg_info = ctk.CTkLabel(
            ffmpeg_box,
            text=status_text,
            font=Theme.FONT_CAPTION,
            text_color=status_color,
            justify="left",
            wraplength=480,
        )
        ffmpeg_info.pack(padx=12, pady=8, anchor="w")

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

    def _browse_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.dir_entry.get())
        if chosen:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, chosen)

    def _run_signin(self):
        self.signin_btn.configure(state="disabled", text="Opening Browser...")
        self.auth_status_lbl.configure(text="Complete sign-in in your browser...", text_color=Theme.TEXT_MUTED)

        def _on_done(success: bool, msg: str):
            self.after(0, lambda: self._on_signin_done(success, msg))

        auth_service.launch_google_signin(_on_done)

    def _on_signin_done(self, success: bool, msg: str):
        self.signin_btn.configure(state="normal", text="🌐 Sign in with Google")
        status_key, label, details = auth_service.get_connection_status()
        self.auth_status_lbl.configure(
            text=f"{label}  —  {msg}",
            text_color=Theme.SUCCESS if success else Theme.TEXT_MUTED,
        )

    def _run_signout(self):
        auth_service.disconnect()
        status_key, label, details = auth_service.get_connection_status()
        self.auth_status_lbl.configure(text=f"{label}  —  {details}", text_color=Theme.TEXT_MUTED)

    def _run_test(self):
        self.test_btn.configure(state="disabled", text="Testing...")
        self.media_status_lbl.configure(text="Testing YouTube media extraction...", text_color=Theme.TEXT_MUTED)

        # Apply current selection to config temporarily for test
        browser_choice = self.media_browser_option.get()
        if "Firefox" in browser_choice:
            config_manager.update(youtube_media_auth_mode="browser", youtube_media_browser="firefox")
        elif "Chrome" in browser_choice:
            config_manager.update(youtube_media_auth_mode="browser", youtube_media_browser="chrome")
        elif "Edge" in browser_choice:
            config_manager.update(youtube_media_auth_mode="browser", youtube_media_browser="edge")
        elif "Brave" in browser_choice:
            config_manager.update(youtube_media_auth_mode="browser", youtube_media_browser="brave")
        elif "Cookie File" in browser_choice:
            cookie_path = self.cookie_entry.get().strip()
            config_manager.update(youtube_media_auth_mode="cookie_file", youtube_media_custom_cookie_path=cookie_path)
        else:
            config_manager.update(youtube_media_auth_mode="none")

        def _worker():
            success, msg = auth_service.test_connection()
            self.after(0, lambda: self._on_test_done(success, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_test_done(self, success: bool, msg: str):
        self.test_btn.configure(state="normal", text="🧪 Test Connection & Media Access")
        _, media_label, _ = auth_service.get_media_access_status()
        self.media_status_lbl.configure(
            text=f"{media_label}  —  {msg.splitlines()[-1]}",
            text_color=Theme.SUCCESS if success else Theme.WARNING,
        )
        status_key, label, _ = auth_service.get_connection_status()
        self.auth_status_lbl.configure(
            text=f"{label}  —  {msg.splitlines()[0]}",
            text_color=Theme.SUCCESS if status_key == "connected" else Theme.TEXT_MUTED,
        )

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

    def _save_settings(self):
        dir_val = self.dir_entry.get().strip() or str(Path.home() / "Downloads" / "Vyntra")
        fmt_val = self.fmt_segmented.get()
        q_str = self.quality_option.get()

        update_kwargs = {
            "download_directory": dir_val,
            "default_format": fmt_val,
            "max_search_results": int(self.limit_option.get()),
        }

        # Media auth mode & browser selection
        browser_choice = self.media_browser_option.get()
        if "Firefox" in browser_choice:
            update_kwargs["youtube_media_auth_mode"] = "browser"
            update_kwargs["youtube_media_browser"] = "firefox"
        elif "Chrome" in browser_choice:
            update_kwargs["youtube_media_auth_mode"] = "browser"
            update_kwargs["youtube_media_browser"] = "chrome"
        elif "Edge" in browser_choice:
            update_kwargs["youtube_media_auth_mode"] = "browser"
            update_kwargs["youtube_media_browser"] = "edge"
        elif "Brave" in browser_choice:
            update_kwargs["youtube_media_auth_mode"] = "browser"
            update_kwargs["youtube_media_browser"] = "brave"
        elif "Cookie File" in browser_choice:
            update_kwargs["youtube_media_auth_mode"] = "cookie_file"
            update_kwargs["youtube_media_custom_cookie_path"] = self.cookie_entry.get().strip()
        else:
            update_kwargs["youtube_media_auth_mode"] = "none"

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
            update_kwargs["video_quality"] = v_val

        config_manager.update(**update_kwargs)

        if self.on_saved:
            self.on_saved()

        self.destroy()
