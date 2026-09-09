"""
Dedicated Full Video Player Dialog for Vyntra.

Runs in the existing application instance using CTkToplevel and ffpyplayer,
providing complete video and audio playback with hardware acceleration.
"""

from pathlib import Path
import threading
import time
from typing import Callable, Optional
import customtkinter as ctk
from PIL import Image

try:
    from ffpyplayer.player import MediaPlayer
except ImportError:
    MediaPlayer = None

if MediaPlayer is None:
    from vyntra.services.media_player import FFmpegMediaPlayer as MediaPlayer

from vyntra.models import SearchResult
from vyntra.services.stream_service import stream_server, stream_service, stream_state
from vyntra.ui.theme import Theme
from vyntra.utils.formatters import format_duration
from vyntra.utils.logger import logger


class VideoPlayerModal(ctk.CTkToplevel):
    """Integrated media player window for complete video & audio playback inside Vyntra."""

    def __init__(self, master, result: SearchResult, on_close: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(master, **kwargs)

        self.on_close = on_close
        self.result = result
        self._is_closed = False
        self._player: Optional[MediaPlayer] = None
        self._is_paused = False
        self._is_muted = False
        self._previous_volume = 1.0
        self._duration = result.duration_seconds or 0
        self._is_seeking = False
        self._is_fullscreen = False
        self._is_render_loop_running = False

        self.title(f"Vyntra Player - {result.display_title}")
        self.geometry("960x640")
        self.minsize(640, 480)
        self.configure(fg_color="#000000")

        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.close)

        # Keyboard shortcuts
        self.bind("<space>", lambda e: self._toggle_play_pause())
        self.bind("<Left>", lambda e: self._seek_relative(-5.0))
        self.bind("<Right>", lambda e: self._seek_relative(5.0))
        self.bind("<Up>", lambda e: self._change_volume(0.1))
        self.bind("<Down>", lambda e: self._change_volume(-0.1))
        self.bind("m", lambda e: self._toggle_mute())
        self.bind("M", lambda e: self._toggle_mute())
        self.bind("f", lambda e: self._toggle_fullscreen())
        self.bind("F", lambda e: self._toggle_fullscreen())
        self.bind("<Escape>", lambda e: self._on_escape())

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_ui()
        self.load_video(result)

    def _build_ui(self):
        # 1. Top Header
        self.top_bar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=44, corner_radius=0)
        self.top_bar.grid(row=0, column=0, sticky="ew")
        self.top_bar.grid_columnconfigure(1, weight=1)

        badge = ctk.CTkLabel(
            self.top_bar,
            text="🎬 Vyntra Player",
            font=Theme.FONT_BADGE,
            text_color=Theme.PRIMARY,
        )
        badge.grid(row=0, column=0, padx=(14, 10), pady=8, sticky="w")

        self.title_label = ctk.CTkLabel(
            self.top_bar,
            text=self.result.display_title,
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_PRIMARY,
            anchor="w",
        )
        self.title_label.grid(row=0, column=1, padx=4, sticky="ew")

        close_btn = ctk.CTkButton(
            self.top_bar,
            text="✕",
            font=Theme.FONT_BODY_BOLD,
            width=36,
            height=28,
            corner_radius=6,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.ERROR,
            command=self.close,
        )
        close_btn.grid(row=0, column=2, padx=12, sticky="e")

        # 2. Center Video Viewport Area
        self.video_container = ctk.CTkFrame(self, fg_color="#000000", corner_radius=0)
        self.video_container.grid(row=1, column=0, sticky="nsew")
        self.video_container.grid_columnconfigure(0, weight=1)
        self.video_container.grid_rowconfigure(0, weight=1)

        self.video_label = ctk.CTkLabel(self.video_container, text="", fg_color="#000000")
        self.video_label.grid(row=0, column=0, sticky="nsew")
        self.video_label.bind("<Button-1>", lambda e: self._toggle_play_pause())
        self.video_label.bind("<Double-Button-1>", lambda e: self._toggle_fullscreen())

        self.loading_label = ctk.CTkLabel(
            self.video_container,
            text="Loading video...",
            font=Theme.FONT_HEADER,
            text_color=Theme.TEXT_MUTED,
        )
        self.loading_label.grid(row=0, column=0)

        # 3. Bottom Controls Bar
        self.bottom_bar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=0)
        self.bottom_bar.grid(row=2, column=0, sticky="ew")
        self.bottom_bar.grid_columnconfigure(0, weight=1)

        # Progress / Seek Slider Row
        slider_frame = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        slider_frame.pack(fill="x", padx=16, pady=(8, 2))
        slider_frame.grid_columnconfigure(0, weight=1)

        self.seek_slider = ctk.CTkSlider(
            slider_frame,
            from_=0.0,
            to=max(1.0, float(self._duration)),
            progress_color=Theme.PRIMARY,
            button_color=Theme.PRIMARY,
            button_hover_color=Theme.PRIMARY_HOVER,
            fg_color=Theme.BG_MUTED,
            height=14,
            command=self._on_seek_drag,
        )
        self.seek_slider.set(0.0)
        self.seek_slider.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.seek_slider.bind("<ButtonRelease-1>", self._on_seek_release)

        self.time_label = ctk.CTkLabel(
            slider_frame,
            text=f"00:00 / {format_duration(self._duration)}",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_SECONDARY,
        )
        self.time_label.grid(row=0, column=1, sticky="e")

        # Buttons Row
        ctrl_row = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=16, pady=(2, 10))

        # Left Controls: Play/Pause, Rewind, Forward, Stop
        self.play_btn = ctk.CTkButton(
            ctrl_row,
            text="⏸ Pause",
            font=Theme.FONT_BODY_BOLD,
            width=80,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._toggle_play_pause,
        )
        self.play_btn.pack(side="left", padx=(0, 8))

        rewind_btn = ctk.CTkButton(
            ctrl_row,
            text="⏪ -10s",
            font=Theme.FONT_CAPTION,
            width=58,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=lambda: self._seek_relative(-10.0),
        )
        rewind_btn.pack(side="left", padx=(0, 6))

        forward_btn = ctk.CTkButton(
            ctrl_row,
            text="+10s ⏩",
            font=Theme.FONT_CAPTION,
            width=58,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=lambda: self._seek_relative(10.0),
        )
        forward_btn.pack(side="left", padx=(0, 12))

        stop_btn = ctk.CTkButton(
            ctrl_row,
            text="⏹ Stop",
            font=Theme.FONT_CAPTION,
            width=54,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.ERROR,
            command=self.close,
        )
        stop_btn.pack(side="left")

        # Right Controls: Fullscreen, Volume Mute, Volume Slider
        fs_btn = ctk.CTkButton(
            ctrl_row,
            text="⛶ Fullscreen",
            font=Theme.FONT_CAPTION,
            width=84,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._toggle_fullscreen,
        )
        fs_btn.pack(side="right")

        self.vol_slider = ctk.CTkSlider(
            ctrl_row,
            from_=0.0,
            to=1.0,
            number_of_steps=20,
            width=90,
            height=14,
            progress_color=Theme.PRIMARY,
            button_color=Theme.PRIMARY,
            fg_color=Theme.BG_MUTED,
            command=self._on_volume_changed,
        )
        self.vol_slider.set(1.0)
        self.vol_slider.pack(side="right", padx=(6, 12))

        self.mute_btn = ctk.CTkButton(
            ctrl_row,
            text="🔊",
            font=Theme.FONT_BODY,
            width=36,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._toggle_mute,
        )
        self.mute_btn.pack(side="right", padx=(0, 4))

    def load_video(self, result: SearchResult):
        """Loads and begins playing a new video cleanly."""
        self.result = result
        self._duration = result.duration_seconds or 0
        self._has_logged_playback_started = False
        self.title_label.configure(text=result.display_title)
        self.title(f"Vyntra Player - {result.display_title}")

        self.seek_slider.configure(to=max(1.0, float(self._duration)))
        self.seek_slider.set(0.0)
        self.time_label.configure(text=f"00:00 / {format_duration(self._duration)}")

        self.loading_label.configure(text="Loading video...", text_color=Theme.TEXT_MUTED)
        self.loading_label.lift()

        logger.info("[Player] Starting playback for %s", result.video_id)
        logger.info("[Player] Extracting playable stream...")

        # Stop previous player if any
        self._stop_current_player()

        def _on_ready(file_path: str, duration: int):
            if not self._is_closed:
                logger.info("[Player] Stream extraction completed")
                logger.info("[Player] Stream URL obtained")
                self.after(0, lambda: self._start_playback(file_path, duration))

        def _on_error(err: Exception):
            if not self._is_closed:
                sanitized_err = str(err)
                logger.error("[Player] Stream extraction failed: %s", sanitized_err)
                self.after(0, lambda: self.loading_label.configure(
                    text="Unable to play this video.", text_color=Theme.ERROR
                ))

        stream_service.prepare_video_for_playback(
            result=result,
            on_ready=_on_ready,
            on_error=_on_error,
        )

    def _start_playback(self, media_path: str, duration: int):
        if self._is_closed:
            return
        if not MediaPlayer:
            logger.error("[Player] Media player backend unavailable")
            self.loading_label.configure(text="Unable to play this video.", text_color=Theme.ERROR)
            return

        logger.info("[Player] Initializing media player")
        self._duration = duration or self._duration
        self.seek_slider.configure(to=max(1.0, float(self._duration)))

        ff_opts = {
            "sync": "audio",
            "autoexit": True,
            "paused": False,
        }

        try:
            self._player = MediaPlayer(media_path, ff_opts=ff_opts)
            self._player.set_volume(self.vol_slider.get())
            self._is_paused = False
            self.play_btn.configure(text="⏸ Pause")
            logger.info("MediaPlayer initialized for media: %s", media_path)

            # Start the render loop
            self._is_render_loop_running = True
            self.after(30, self._render_loop)

        except Exception as e:
            logger.error("[Player] Failed to initialize MediaPlayer: %s", e)
            self.loading_label.configure(text="Unable to play this video.", text_color=Theme.ERROR)

    def _ensure_render_loop_running(self):
        """Ensures the rendering loop is active if it had stopped on EOF or pause."""
        if not self._is_render_loop_running and not self._is_closed and self._player is not None:
            self._is_render_loop_running = True
            self.after(10, self._render_loop)

    def _render_loop(self):
        """Continuously pulls decoded video frames and updates the UI."""
        if self._is_closed or self._player is None:
            self._is_render_loop_running = False
            return

        frame, val = self._player.get_frame()

        if frame:
            if not self._has_logged_playback_started:
                self._has_logged_playback_started = True
                logger.info("[Player] Playback started")
                self.loading_label.lower()

            img, pts = frame
            w, h = img.get_size()
            raw_bytes = bytes(img.to_bytearray()[0])

            # Calculate scaled dimensions maintaining aspect ratio
            container_w = max(320, self.video_container.winfo_width())
            container_h = max(240, self.video_container.winfo_height())

            scale = min(container_w / w, container_h / h)
            target_w = max(10, int(w * scale))
            target_h = max(10, int(h * scale))

            pil_img = Image.frombytes("RGB", (w, h), raw_bytes)
            if target_w != w or target_h != h:
                pil_img = pil_img.resize((target_w, target_h), Image.Resampling.BILINEAR)

            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(target_w, target_h))
            self.video_label.configure(image=ctk_img)

            # Update seek position
            if not self._is_seeking and pts is not None:
                self.seek_slider.set(float(pts))
                self.time_label.configure(text=f"{format_duration(int(pts))} / {format_duration(self._duration)}")

        if val == "eof":
            logger.info("[Player] Reached end of video stream.")
            self.play_btn.configure(text="▶ Play")
            self._is_paused = True
            self._is_render_loop_running = False
            return

        # Schedule next frame read (~60 fps polling)
        self._is_render_loop_running = True
        self.after(16, self._render_loop)

    def _toggle_play_pause(self):
        if not self._player:
            return
        self._is_paused = not self._is_paused
        self._player.set_pause(self._is_paused)
        self.play_btn.configure(text="▶ Play" if self._is_paused else "⏸ Pause")
        if not self._is_paused:
            self._ensure_render_loop_running()

    def _seek_relative(self, delta_secs: float):
        if not self._player:
            return
        try:
            curr = self._player.get_pts() or 0.0
            new_pos = max(0.0, min(float(self._duration), curr + delta_secs))
            logger.info("[Player] Skip %+.1fs requested (from %.2fs -> %.2fs)", delta_secs, curr, new_pos)
            self._player.seek(new_pos, relative=False)
            self.seek_slider.set(new_pos)
            self.time_label.configure(text=f"{format_duration(int(new_pos))} / {format_duration(self._duration)}")
            if self._is_paused:
                self._is_paused = False
                self.play_btn.configure(text="⏸ Pause")
                self._player.set_pause(False)
            self._ensure_render_loop_running()
        except Exception as e:
            import traceback
            logger.error("[Player] Seek relative failed:\n%s", traceback.format_exc())
            orig_title = self.result.display_title if self.result else "Vyntra Player"
            self.title_label.configure(text=f"{orig_title} (Unable to seek)")
            self.after(3000, lambda: self.title_label.configure(text=orig_title) if not self._is_closed else None)

    def _on_seek_drag(self, value):
        self._is_seeking = True
        self.time_label.configure(text=f"{format_duration(int(value))} / {format_duration(self._duration)}")

    def _on_seek_release(self, event):
        self._is_seeking = False
        if self._player:
            try:
                val = float(self.seek_slider.get())
                logger.info("[Player] Timeline seek released at %.2fs", val)
                self._player.seek(val, relative=False)
                if self._is_paused:
                    self._is_paused = False
                    self.play_btn.configure(text="⏸ Pause")
                    self._player.set_pause(False)
                self._ensure_render_loop_running()
            except Exception as e:
                import traceback
                logger.error("[Player] Seek release failed:\n%s", traceback.format_exc())
                orig_title = self.result.display_title if self.result else "Vyntra Player"
                self.title_label.configure(text=f"{orig_title} (Unable to seek to this position)")
                self.after(3000, lambda: self.title_label.configure(text=orig_title) if not self._is_closed else None)

    def _on_volume_changed(self, value: float):
        if self._player:
            self._player.set_volume(float(value))
        if value == 0.0:
            self.mute_btn.configure(text="🔇")
            self._is_muted = True
        else:
            self.mute_btn.configure(text="🔊")
            self._is_muted = False

    def _toggle_mute(self):
        if not self._is_muted:
            self._previous_volume = self.vol_slider.get() or 1.0
            self.vol_slider.set(0.0)
            self._on_volume_changed(0.0)
        else:
            restore_vol = self._previous_volume if self._previous_volume > 0.0 else 1.0
            self.vol_slider.set(restore_vol)
            self._on_volume_changed(restore_vol)

    def _toggle_fullscreen(self):
        self._is_fullscreen = not self._is_fullscreen
        self.attributes("-fullscreen", self._is_fullscreen)
        if self._is_fullscreen:
            self.top_bar.grid_remove()
        else:
            self.top_bar.grid()

    def _on_escape(self):
        if self._is_fullscreen:
            self._toggle_fullscreen()
        else:
            self.close()

    def _stop_current_player(self):
        """Stops active player instance."""
        if self._player:
            try:
                self._player.close_player()
            except Exception:
                pass
            self._player = None

    def close(self):
        """Closes player modal and frees resources cleanly."""
        if self._is_closed:
            return
        self._is_closed = True
        self._stop_current_player()
        stream_state.stop_active_ffmpeg()
        if self.on_close:
            self.on_close()
        self.destroy()
