"""
Main Application Window and Layout Orchestrator for Vyntra.
"""

import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import List, Optional
import customtkinter as ctk

from vyntra import __app_name__, __version__
from vyntra.config import config_manager
from vyntra.models import AudioQuality, DownloadStatus, DownloadTask, MediaFormat, ProgressInfo, SearchResult
from vyntra.services.auth_service import auth_service
from vyntra.services.download_service import download_service
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.services.search_service import search_service
from vyntra.services.stream_service import stream_server, stream_service
from vyntra.ui.components.download_panel import DownloadPanel
from vyntra.ui.components.results_list import ResultsList
from vyntra.ui.components.search_bar import SearchBar
from vyntra.ui.components.status_banner import StatusBanner
from vyntra.ui.theme import Theme
from vyntra.ui.views.account_modal import AccountModal
from vyntra.ui.views.player_modal import VideoPlayerModal
from vyntra.ui.views.settings_modal import SettingsModal
from vyntra.ui.views.setup_wizard import SetupWizard
from vyntra.utils.logger import logger


class VyntraApp(ctk.CTk):
    """Main desktop application window for Vyntra."""

    def __init__(self):
        super().__init__()

        # Window Setup
        self.title(f"{__app_name__} - YouTube Media Downloader")
        self.geometry("960x780")
        self.minsize(820, 600)
        self.configure(fg_color=Theme.BG_MAIN)

        self._active_task_id: Optional[str] = None
        self._current_search_query: str = ""
        self._player_modal: Optional[VideoPlayerModal] = None

        # Layout Configuration
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)  # Results list expands

        # Build UI Sections
        self._create_header()
        self._create_status_banner()
        self._create_search_section()
        self._create_results_section()
        self._create_download_section()

        # Handle window close cleanup
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)

        # Check FFmpeg on launch and show subtle banner if missing
        self._check_initial_ffmpeg_status()

        # First run: Show Setup Wizard if not completed
        if not config_manager.config.setup_completed:
            self.after(250, self._open_setup_wizard)

    def _create_header(self):
        """Top branding header with navigation controls and YouTube account status."""
        header = ctk.CTkFrame(self, fg_color=Theme.BG_SIDEBAR, height=58, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        # Brand Logo & Title
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=18, pady=10, sticky="w")

        brand_icon = ctk.CTkLabel(
            title_box,
            text="🎵",
            font=(Theme.FONT_FAMILY, 20),
        )
        brand_icon.pack(side="left", padx=(0, 8))

        brand_name = ctk.CTkLabel(
            title_box,
            text=__app_name__,
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_PRIMARY,
        )
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

        # Right Action Buttons (Account Badge, Downloads & Settings)
        actions_box = ctk.CTkFrame(header, fg_color="transparent")
        actions_box.grid(row=0, column=2, padx=18, pady=10, sticky="e")

        # YouTube Account Status Badge Button
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
        open_dir_btn.pack(side="left", padx=(0, 8))

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

    def _create_status_banner(self):
        """Notification banner placeholder."""
        self.status_banner = StatusBanner(self)
        self.status_banner.grid(row=1, column=0, sticky="ew", padx=16, pady=(6, 0))
        self.status_banner.grid_remove()

    def _create_search_section(self):
        """Search input container."""
        search_container = ctk.CTkFrame(self, fg_color="transparent")
        search_container.grid(row=2, column=0, sticky="ew", padx=16, pady=(12, 8))
        search_container.grid_columnconfigure(0, weight=1)

        self.search_bar = SearchBar(search_container, on_search=self._handle_search_query)
        self.search_bar.grid(row=0, column=0, sticky="ew")

    def _create_results_section(self):
        """Scrollable results container."""
        self.results_list = ResultsList(
            self,
            on_result_selected=self._handle_result_selected,
            on_preview=self._handle_play_video,
        )
        self.results_list.grid(row=3, column=0, sticky="nsew", padx=16, pady=4)

    def _create_download_section(self):
        """Bottom download controls panel."""
        self.download_panel = DownloadPanel(
            self,
            on_download=self._handle_start_download,
            on_cancel=self._handle_cancel_download,
        )
        self.download_panel.grid(row=4, column=0, sticky="ew", padx=16, pady=(8, 16))

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
        """Copies text to system clipboard."""
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.status_banner.show_info("Copied command to clipboard! Run it in your terminal.")

    def _handle_search_query(self, query: str):
        """Initiates YouTube search on worker thread."""
        # Stop any active video player when searching
        stream_service.stop_playback()

        self._current_search_query = query
        self.search_bar.set_loading(True)
        self.results_list.show_loading_state(query)

        def _on_success(results: List[SearchResult]):
            self.after(0, lambda: self._display_search_success(results))

        def _on_error(err: Exception):
            self.after(0, lambda: self._display_search_error(err))

        search_service.search_async(
            query=query,
            on_success=_on_success,
            on_error=_on_error,
        )

    def _display_search_success(self, results: List[SearchResult]):
        self.search_bar.set_loading(False)
        self.results_list.display_results(results)

    def _display_search_error(self, err: Exception):
        self.search_bar.set_loading(False)
        self.results_list.show_error_state(f"Error fetching results: {str(err)}")
        self.status_banner.show_error(f"Search failed: {str(err)}")

    def _handle_result_selected(self, result: SearchResult):
        """Updates download panel with newly selected search result."""
        self.download_panel.set_selected_result(result)

    def _handle_play_video(self, result: SearchResult):
        """Launches live full video and audio player for selected result inside current instance."""
        self.download_panel.set_selected_result(result)
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
        """Callback when the video player modal is closed."""
        self._player_modal = None

    def _on_app_close(self):
        """Terminates player modal, streams, server, and closes window."""
        try:
            if self._player_modal and self._player_modal.winfo_exists():
                self._player_modal.close()
            stream_service.stop_playback()
            stream_server.stop()
        except Exception:
            pass
        self.destroy()

    def _handle_start_download(
        self,
        result: SearchResult,
        media_format: MediaFormat,
        quality: str,
        save_dir: str,
    ):
        """Dispatches download job."""
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
            audio_quality=audio_quality,
            selected_quality=quality or "best",
        )
        self._active_task_id = task.task_id

        def _on_progress(prog: ProgressInfo):
            self.after(0, lambda: self.download_panel.update_progress(prog))

        def _on_complete(output_path: str):
            self.after(0, lambda: self._download_completed(task, output_path))

        def _on_error(err: Exception):
            self.after(0, lambda: self._download_failed(err))

        download_service.start_download(
            task=task,
            on_progress=_on_progress,
            on_complete=_on_complete,
            on_error=_on_error,
        )

    def _download_completed(self, task: DownloadTask, output_path: str):
        self.download_panel.set_downloading(False)
        self._active_task_id = None
        file_name = Path(output_path).name

        self.status_banner.show_success(
            message=f"✓ Downloaded: {file_name}",
            action_text="Open Folder",
            on_action=lambda: self._open_file_location(output_path),
        )

    def _download_failed(self, err: Exception):
        self.download_panel.set_downloading(False)
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
            self.download_panel.set_downloading(False)
            self.status_banner.show_warning("Download was cancelled.")

    def _open_downloads_folder(self):
        folder = config_manager.config.download_directory
        Path(folder).mkdir(parents=True, exist_ok=True)
        self._open_in_file_manager(folder)

    def _open_file_location(self, file_path: str):
        path = Path(file_path)
        if path.exists():
            if platform.system() == "Darwin":
                subprocess.run(["open", "-R", str(path)])
            elif platform.system() == "Windows":
                subprocess.run(["explorer", f"/select,{str(path)}"])
            else:
                self._open_in_file_manager(str(path.parent))
        else:
            self._open_downloads_folder()

    def _open_in_file_manager(self, folder_path: str):
        if platform.system() == "Darwin":
            subprocess.run(["open", folder_path])
        elif platform.system() == "Windows":
            os.startfile(folder_path)
        else:
            subprocess.run(["xdg-open", folder_path])

    def _open_settings(self):
        SettingsModal(self, on_saved=self._on_settings_saved)

    def _open_account_modal(self):
        AccountModal(self, on_changed=self._update_auth_badge)

    def _open_setup_wizard(self):
        SetupWizard(self, on_completed=self._on_setup_completed)

    def _on_setup_completed(self):
        self._update_auth_badge()
        self.download_panel.folder_entry.delete(0, "end")
        self.download_panel.folder_entry.insert(0, config_manager.config.download_directory)
        self.download_panel.format_segmented.set(config_manager.config.default_format)
        self.status_banner.show_success("Setup complete! Welcome to Vyntra.")

    def _update_auth_badge(self):
        status_key, label, _ = auth_service.get_connection_status()
        color = Theme.SUCCESS if status_key == "connected" else (Theme.WARNING if status_key == "expired" else Theme.TEXT_MUTED)
        self.account_btn.configure(text=label, text_color=color)

    def _on_settings_saved(self):
        # Refresh download directory in panel
        self.download_panel.folder_entry.delete(0, "end")
        self.download_panel.folder_entry.insert(0, config_manager.config.download_directory)
        self.download_panel.format_segmented.set(config_manager.config.default_format)
        self._update_auth_badge()
        self.status_banner.show_info("Preferences updated successfully.")
