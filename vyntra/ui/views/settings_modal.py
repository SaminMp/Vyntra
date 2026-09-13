"""
Settings and preferences modal dialog with YouTube Authentication configuration.
"""

from pathlib import Path
import platform
import threading
from tkinter import filedialog
from typing import Callable, Optional
import customtkinter as ctk

from vyntra import __version__
from vyntra.config import config_manager
from vyntra.models import AudioQuality, MediaFormat
from vyntra.services.auth_service import auth_service
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.ui.theme import Theme
from vyntra.ui.views.update_modal import UpdateModal
from vyntra.updater.manager import update_manager


class SettingsModal(ctk.CTkToplevel):
    """Configuration dialog for application preferences and in-app YouTube authentication."""

    def __init__(self, master, on_saved: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(master, **kwargs)

        self.on_saved = on_saved
        self.title(f"Vyntra Settings - v{__version__}")
        self.geometry("640x700")
        self.minsize(580, 560)
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
            text=f"⚙️ Preferences & Account  (v{__version__})",
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
        self._build_platform_settings()
        self._build_diagnostics_section()
        self._build_updates_section()
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

        browser_options = ["Guest (No Session)"]
        if platform.system() == "Darwin":
            browser_options.extend(["Safari Session", "Chrome Session", "Firefox Session", "Brave Session", "Edge Session"])
        else:
            browser_options.extend(["Firefox Session", "Chrome Session", "Edge Session", "Brave Session"])
        browser_options.append("Custom Cookie File")

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

        # Privacy / Consent note tailored per OS
        if platform.system() == "Windows":
            os_note = (
                "💡 Windows Note: Chrome 127+ & Edge use App-Bound Encryption preventing external cookie reading. "
                "Firefox Session or Custom Cookie File are recommended."
            )
        elif platform.system() == "Darwin":
            os_note = (
                "💡 Mac Note: Safari, Chrome, and Firefox authenticate via macOS Keychain. "
                "Grant Keychain or Full Disk Access if prompted by macOS."
            )
        else:
            os_note = "💡 Tip: Firefox Session or Custom Cookie File recommended for desktop sessions."

        self.consent_notice_lbl = ctk.CTkLabel(
            media_box,
            text=(
                f"🔒 Vyntra accesses your YouTube session in-memory only to authenticate media requests. Your password is never captured.\n"
                f"{os_note}"
            ),
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            wraplength=470,
            justify="left",
        )
        self.consent_notice_lbl.pack(padx=14, pady=(2, 8), anchor="w")

        # Test Media Access and Diagnostics Button row
        test_media_row = ctk.CTkFrame(media_box, fg_color="transparent")
        test_media_row.pack(fill="x", padx=14, pady=(0, 10))

        self.test_btn = ctk.CTkButton(
            test_media_row,
            text="🧪 Test Connection & Media",
            font=Theme.FONT_CAPTION,
            height=30,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._run_test,
        )
        self.test_btn.pack(side="left", padx=(0, 8))

        self.diag_btn = ctk.CTkButton(
            test_media_row,
            text="📋 Run Diagnostics",
            font=Theme.FONT_CAPTION,
            height=30,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._run_diagnostics,
        )
        self.diag_btn.pack(side="left")

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

    def _build_platform_settings(self):
        """Platform-specific settings for Instagram, TikTok, and Spotify."""
        row = self._next_row

        # Divider
        divider = ctk.CTkFrame(self.scroll_frame, height=1, fg_color=Theme.BORDER_CARD)
        divider.grid(row=row, column=0, columnspan=2, padx=16, pady=10, sticky="ew")
        row += 1

        # Platform Header
        plat_header = ctk.CTkLabel(
            self.scroll_frame,
            text="🌐 Multi-Platform Configuration",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_ACCENT,
        )
        plat_header.grid(row=row, column=0, columnspan=2, padx=16, pady=(12, 2), sticky="w")
        row += 1

        plat_sub = ctk.CTkLabel(
            self.scroll_frame,
            text="Configure optional credentials and session files for Instagram, TikTok, and Spotify.",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
        )
        plat_sub.grid(row=row, column=0, columnspan=2, padx=16, pady=(0, 6), sticky="w")
        row += 1

        # --- Spotify Box ---
        spotify_box = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_MAIN, corner_radius=Theme.RADIUS_BUTTON)
        spotify_box.grid(row=row, column=0, columnspan=2, padx=16, pady=(2, 8), sticky="ew")
        spotify_box.grid_columnconfigure(1, weight=1)

        sp_title = ctk.CTkLabel(
            spotify_box,
            text="🟢 Spotify Web API (Optional for Full Catalog Search)",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_PRIMARY,
        )
        sp_title.grid(row=0, column=0, columnspan=2, padx=14, pady=(8, 2), sticky="w")

        sp_desc = ctk.CTkLabel(
            spotify_box,
            text="Enables official Spotify catalog search. (Track URLs & 30s previews work without credentials).",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            justify="left",
        )
        sp_desc.grid(row=1, column=0, columnspan=2, padx=14, pady=(0, 6), sticky="w")

        id_lbl = ctk.CTkLabel(spotify_box, text="Client ID:", font=Theme.FONT_CAPTION, text_color=Theme.TEXT_SECONDARY)
        id_lbl.grid(row=2, column=0, padx=(14, 8), pady=3, sticky="w")
        self.spotify_id_entry = ctk.CTkEntry(spotify_box, font=Theme.FONT_CAPTION, height=28)
        self.spotify_id_entry.insert(0, getattr(config_manager.config, "spotify_client_id", ""))
        self.spotify_id_entry.grid(row=2, column=1, padx=(0, 14), pady=3, sticky="ew")

        sec_lbl = ctk.CTkLabel(spotify_box, text="Client Secret:", font=Theme.FONT_CAPTION, text_color=Theme.TEXT_SECONDARY)
        sec_lbl.grid(row=3, column=0, padx=(14, 8), pady=(3, 10), sticky="w")
        self.spotify_secret_entry = ctk.CTkEntry(spotify_box, font=Theme.FONT_CAPTION, height=28, show="*")
        self.spotify_secret_entry.insert(0, getattr(config_manager.config, "spotify_client_secret", ""))
        self.spotify_secret_entry.grid(row=3, column=1, padx=(0, 14), pady=(3, 10), sticky="ew")

        row += 1

        # --- Instagram & TikTok Box ---
        social_box = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_MAIN, corner_radius=Theme.RADIUS_BUTTON)
        social_box.grid(row=row, column=0, columnspan=2, padx=16, pady=(2, 10), sticky="ew")
        social_box.grid_columnconfigure(1, weight=1)

        soc_title = ctk.CTkLabel(
            social_box,
            text="📸 Instagram & 🎵 TikTok (Optional Session Cookies)",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_PRIMARY,
        )
        soc_title.grid(row=0, column=0, columnspan=3, padx=14, pady=(8, 2), sticky="w")

        soc_desc = ctk.CTkLabel(
            social_box,
            text="Provide Netscape-format cookie files to access age-restricted or private posts/reels.",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            justify="left",
        )
        soc_desc.grid(row=1, column=0, columnspan=3, padx=14, pady=(0, 6), sticky="w")

        # Instagram Cookie
        ig_lbl = ctk.CTkLabel(social_box, text="Instagram Cookies:", font=Theme.FONT_CAPTION, text_color=Theme.TEXT_SECONDARY)
        ig_lbl.grid(row=2, column=0, padx=(14, 8), pady=3, sticky="w")
        self.insta_cookie_entry = ctk.CTkEntry(social_box, font=Theme.FONT_CAPTION, height=28)
        self.insta_cookie_entry.insert(0, getattr(config_manager.config, "instagram_custom_cookie_path", ""))
        self.insta_cookie_entry.grid(row=2, column=1, padx=(0, 6), pady=3, sticky="ew")
        ig_browse_btn = ctk.CTkButton(
            social_box,
            text="Browse...",
            font=Theme.FONT_CAPTION,
            height=28,
            width=65,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._browse_insta_cookie,
        )
        ig_browse_btn.grid(row=2, column=2, padx=(0, 14), pady=3)

        # TikTok Cookie
        tt_lbl = ctk.CTkLabel(social_box, text="TikTok Cookies:", font=Theme.FONT_CAPTION, text_color=Theme.TEXT_SECONDARY)
        tt_lbl.grid(row=3, column=0, padx=(14, 8), pady=(3, 10), sticky="w")
        self.tiktok_cookie_entry = ctk.CTkEntry(social_box, font=Theme.FONT_CAPTION, height=28)
        self.tiktok_cookie_entry.insert(0, getattr(config_manager.config, "tiktok_custom_cookie_path", ""))
        self.tiktok_cookie_entry.grid(row=3, column=1, padx=(0, 6), pady=(3, 10), sticky="ew")
        tt_browse_btn = ctk.CTkButton(
            social_box,
            text="Browse...",
            font=Theme.FONT_CAPTION,
            height=28,
            width=65,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._browse_tiktok_cookie,
        )
        tt_browse_btn.grid(row=3, column=2, padx=(0, 14), pady=(3, 10))

        row += 1
        self._next_row = row

    def _browse_insta_cookie(self):
        chosen = filedialog.askopenfilename(
            title="Select Instagram Cookie File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if chosen:
            self.insta_cookie_entry.delete(0, "end")
            self.insta_cookie_entry.insert(0, chosen)

    def _browse_tiktok_cookie(self):
        chosen = filedialog.askopenfilename(
            title="Select TikTok Cookie File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if chosen:
            self.tiktok_cookie_entry.delete(0, "end")
            self.tiktok_cookie_entry.insert(0, chosen)

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
        self._next_row = row + 1

    def _build_updates_section(self):
        """Builds software updates and release channel section."""
        row = self._next_row
        sec_label = ctk.CTkLabel(
            self.scroll_frame,
            text="🚀 Application Updates & About",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_ACCENT,
        )
        sec_label.grid(row=row, column=0, columnspan=2, padx=16, pady=(16, 6), sticky="w")
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
            text="Automatic update checking is active on launch.",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
        )
        self.updater_status_lbl.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")

        btn_bar = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        btn_bar.grid(row=row + 1, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="ew")

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

        self._next_row = row + 2

    def _on_check_updates_clicked(self):
        self.check_updates_btn.configure(state="disabled", text="Checking...")
        self.updater_status_lbl.configure(text="Querying GitHub Releases API...", text_color=Theme.TEXT_MUTED)

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
                elif result.status == "no_asset":
                    self.updater_status_lbl.configure(
                        text=result.error_message or "New release found, but no compatible package for this OS.",
                        text_color=Theme.WARNING,
                    )
                    self.install_update_btn.pack_forget()
                else:
                    self.updater_status_lbl.configure(
                        text=f"Check failed: {result.error_message or 'Network error'}",
                        text_color=Theme.WARNING,
                    )
                    self.install_update_btn.pack_forget()
            self.after(0, update)

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
        if success:
            self.auth_status_lbl.configure(
                text=f"{label}  —  {msg}",
                text_color=Theme.SUCCESS,
            )
        else:
            self.auth_status_lbl.configure(
                text=f"⚠️ Google Sign-In Failed: {msg}",
                text_color=Theme.WARNING,
            )

    def _run_signout(self):
        auth_service.disconnect()
        status_key, label, details = auth_service.get_connection_status()
        self.auth_status_lbl.configure(text=f"{label}  —  {details}", text_color=Theme.TEXT_MUTED)

    def _run_test(self):
        self.test_btn.configure(state="disabled", text="Testing...")
        self.media_status_lbl.configure(text="Testing YouTube media extraction...", text_color=Theme.TEXT_MUTED)

    def _apply_media_settings_to_config(self):
        browser_choice = self.media_browser_option.get()
        if "Safari" in browser_choice:
            config_manager.update(youtube_media_auth_mode="browser", youtube_media_browser="safari")
        elif "Firefox" in browser_choice:
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

    def _run_test(self):
        self.test_btn.configure(state="disabled", text="Testing...")
        self.media_status_lbl.configure(text="Testing YouTube media extraction...", text_color=Theme.TEXT_MUTED)

        self._apply_media_settings_to_config()

        def _worker():
            success, msg = auth_service.test_connection()
            self.after(0, lambda: self._on_test_done(success, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_test_done(self, success: bool, msg: str):
        self.test_btn.configure(state="normal", text="🧪 Test Connection & Media")
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

    def _run_diagnostics(self):
        self._apply_media_settings_to_config()
        self.diag_btn.configure(state="disabled", text="Running Diagnostics...")

        def _worker():
            from vyntra.services.youtube_service import youtube_service
            report = youtube_service.diagnose_video("Obvg5jVCvxc")
            self.after(0, lambda: self._on_diagnostics_done(report))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_diagnostics_done(self, report: str):
        self.diag_btn.configure(state="normal", text="📋 Run Diagnostics")
        self._show_diagnostics_modal(report)

    def _show_diagnostics_modal(self, report: str):
        diag_win = ctk.CTkToplevel(self)
        diag_win.title("Vyntra YouTube Diagnostics")
        diag_win.geometry("580x540")
        diag_win.minsize(500, 400)
        diag_win.configure(fg_color=Theme.BG_MAIN)
        diag_win.transient(self)
        diag_win.grab_set()

        header = ctk.CTkLabel(
            diag_win,
            text="📋 Vyntra YouTube Diagnostics",
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
            corner_radius=Theme.RADIUS_BUTTON,
        )
        textbox.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        textbox.insert("1.0", report)
        textbox.configure(state="disabled")

        btn_bar = ctk.CTkFrame(diag_win, fg_color="transparent")
        btn_bar.pack(fill="x", padx=20, pady=(0, 16))

        def _copy():
            diag_win.clipboard_clear()
            diag_win.clipboard_append(report)
            copy_btn.configure(text="✓ Copied!")
            diag_win.after(2000, lambda: copy_btn.configure(text="📋 Copy to Clipboard"))

        copy_btn = ctk.CTkButton(
            btn_bar,
            text="📋 Copy to Clipboard",
            font=Theme.FONT_CAPTION,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=_copy,
        )
        copy_btn.pack(side="left")

        close_diag_btn = ctk.CTkButton(
            btn_bar,
            text="Close",
            font=Theme.FONT_CAPTION,
            height=32,
            width=80,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=diag_win.destroy,
        )
        close_diag_btn.pack(side="right")

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

        # Multi-platform settings
        update_kwargs["instagram_custom_cookie_path"] = self.insta_cookie_entry.get().strip()
        update_kwargs["tiktok_custom_cookie_path"] = self.tiktok_cookie_entry.get().strip()
        update_kwargs["spotify_client_id"] = self.spotify_id_entry.get().strip()
        update_kwargs["spotify_client_secret"] = self.spotify_secret_entry.get().strip()

        config_manager.update(**update_kwargs)

        if self.on_saved:
            self.on_saved()

        self.destroy()
