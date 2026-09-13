"""
Main Application Window and Layout Orchestrator for Vyntra.
Supports multi-platform media browsing and downloading across YouTube, Instagram, TikTok, and Spotify.
"""

from __future__ import annotations

from pathlib import Path
import logging
import os
import platform
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import customtkinter as ctk

from vyntra import __app_name__, __version__
from vyntra.config import config_manager
from vyntra.models import AudioQuality, DownloadStatus, DownloadTask, MediaFormat, MediaItem, ProgressInfo, SearchResult
from vyntra.services.auth_service import auth_service
from vyntra.services.download_service import download_service
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.services.stream_service import stream_server, stream_service
from vyntra.services.watch_later_service import watch_later_service
from vyntra.ui.components.footer_terminal import FooterTerminal
from vyntra.ui.components.platform_selector import PlatformSelector
from vyntra.ui.components.status_banner import StatusBanner
from vyntra.ui.pages import BasePlatformPage, InstagramPage, SpotifyPage, TikTokPage, YouTubePage
from vyntra.ui.theme import Theme
from vyntra.ui.views.account_modal import AccountModal
from vyntra.ui.views.donation_modal import DonationModal
from vyntra.ui.views.player_modal import VideoPlayerModal
from vyntra.ui.views.settings_modal import SettingsModal
from vyntra.ui.views.setup_wizard import SetupWizard
from vyntra.ui.views.update_modal import UpdateModal
from vyntra.ui.views.watch_later_view import WatchLaterView
from vyntra.updater.manager import update_manager
from vyntra.updater.models import UpdateCheckResult
from vyntra.utils.logger import logger


class _TerminalLogBridge(logging.Handler):
    """Bridges selected logging events into Vyntra's interactive footer terminal."""

    def __init__(self, terminal: FooterTerminal):
        super().__init__()
        self.terminal = terminal

    def emit(self, record):
        try:
            if not self.terminal or not hasattr(self.terminal, "winfo_exists"):
                return
            if not self.terminal.winfo_exists():
                return
            msg = record.getMessage()
            lvl = record.levelname.lower()
            # Filter internal high-frequency or noisy background probes
            skip_patterns = (
                "Probing formats",
                "Authentication method",
                "Player client",
                "PO Token provider",
                "Loaded user configuration",
                "Loaded from keyring",
                "Loaded default config",
            )
            if any(pattern in msg for pattern in skip_patterns):
                return
            if hasattr(self.terminal, "after") and self.terminal.winfo_exists():
                self.terminal.after(0, lambda m=msg, l=lvl: self._safe_log(m, l))
        except Exception:
            pass

    def _safe_log(self, msg, lvl):
        try:
            if self.terminal and hasattr(self.terminal, "winfo_exists") and self.terminal.winfo_exists():
                self.terminal.log(msg, level=lvl)
        except Exception:
            pass


class VyntraApp(ctk.CTk):
    """Main desktop application window for Vyntra multi-platform media downloader."""

    def __init__(self):
        super().__init__()

        # Lifecycle Tracking
        self._tracked_after_ids = set()
        self._is_disposed = False

        # Window Setup
        self._current_platform = "youtube"
        self.title(f"{__app_name__} v{__version__} - YouTube Media Downloader")
        self.geometry("980x800")
        self.minsize(740, 520)
        self.configure(fg_color=Theme.BG_MAIN)
        self._apply_window_icon()

        self._active_task_id: Optional[str] = None
        self._player_modal: Optional[VideoPlayerModal] = None
        self._donation_modal: Optional[DonationModal] = None
        self._donation_shown_this_session: bool = False
        self._is_watch_later_active: bool = False

        # Layout Configuration: row 2 (pages) expands; header, nav, and terminal stay fixed
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Build UI Sections in dedicated, isolated rows
        self._create_header()
        self._create_platform_navigation()
        self._create_platform_pages()
        self._create_footer_terminal()
        self._create_watch_later_view()

        # Connect logging bridge so operational messages write to the terminal
        self._log_bridge = _TerminalLogBridge(self.footer_terminal)
        logger.addHandler(self._log_bridge)

        # Handle window close cleanup
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)

        # Subscribe to authentication changes so header badge updates immediately
        self._auth_listener = lambda: self._safe_after(0, self._update_auth_badge)
        auth_service.add_auth_listener(self._auth_listener)

        # Check FFmpeg on launch and show subtle log in terminal
        self._check_initial_ffmpeg_status()

        # Background update check on launch
        self._pending_update: Optional[UpdateCheckResult] = None
        self._update_listener = lambda res: self._safe_after(0, lambda r=res: self._handle_update_result(r))
        update_manager.add_listener(self._update_listener)
        self._update_check_after_id = self._safe_after(1000, lambda: update_manager.check_for_updates(background=True))

        # First run: Show Setup Wizard if not completed
        if not config_manager.config.setup_completed:
            self._setup_wizard_after_id = self._safe_after(250, self._open_setup_wizard)
        elif not config_manager.config.donation_prompt_dismissed:
            self._donation_prompt_after_id = self._safe_after(3000, lambda: self._maybe_prompt_donation(trigger="launch"))

    def _safe_after(self, delay_ms: int, callback: Callable) -> Optional[str]:
        """Schedules a callback via after() while tracking ID for cancellation and verifying alive state."""
        if self._is_disposed:
            return None
        try:
            aid = None
            def _wrapper(*args, **kwargs):
                if self._is_disposed:
                    return
                try:
                    if aid in self._tracked_after_ids:
                        self._tracked_after_ids.remove(aid)
                except Exception:
                    pass
                try:
                    if self.winfo_exists():
                        callback(*args, **kwargs)
                except Exception:
                    pass

            aid = self.after(delay_ms, _wrapper)
            self._tracked_after_ids.add(aid)
            return aid
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Backward Compatibility Properties for Existing Code & Tests
    # -------------------------------------------------------------------------
    @property
    def youtube_page(self) -> YouTubePage:
        return self._pages["youtube"]

    @property
    def search_bar(self):
        return self.youtube_page.search_bar

    @property
    def results_list(self):
        return self.youtube_page.results_list

    @property
    def download_panel(self):
        return self.youtube_page.download_panel

    def _apply_window_icon(self):
        """Sets the application window icon across Windows (.ico) and macOS/Linux (.png iconphoto)."""
        root_candidates = []
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            root_candidates.append(Path(sys._MEIPASS) / "assets")
        root_candidates.append(Path(__file__).resolve().parent.parent.parent / "assets")
        root_candidates.append(Path.cwd() / "assets")

        # 1. On Windows, try iconbitmap (.ico)
        if sys.platform == "win32":
            for base in root_candidates:
                ico_path = base / "icon.ico"
                if ico_path.is_file():
                    try:
                        self.iconbitmap(str(ico_path))
                        return
                    except Exception as e:
                        logger.debug("iconbitmap failed on %s: %s", ico_path, e)

        # 2. On macOS or as universal fallback, use iconphoto with PNG
        for base in root_candidates:
            png_path = base / "icon.png"
            if png_path.is_file():
                try:
                    from PIL import Image, ImageTk
                    pil_img = Image.open(png_path)
                    photo = ImageTk.PhotoImage(pil_img)
                    self.iconphoto(False, photo)
                    self._icon_photo_ref = photo  # Prevent GC
                    return
                except Exception as e:
                    logger.debug("iconphoto failed on %s: %s", png_path, e)

    def _create_header(self):
        """Top branding header with navigation controls and action badges."""
        header = ctk.CTkFrame(self, fg_color=Theme.BG_SIDEBAR, height=58, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=0)
        header.grid_columnconfigure(1, weight=1)  # Expandable spacer
        header.grid_columnconfigure(2, weight=0)

        # Brand Logo & Title
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=18, pady=10, sticky="w")

        brand_icon = ctk.CTkLabel(title_box, text="🎵", font=(Theme.FONT_FAMILY, 20))
        brand_icon.pack(side="left", padx=(0, 8))

        brand_name = ctk.CTkLabel(title_box, text=__app_name__, font=Theme.FONT_TITLE, text_color=Theme.TEXT_PRIMARY)
        brand_name.pack(side="left")

        version_badge = ctk.CTkLabel(
            title_box,
            text=f"v{__version__}",
            font=Theme.FONT_BADGE,
            text_color=Theme.TEXT_MUTED,
            fg_color=Theme.BG_CARD,
            corner_radius=Theme.RADIUS_BADGE,
            padx=6,
            pady=2,
        )
        version_badge.pack(side="left", padx=8)

        # Right Action Buttons (Account Badge, Watch Later, Downloads & Settings)
        actions_box = ctk.CTkFrame(header, fg_color="transparent")
        actions_box.grid(row=0, column=2, padx=16, pady=10, sticky="e")

        # Update Available Button (hidden by default until a newer version is discovered)
        self.update_badge_btn = ctk.CTkButton(
            actions_box,
            text="✨ Update Available",
            font=(Theme.FONT_FAMILY, 11, "bold"),
            height=30,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.SUCCESS,
            hover_color="#059669",
            text_color="#FFFFFF",
            command=self._open_update_modal,
        )
        self.update_badge_btn.pack(side="left", padx=(0, 8))
        self.update_badge_btn.pack_forget()

        # Account Status Badge Button
        self.account_btn = ctk.CTkButton(
            actions_box,
            text="○ YouTube: Guest",
            font=Theme.FONT_CAPTION,
            height=30,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_CARD,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._open_account_modal,
        )
        self.account_btn.pack(side="left", padx=(0, 8))
        self._update_auth_badge()

        # Watch Later library button
        self.watch_later_btn = ctk.CTkButton(
            actions_box,
            text=f"⭐ Watch Later ({watch_later_service.count()})",
            font=Theme.FONT_CAPTION,
            height=30,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_CARD,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._toggle_watch_later_view,
        )
        self.watch_later_btn.pack(side="left", padx=(0, 8))

        open_dir_btn = ctk.CTkButton(
            actions_box,
            text="📁 Downloads",
            font=Theme.FONT_CAPTION,
            width=96,
            height=30,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_CARD,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._open_downloads_folder,
        )
        self.support_btn = ctk.CTkButton(
            actions_box,
            text="💖 Support",
            font=Theme.FONT_CAPTION,
            width=84,
            height=30,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_CARD,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._open_donation_modal,
        )
        self.support_btn.pack(side="left", padx=(0, 8))

        settings_btn = ctk.CTkButton(
            actions_box,
            text="⚙️ Settings",
            font=Theme.FONT_CAPTION,
            width=88,
            height=30,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_CARD,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._open_settings,
        )
        settings_btn.pack(side="left")

    def _create_platform_navigation(self):
        """Builds prominent multi-platform selector navigation bar."""
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(10, 2))
        nav_frame.grid_columnconfigure(0, weight=1)

        self.platform_selector = PlatformSelector(
            nav_frame,
            current_platform=self._current_platform,
            on_platform_changed=self._switch_platform,
        )
        self.platform_selector.pack(fill="x")

    def _create_platform_pages(self):
        """Builds container hosting dedicated platform pages."""
        self.pages_container = ctk.CTkFrame(self, fg_color="transparent")
        self.pages_container.grid(row=2, column=0, sticky="nsew")
        self.pages_container.grid_columnconfigure(0, weight=1)
        self.pages_container.grid_rowconfigure(0, weight=1)

        self._pages: Dict[str, BasePlatformPage] = {}
        self._pages["youtube"] = YouTubePage(self.pages_container, app=self)
        self._pages["instagram"] = InstagramPage(self.pages_container, app=self)
        self._pages["tiktok"] = TikTokPage(self.pages_container, app=self)
        self._pages["spotify"] = SpotifyPage(self.pages_container, app=self)

        # Show initial page
        self._pages["youtube"].grid(row=0, column=0, sticky="nsew")
        self._pages["youtube"].activate()

    def _create_footer_terminal(self):
        """Builds modern compact terminal in footer for notifications and live status."""
        self.footer_terminal = FooterTerminal(self)
        self.footer_terminal.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 10))
        # Alias for backward-compatibility with status_banner calls
        self.status_banner = self.footer_terminal

    def _create_watch_later_view(self):
        """Initializes Watch Later view."""
        self.watch_later_view = WatchLaterView(
            self,
            on_watch=self._handle_play_video,
            on_download=self._handle_watch_later_download,
            on_back=self._show_search_view,
            on_count_changed=self._on_watch_later_count_changed,
        )

    def _switch_platform(self, platform_id: str):
        """Smoothly switches the active visible platform page without destroying state."""
        pid = platform_id.lower()
        if pid == self._current_platform:
            return

        if self._is_watch_later_active:
            self._show_search_view()

        # Hide current page
        old_page = self._pages.get(self._current_platform)
        if old_page:
            old_page.grid_remove()
            old_page.deactivate()

        # Show target page
        self._current_platform = pid
        new_page = self._pages.get(pid)
        if new_page:
            new_page.grid(row=0, column=0, sticky="nsew")
            new_page.activate()
            display_name = new_page.capabilities.display_name
            self.title(f"{__app_name__} v{__version__} - {display_name} Media Downloader")
            self.status_banner.show_info(f"Switched to {display_name}")

        if hasattr(self, "platform_selector") and self.platform_selector.get_selected_platform() != pid:
            self.platform_selector.set_platform(pid)

    def _check_initial_ffmpeg_status(self):
        """Checks if FFmpeg is available and displays guide if missing."""
        status = ffmpeg_service.get_status()
        if not status.is_available:
            self.status_banner.show_warning(
                message=f"FFmpeg not found. {status.install_guide}",
                action_text="Copy Command" if "brew" in status.install_guide or "winget" in status.install_guide else None,
                on_action=lambda: self._copy_to_clipboard(status.install_guide),
            )

    def _copy_to_clipboard(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.status_banner.show_info("Copied command to clipboard! Run it in your terminal.")

    def _handle_result_selected(self, result: SearchResult):
        """Updates download panel with newly selected search result."""
        self.youtube_page.download_panel.set_selected_result(result)

    def _handle_play_video(self, result: MediaItem):
        """Launches live full video/audio player modal using SynchronizedMediaPlayer."""
        if self._player_modal and self._player_modal.winfo_exists():
            self._player_modal.lift()
            self._player_modal.focus_force()
            self._player_modal.load_video(result)
        else:
            self._player_modal = VideoPlayerModal(
                master=self,
                result=result,
                on_close=self._on_player_closed,
            )

    def _on_player_closed(self):
        self._player_modal = None

    def _update_watch_later_badge(self):
        count = watch_later_service.count()
        self.watch_later_btn.configure(text=f"⭐ Watch Later ({count})")

    def _on_watch_later_count_changed(self, count: int):
        self.watch_later_btn.configure(text=f"⭐ Watch Later ({count})")

    def _toggle_watch_later_view(self):
        if self._is_watch_later_active:
            self._show_search_view()
        else:
            self._show_watch_later_view()

    def _show_watch_later_view(self):
        self._is_watch_later_active = True
        self.pages_container.grid_remove()
        self.watch_later_view.grid(row=2, column=0, sticky="nsew", padx=16, pady=4)
        self.watch_later_view.refresh()
        self.watch_later_btn.configure(fg_color=Theme.BG_CARD_SELECTED)

    def _show_search_view(self):
        self._is_watch_later_active = False
        self.watch_later_view.grid_remove()
        self.pages_container.grid(row=2, column=0, sticky="nsew")
        self.watch_later_btn.configure(fg_color=Theme.BG_CARD)

    def _handle_watch_later_download(self, result: MediaItem, media_format: MediaFormat):
        save_dir = config_manager.config.download_directory
        self._handle_start_download(result, media_format, "best", save_dir)

    def _on_app_close(self):
        """Terminates player modal, streams, server, and closes window."""
        try:
            if hasattr(self, "_update_listener"):
                update_manager.remove_listener(self._update_listener)
            if hasattr(self, "_log_bridge"):
                logger.removeHandler(self._log_bridge)
            if hasattr(self, "_auth_listener"):
                auth_service.remove_auth_listener(self._auth_listener)
            if self._player_modal and self._player_modal.winfo_exists():
                self._player_modal.close()
            stream_service.stop_playback()
            stream_server.stop()
        except Exception:
            pass
        self.destroy()

    def _handle_update_result(self, result: UpdateCheckResult):
        """Processes update check results on the UI thread."""
        if result.status == "available" and result.target_asset:
            self._pending_update = result
            version_str = result.latest_release.version if result.latest_release else ""
            self.update_badge_btn.configure(text=f"✨ Update v{version_str}")
            self.update_badge_btn.pack(side="left", padx=(0, 8), before=self.account_btn)

            # Log to footer terminal with actionable button
            self.footer_terminal.log(
                f"New version v{version_str} available! Click 'Update Now' to inspect release notes and install.",
                level="info",
                action_text="Update Now",
                on_action=self._open_update_modal,
            )

    def _open_update_modal(self):
        """Opens UpdateModal for pending release."""
        if self._pending_update and self._pending_update.has_update:
            UpdateModal(self, check_result=self._pending_update)

    def _open_donation_modal(self, force: bool = True):
        """Opens the USDT donation modal."""
        if self._donation_modal and self._donation_modal.winfo_exists():
            try:
                self._donation_modal.lift()
                self._donation_modal.focus_force()
            except Exception:
                pass
            return

        self._donation_modal = DonationModal(self)
        if force:
            self._donation_shown_this_session = True

    def _maybe_prompt_donation(self, trigger: str = "download"):
        """Prompts for donation if not dismissed and not yet shown this session."""
        if self._is_disposed:
            return
        if config_manager.config.donation_prompt_dismissed:
            return
        if self._donation_shown_this_session:
            return
        if self._donation_modal and self._donation_modal.winfo_exists():
            return

        self._donation_shown_this_session = True
        self._open_donation_modal(force=False)

    def _handle_start_download(
        self,
        result: MediaItem,
        media_format: MediaFormat,
        quality: str,
        save_dir: str,
    ):
        """Dispatches download job across any supported platform."""
        if save_dir and Path(save_dir).exists():
            if str(Path(save_dir).resolve()) != str(Path(config_manager.config.download_directory).resolve()):
                config_manager.update(download_directory=str(Path(save_dir).resolve()))

        audio_q_str = config_manager.config.audio_quality
        if media_format == MediaFormat.MP3 and quality:
            audio_q_str = quality

        audio_quality = AudioQuality.BEST
        if audio_q_str == "192":
            audio_quality = AudioQuality.STANDARD
        elif audio_q_str == "256":
            audio_quality = AudioQuality.HIGH

        task = DownloadTask(
            result=result,
            format=media_format,
            save_directory=save_dir,
            platform=getattr(result, "platform", "youtube"),
            audio_quality=audio_quality,
            selected_quality=quality or "best",
        )
        self._active_task_id = task.task_id

        # Update downloading state on matching page
        page = self._pages.get(task.platform)
        if page and hasattr(page, "set_downloading"):
            page.set_downloading(True)

        def _on_progress(prog: ProgressInfo):
            self.after(0, lambda: self._update_active_progress(task.platform, prog))

        def _on_complete(output_path: str):
            self.after(0, lambda: self._download_completed(task, output_path))

        def _on_error(err: Exception):
            self.after(0, lambda: self._download_failed(task, err))

        download_service.start_download(
            task=task,
            on_progress=_on_progress,
            on_complete=_on_complete,
            on_error=_on_error,
        )

    def _update_active_progress(self, platform_id: str, prog: ProgressInfo):
        page = self._pages.get(platform_id)
        if page and hasattr(page, "update_progress"):
            page.update_progress(prog)

    def _download_completed(self, task: DownloadTask, output_path: str):
        page = self._pages.get(task.platform)
        if page and hasattr(page, "set_downloading"):
            page.set_downloading(False)
        self._active_task_id = None
        file_name = Path(output_path).name

        self.status_banner.show_success(
            message=f"✓ Downloaded: {file_name}",
            action_text="Open Folder",
            on_action=lambda: self._open_file_location(output_path, fallback_dir=task.save_directory),
        )

        # Trigger polite donation prompt if appropriate
        self._safe_after(800, lambda: self._maybe_prompt_donation(trigger="download"))

    def _download_failed(self, task: DownloadTask, err: Exception):
        page = self._pages.get(task.platform)
        if page and hasattr(page, "set_downloading"):
            page.set_downloading(False)
        self._active_task_id = None
        err_msg = str(err)
        if "Settings" in err_msg or "bot" in err_msg.lower() or "verification" in err_msg.lower():
            self.status_banner.show_warning(
                message=err_msg,
                action_text="Open Settings",
                on_action=self._open_settings,
            )
        else:
            self.status_banner.show_error(f"Download error: {err_msg}")

    def _handle_cancel_download(self):
        if self._active_task_id:
            download_service.cancel_download(self._active_task_id)
            self._active_task_id = None
            page = self._pages.get(self._current_platform)
            if page and hasattr(page, "set_downloading"):
                page.set_downloading(False)
            self.status_banner.show_warning("Download was cancelled.")

    def _open_downloads_folder(self):
        folder = config_manager.config.download_directory
        Path(folder).mkdir(parents=True, exist_ok=True)
        self._open_in_file_manager(folder)

    def _open_file_location(self, file_path: str, fallback_dir: Optional[str] = None):
        target_path = Path(file_path).resolve()
        if target_path.is_file():
            target_dir = target_path.parent
        elif target_path.is_dir():
            target_dir = target_path
        elif fallback_dir and Path(fallback_dir).exists():
            target_dir = Path(fallback_dir).resolve()
        else:
            target_dir = Path(config_manager.config.download_directory).resolve()

        logger.info("[Notification] Open Folder target: %s", target_dir)
        self._open_in_file_manager(str(target_dir))

    def _open_in_file_manager(self, folder_path: str):
        folder = Path(folder_path).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        folder_str = str(folder)
        if platform.system() == "Darwin":
            subprocess.run(["open", folder_str])
        elif platform.system() == "Windows":
            os.startfile(folder_str)
        else:
            subprocess.run(["xdg-open", folder_str])

    def _open_settings(self):
        SettingsModal(self, on_saved=self._on_settings_saved)

    def _open_account_modal(self):
        AccountModal(self, on_changed=self._update_auth_badge)

    def _open_setup_wizard(self):
        SetupWizard(self, on_completed=self._on_setup_completed)

    def _on_setup_completed(self):
        self._update_auth_badge()
        self.youtube_page.download_panel.folder_entry.delete(0, "end")
        self.youtube_page.download_panel.folder_entry.insert(0, config_manager.config.download_directory)
        self.youtube_page.download_panel.format_segmented.set(config_manager.config.default_format)
        self.status_banner.show_success("Setup complete! Welcome to Vyntra.")

    def _update_auth_badge(self):
        status_key, label, _ = auth_service.get_connection_status()
        color = Theme.SUCCESS if status_key == "connected" else (Theme.WARNING if status_key == "expired" else Theme.TEXT_MUTED)
        self.account_btn.configure(text=label, text_color=color)

    def _on_settings_saved(self):
        # Refresh download directory in all active panels
        self.youtube_page.download_panel.folder_entry.delete(0, "end")
        self.youtube_page.download_panel.folder_entry.insert(0, config_manager.config.download_directory)
        self.youtube_page.download_panel.format_segmented.set(config_manager.config.default_format)
        self._update_auth_badge()
        self.status_banner.show_info("Preferences updated successfully.")

    def _handle_update_result(self, result: UpdateCheckResult):
        """Processes update check results emitted by update_manager."""
        self._pending_update = result
        if result.status == "available":
            v = result.latest_release.version if result.latest_release else ""
            self.update_badge_btn.configure(text=f"✨ Update v{v}")
            self.update_badge_btn.pack(side="left", padx=(0, 8))
            self.footer_terminal.log(f"[Updater] New version v{v} available", level="info")
        elif result.status == "auth_required":
            self.update_badge_btn.pack_forget()
            logger.debug("[Updater] Private release check unavailable: Update Access not configured.")
        elif result.status == "up_to_date":
            self.update_badge_btn.pack_forget()
            logger.debug("[Updater] Vyntra is running the latest version.")
        else:
            self.update_badge_btn.pack_forget()

    def _open_update_modal(self):
        """Opens the update modal when user clicks the header update badge."""
        if self._pending_update and self._pending_update.has_update:
            UpdateModal(self, check_result=self._pending_update)

    def dispose(self):
        """Clean disposal of all listeners, callbacks, pages, and bridge handlers."""
        if self._is_disposed:
            return
        self._is_disposed = True

        # 1. Unhook logging bridge from root logger
        if hasattr(self, "_log_bridge") and self._log_bridge:
            try:
                logger.removeHandler(self._log_bridge)
            except Exception:
                pass
            self._log_bridge = None

        # 2. Unhook authentication and update listeners
        if hasattr(self, "_auth_listener") and self._auth_listener:
            try:
                auth_service.remove_auth_listener(self._auth_listener)
            except Exception:
                pass
            self._auth_listener = None

        if hasattr(self, "_update_listener") and self._update_listener:
            try:
                update_manager.remove_listener(self._update_listener)
            except Exception:
                pass
            self._update_listener = None

        # 3. Cancel tracked after IDs
        for aid in list(getattr(self, "_tracked_after_ids", set())):
            try:
                self.after_cancel(aid)
            except Exception:
                pass
        self._tracked_after_ids.clear()

        # 4. Cancel all pending after timers in Tk interpreter for this widget
        try:
            pending = self.tk.splitlist(self.tk.eval("after info"))
            for aid in pending:
                try:
                    self.tk.eval(f"after cancel {aid}")
                except Exception:
                    pass
        except Exception:
            pass

        # 5. Deactivate and dispose all pages
        for page in list(getattr(self, "_pages", {}).values()):
            try:
                if hasattr(page, "deactivate"):
                    page.deactivate()
            except Exception:
                pass

        # 6. Dispose player and donation modals if open
        if getattr(self, "_player_modal", None):
            try:
                self._player_modal.destroy()
            except Exception:
                pass
            self._player_modal = None

        if getattr(self, "_donation_modal", None):
            try:
                self._donation_modal.destroy()
            except Exception:
                pass
            self._donation_modal = None

        # 7. Clear CustomTkinter tracker references for this window
        try:
            from customtkinter.windows.widgets.appearance_mode import AppearanceModeTracker
            if self in AppearanceModeTracker.app_list:
                AppearanceModeTracker.app_list.remove(self)
        except Exception:
            pass

        try:
            from customtkinter.windows.widgets.scaling import ScalingTracker
            ScalingTracker.remove_window(None, self)
            if self in ScalingTracker.window_widgets_dict:
                del ScalingTracker.window_widgets_dict[self]
            if self in ScalingTracker.window_dpi_scaling_dict:
                del ScalingTracker.window_dpi_scaling_dict[self]
        except Exception:
            pass

    def destroy(self):
        """Overrides Tk destroy to guarantee clean resource disposal."""
        try:
            self.dispose()
        except Exception:
            pass
        try:
            super().destroy()
        except Exception:
            pass

    def _on_app_close(self):
        """Clean shutdown of all platform pages, background tasks, and application."""
        self.destroy()

