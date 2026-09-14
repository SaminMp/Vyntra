"""
Dedicated Audio-Only Player Modal for Spotify and Music Tracks in Vyntra.

Designed strictly for audio-only playback:
- Large album artwork display
- Track title, artist, and album metadata
- Play / Pause / Resume / Stop controls
- Seeking slider with current time and total duration
- Volume slider and Mute button
- No video frame, no video quality controls, no MP4 elements
"""

import threading
import time
from typing import Callable, Optional
import customtkinter as ctk

from vyntra.models import MediaItem
from vyntra.services.audio_player import AudioPlayer
from vyntra.services.image_service import image_service
from vyntra.ui.theme import Theme
from vyntra.utils.formatters import format_duration
from vyntra.utils.logger import logger


class AudioPlayerModal(ctk.CTkToplevel):
    """
    Dedicated audio-only player modal dialog.
    Plays official previews or extracted audio streams cleanly without any video rendering.
    """

    def __init__(
        self,
        master,
        item: MediaItem,
        on_close: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)

        self.item = item
        self.on_close = on_close
        self._is_closed = False
        self._player: Optional[AudioPlayer] = None
        self._is_paused = False
        self._is_muted = False
        self._previous_volume = 1.0
        self._duration = item.duration_seconds or 30
        self._is_seeking = False
        self._is_poll_running = False

        self.title(f"Vyntra Audio Player — {item.display_title}")
        self.geometry("520x560")
        self.minsize(460, 500)
        self.configure(fg_color=Theme.BG_MAIN)

        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.close)

        # Keyboard shortcuts for audio control
        self.bind("<space>", lambda e: self._toggle_play_pause())
        self.bind("<Left>", lambda e: self._seek_relative(-5.0))
        self.bind("<Right>", lambda e: self._seek_relative(5.0))
        self.bind("<Up>", lambda e: self._change_volume(0.1))
        self.bind("<Down>", lambda e: self._change_volume(-0.1))
        self.bind("m", lambda e: self._toggle_mute())
        self.bind("M", lambda e: self._toggle_mute())
        self.bind("<Escape>", lambda e: self.close())

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_ui()
        self.load_audio(item)

    def _build_ui(self):
        # 1. Top Header Bar
        self.top_bar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=44, corner_radius=0)
        self.top_bar.grid(row=0, column=0, sticky="ew")
        self.top_bar.grid_columnconfigure(1, weight=1)

        platform_icon = "🟢" if getattr(self.item, "platform", "") == "spotify" else "🎵"
        badge = ctk.CTkLabel(
            self.top_bar,
            text=f"{platform_icon} Audio Player",
            font=Theme.FONT_BADGE,
            text_color=Theme.SUCCESS if platform_icon == "🟢" else Theme.PRIMARY,
        )
        badge.grid(row=0, column=0, padx=(14, 10), pady=8, sticky="w")

        header_title = ctk.CTkLabel(
            self.top_bar,
            text="Now Playing",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            anchor="w",
        )
        header_title.grid(row=0, column=1, padx=4, sticky="w")

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
        close_btn.grid(row=0, column=2, padx=12, pady=8, sticky="e")

        # 2. Main Content Center (Artwork + Metadata)
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.grid(row=1, column=0, sticky="nsew", padx=24, pady=16)
        content_frame.grid_columnconfigure(0, weight=1)

        # Artwork Card
        self.art_container = ctk.CTkFrame(
            content_frame,
            fg_color=Theme.BG_CARD,
            corner_radius=16,
            border_width=1,
            border_color=Theme.BORDER_CARD,
            width=220,
            height=220,
        )
        self.art_container.pack(pady=(10, 16))
        self.art_container.pack_propagate(False)

        self.art_label = ctk.CTkLabel(
            self.art_container,
            text="🎵",
            font=(Theme.FONT_FAMILY, 56),
            text_color=Theme.TEXT_MUTED,
        )
        self.art_label.place(relx=0.5, rely=0.5, anchor="center")

        # Track Title
        self.title_label = ctk.CTkLabel(
            content_frame,
            text=self.item.display_title,
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_PRIMARY,
            wraplength=440,
        )
        self.title_label.pack(pady=(4, 2))

        # Artist & Album
        artist_text = self.item.channel
        if getattr(self.item, "album", None):
            artist_text += f"  •  {self.item.album}"
        self.artist_label = ctk.CTkLabel(
            content_frame,
            text=artist_text,
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_SECONDARY,
            wraplength=440,
        )
        self.artist_label.pack(pady=(0, 8))

        # Status / Loading indicator
        self.status_label = ctk.CTkLabel(
            content_frame,
            text="Loading audio...",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
        )
        self.status_label.pack(pady=(0, 6))

        # 3. Playback Controls Bottom Bar
        controls_frame = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_CARD,
            corner_radius=12,
            border_width=1,
            border_color=Theme.BORDER_CARD,
        )
        controls_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        controls_frame.grid_columnconfigure(0, weight=1)

        # Row 1: Seek slider & Time display
        seek_row = ctk.CTkFrame(controls_frame, fg_color="transparent")
        seek_row.pack(fill="x", padx=16, pady=(12, 4))
        seek_row.grid_columnconfigure(1, weight=1)

        self.time_current_label = ctk.CTkLabel(
            seek_row,
            text="00:00",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            width=40,
            anchor="w",
        )
        self.time_current_label.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.seek_slider = ctk.CTkSlider(
            seek_row,
            from_=0.0,
            to=max(1.0, float(self._duration)),
            number_of_steps=1000,
            height=14,
            progress_color=Theme.SUCCESS if getattr(self.item, "platform", "") == "spotify" else Theme.PRIMARY,
            button_color=Theme.SUCCESS if getattr(self.item, "platform", "") == "spotify" else Theme.PRIMARY,
            fg_color=Theme.BG_MUTED,
            command=self._on_seek_drag,
        )
        self.seek_slider.set(0.0)
        self.seek_slider.grid(row=0, column=1, sticky="ew")
        self.seek_slider.bind("<ButtonRelease-1>", self._on_seek_commit)

        self.time_total_label = ctk.CTkLabel(
            seek_row,
            text=format_duration(self._duration),
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            width=40,
            anchor="e",
        )
        self.time_total_label.grid(row=0, column=2, padx=(8, 0), sticky="e")

        # Row 2: Play/Pause, Stop, Volume, Mute
        btn_row = ctk.CTkFrame(controls_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(4, 12))

        self.rewind_btn = ctk.CTkButton(
            btn_row,
            text="⏪ -5s",
            font=Theme.FONT_CAPTION,
            width=58,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=lambda: self._seek_relative(-5.0),
        )
        self.rewind_btn.pack(side="left", padx=(0, 6))

        play_accent = Theme.SUCCESS if getattr(self.item, "platform", "") == "spotify" else Theme.PRIMARY
        play_hover = "#059669" if getattr(self.item, "platform", "") == "spotify" else Theme.PRIMARY_HOVER
        self.play_btn = ctk.CTkButton(
            btn_row,
            text="▶ Play",
            font=Theme.FONT_BODY_BOLD,
            width=88,
            height=34,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=play_accent,
            hover_color=play_hover,
            command=self._toggle_play_pause,
        )
        self.play_btn.pack(side="left", padx=(0, 6))

        self.forward_btn = ctk.CTkButton(
            btn_row,
            text="+5s ⏩",
            font=Theme.FONT_CAPTION,
            width=58,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=lambda: self._seek_relative(5.0),
        )
        self.forward_btn.pack(side="left", padx=(0, 6))

        self.stop_btn = ctk.CTkButton(
            btn_row,
            text="⏹ Stop",
            font=Theme.FONT_CAPTION,
            width=54,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.ERROR,
            command=self.close,
        )
        self.stop_btn.pack(side="left")

        # Right side: Volume
        self.vol_slider = ctk.CTkSlider(
            btn_row,
            from_=0.0,
            to=1.0,
            number_of_steps=20,
            width=80,
            height=14,
            progress_color=play_accent,
            button_color=play_accent,
            fg_color=Theme.BG_MUTED,
            command=self._on_volume_changed,
        )
        self.vol_slider.set(1.0)
        self.vol_slider.pack(side="right", padx=(4, 0))

        self.mute_btn = ctk.CTkButton(
            btn_row,
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

    def load_audio(self, item: MediaItem):
        """Resolves audio stream via platform service and initializes playback."""
        self.item = item
        self._duration = item.duration_seconds or 30
        self.title_label.configure(text=item.display_title)
        artist_text = item.channel
        if getattr(item, "album", None):
            artist_text += f"  •  {item.album}"
        self.artist_label.configure(text=artist_text)
        self.time_total_label.configure(text=format_duration(self._duration))
        self.seek_slider.configure(to=max(1.0, float(self._duration)))
        self.seek_slider.set(0.0)
        self.status_label.configure(text="Resolving audio stream...", text_color=Theme.TEXT_MUTED)

        # Load artwork
        if item.thumbnail_url:
            def _on_art_loaded(img):
                if not self._is_closed and self.art_label.winfo_exists():
                    self.art_label.configure(image=img, text="")

            placeholder = image_service.get_thumbnail_async(
                url=item.thumbnail_url,
                size=(220, 220),
                on_success=lambda img: self.after(0, lambda: _on_art_loaded(img)),
            )
            self.art_label.configure(image=placeholder, text="")

        # Resolve audio stream on background thread
        def _resolver_worker():
            try:
                from vyntra.platforms.registry import platform_registry
                platform_svc = platform_registry.get(getattr(item, "platform", "spotify"))
                if not platform_svc:
                    from vyntra.platforms.spotify.service import spotify_platform
                    platform_svc = spotify_platform

                stream_info = platform_svc.prepare_playback_stream(item)
                audio_url = stream_info.get("url") if isinstance(stream_info, dict) else str(stream_info)
                if not audio_url:
                    raise RuntimeError("No audio URL resolved.")

                if not self._is_closed:
                    self.after(0, lambda: self._start_audio_playback(audio_url, stream_info))
            except Exception as e:
                logger.error("[AudioPlayer] Failed to resolve audio stream: %s", e)
                if not self._is_closed:
                    self.after(0, lambda: self.status_label.configure(
                        text=f"Failed to load audio: {e}",
                        text_color=Theme.ERROR,
                    ))

        threading.Thread(target=_resolver_worker, daemon=True).start()

    def _start_audio_playback(self, audio_url: str, stream_info: Any):
        """Initializes AudioPlayer with audio-only stream."""
        if self._is_closed:
            return

        self._stop_current_player()
        headers = stream_info.get("headers", {}) if isinstance(stream_info, dict) else {}

        # Construct pure audio media payload
        audio_payload = {
            "audio_url": audio_url,
            "http_headers": headers,
        }

        try:
            self._player = AudioPlayer(audio_payload, diagnostic_mode=True)
            self._player.set_volume(self.vol_slider.get())
            self._is_paused = False
            self.play_btn.configure(text="⏸ Pause")
            self.status_label.configure(text="Playing audio", text_color=Theme.SUCCESS)

            # Start time polling loop
            self._is_poll_running = True
            self.after(100, self._poll_time_loop)
        except Exception as err:
            logger.error("[AudioPlayer] Failed to start audio playback: %s", err)
            self.status_label.configure(text=f"Audio error: {err}", text_color=Theme.ERROR)

    def _poll_time_loop(self):
        """Updates progress bar and current time label based on master audio clock."""
        if self._is_closed or not self._is_poll_running:
            return

        if self._player:
            current_pts = self._player.get_pts()
            if not self._is_seeking:
                self.seek_slider.set(current_pts)
                self.time_current_label.configure(text=format_duration(current_pts))

            # Auto-stop on EOF
            if self._player.is_eof() and current_pts >= self._duration - 1.0:
                self._is_paused = True
                self.play_btn.configure(text="▶ Play")
                self.status_label.configure(text="Playback completed", text_color=Theme.TEXT_MUTED)
                return

        self.after(100, self._poll_time_loop)

    def _toggle_play_pause(self):
        if not self._player:
            return
        self._is_paused = not self._is_paused
        self._player.set_pause(self._is_paused)
        self.play_btn.configure(text="▶ Play" if self._is_paused else "⏸ Pause")
        self.status_label.configure(
            text="Paused" if self._is_paused else "Playing audio",
            text_color=Theme.TEXT_MUTED if self._is_paused else Theme.SUCCESS,
        )

    def _on_seek_drag(self, val: float):
        self._is_seeking = True
        self.time_current_label.configure(text=format_duration(val))

    def _on_seek_commit(self, event=None):
        if not self._player:
            self._is_seeking = False
            return
        target_pts = float(self.seek_slider.get())
        self._player.seek(target_pts)
        self._is_seeking = False

    def _seek_relative(self, delta_secs: float):
        if not self._player:
            return
        current = self._player.get_pts()
        target = max(0.0, min(float(self._duration), current + delta_secs))
        self.seek_slider.set(target)
        self.time_current_label.configure(text=format_duration(target))
        self._player.seek(target)

    def _on_volume_changed(self, val: float):
        if self._player:
            self._player.set_volume(val)
        if val > 0 and self._is_muted:
            self._is_muted = False
            self.mute_btn.configure(text="🔊")
        elif val == 0 and not self._is_muted:
            self._is_muted = True
            self.mute_btn.configure(text="🔇")

    def _toggle_mute(self):
        if not self._player:
            return
        if self._is_muted:
            self._is_muted = False
            self._player.set_volume(self._previous_volume)
            self.vol_slider.set(self._previous_volume)
            self.mute_btn.configure(text="🔊")
        else:
            self._is_muted = True
            self._previous_volume = self.vol_slider.get() or 1.0
            self._player.set_volume(0.0)
            self.vol_slider.set(0.0)
            self.mute_btn.configure(text="🔇")

    def _change_volume(self, delta: float):
        curr = self.vol_slider.get()
        new_vol = max(0.0, min(1.0, curr + delta))
        self.vol_slider.set(new_vol)
        self._on_volume_changed(new_vol)

    def _stop_current_player(self):
        self._is_poll_running = False
        if self._player:
            try:
                self._player.close()
            except Exception:
                pass
            self._player = None

    def close(self):
        """Stops audio pipeline and destroys the modal window cleanly."""
        if self._is_closed:
            return
        self._is_closed = True
        self._stop_current_player()
        if self.on_close:
            try:
                self.on_close()
            except Exception:
                pass
        self.destroy()
