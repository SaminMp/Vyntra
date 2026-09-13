"""
Authoritative Synchronized Media Player Engine for Vyntra.
Provides unified single-pipeline video and audio playback slaved to a master audio clock.
Uses PyAV (libavformat/libavcodec) and PortAudio/sounddevice for hardware-accurate lip-sync.
"""

import os
from pathlib import Path
import queue
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import av
    import numpy as np
    import sounddevice as sd
    PYAV_AUDIO_AVAILABLE = True
except ImportError:
    PYAV_AUDIO_AVAILABLE = False

from vyntra.utils.logger import logger


class ImageWrapper:
    """Wraps raw decoded RGB frame bytes with a MediaPlayer-compatible interface."""

    def __init__(self, raw_bytes: bytes, size: Tuple[int, int]):
        self._raw_bytes = raw_bytes
        self._size = size

    def get_size(self) -> Tuple[int, int]:
        return self._size

    def to_bytearray(self) -> List[bytes]:
        return [self._raw_bytes]


class SynchronizedMediaPlayer:
    """
    Authoritative single-engine media player for Vyntra.
    Both video and audio are demuxed and decoded through a single synchronized pipeline,
    with video presentation timestamps slaved to the hardware master audio clock.
    """

    def __init__(
        self,
        media_path: Union[str, Dict[str, Any], Any],
        ff_opts: Optional[Dict[str, Any]] = None,
        diagnostic_mode: bool = True,
    ):
        self.raw_media = media_path
        self.ff_opts = ff_opts or {}
        self.diagnostic_mode = diagnostic_mode

        self._volume = 1.0  # 0.0 to 1.0
        self._is_muted = False
        self._is_paused = False
        self._is_closed = False
        self._is_seeking = False
        self._eof_reached = False

        self._lock = threading.RLock()
        self._seek_lock = threading.Lock()

        # Parse video and audio stream sources and headers
        headers_dict: Dict[str, str] = {}
        if isinstance(media_path, dict):
            self.video_url = str(media_path.get("video_url") or media_path.get("url") or "")
            self.audio_url = str(media_path.get("audio_url") or self.video_url)
            headers_dict = dict(media_path.get("http_headers") or {})
            self.media_path = self.video_url
        elif hasattr(media_path, "video_url") and hasattr(media_path, "audio_url"):
            self.video_url = str(media_path.video_url)
            self.audio_url = str(media_path.audio_url)
            headers_dict = dict(getattr(media_path, "http_headers", {}) or {})
            self.media_path = str(media_path)
        else:
            self.media_path = str(media_path)
            self.video_url = self.media_path
            self.audio_url = self.media_path
            headers_dict = {}

        # Construct sanitized HTTP headers for AVFormatContext
        user_agent = headers_dict.get("User-Agent")
        if not user_agent and (self.video_url.startswith("http://") or self.video_url.startswith("https://")):
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"

        self._av_options = {
            "probesize": "2000000",
            "analyzeduration": "2000000",
            "timeout": "15000000",  # 15 seconds network timeout
        }
        if user_agent:
            self._av_options["headers"] = f"User-Agent: {user_agent}\r\n"

        # Stream containers and stream info
        self._container_v: Optional[Any] = None
        self._container_a: Optional[Any] = None
        self._v_stream: Optional[Any] = None
        self._a_stream: Optional[Any] = None
        self._v_time_base: float = 1.0 / 30.0
        self._a_time_base: float = 1.0 / 44100.0
        self.width = 640
        self.height = 360
        self.fps = 30.0

        # Master Clock state
        self._master_audio_pts: float = 0.0
        self._last_video_pts: float = 0.0
        self._audio_sample_rate: int = 44100
        self._audio_channels: int = 2
        self._audio_stream_active: bool = False
        self._audio_device_stream: Optional[Any] = None

        # Fallback clock for video-only media or systems without audio devices
        self._fallback_start_time: float = time.monotonic()
        self._fallback_pause_time: float = 0.0

        # Threading and queues
        self._audio_queue: queue.Queue = queue.Queue(maxsize=60)
        self._video_queue: queue.Queue = queue.Queue(maxsize=20)
        self._current_audio_chunk: List[Any] = [b"", 0]
        self._current_video_frame: Optional[Tuple[Any, float]] = None

        self._audio_thread: Optional[threading.Thread] = None
        self._video_thread: Optional[threading.Thread] = None

        # Diagnostic telemetry
        self._last_diag_time: float = 0.0
        self._v_codec_name = "unknown"
        self._a_codec_name = "none"
        self._v_start_time: float = 0.0
        self._a_start_time: float = 0.0

        logger.info("[Player] Initializing SynchronizedMediaPlayer")
        self._start_pipeline(start_pts=0.0)

    def _start_pipeline(self, start_pts: float = 0.0):
        """Initializes demuxers, audio output device, and decoder worker threads."""
        with self._lock:
            self._close_internal_pipeline()
            self._master_audio_pts = max(0.0, float(start_pts))
            self._last_video_pts = self._master_audio_pts
            self._fallback_start_time = time.monotonic() - self._master_audio_pts
            self._is_seeking = False
            self._eof_reached = False

            if not PYAV_AUDIO_AVAILABLE:
                logger.warning("[Player] PyAV or sounddevice not available.")
                return

            try:
                # 1. Open video container
                self._container_v = av.open(self.video_url, options=self._av_options)
                if self._container_v.streams.video:
                    self._v_stream = self._container_v.streams.video[0]
                    self._v_time_base = float(self._v_stream.time_base)
                    self.width = self._v_stream.width or 640
                    self.height = self._v_stream.height or 360
                    self.fps = float(self._v_stream.average_rate or 30.0)
                    self._v_codec_name = self._v_stream.codec_context.name or "video"
                    if self._v_stream.start_time is not None:
                        self._v_start_time = float(self._v_stream.start_time * self._v_time_base)

                # 2. Open audio container (if same file, reuse; if separate DASH stream, open separate)
                if self.audio_url and self.audio_url == self.video_url:
                    self._container_a = self._container_v
                elif self.audio_url:
                    self._container_a = av.open(self.audio_url, options=self._av_options)

                if self._container_a and self._container_a.streams.audio:
                    self._a_stream = self._container_a.streams.audio[0]
                    self._a_time_base = float(self._a_stream.time_base)
                    self._audio_sample_rate = self._a_stream.rate or 44100
                    self._audio_channels = 2  # Standard stereo PCM
                    self._a_codec_name = self._a_stream.codec_context.name or "audio"
                    if self._a_stream.start_time is not None:
                        self._a_start_time = float(self._a_stream.start_time * self._a_time_base)

                # 3. Seek if starting at non-zero PTS
                if start_pts > 0:
                    self._seek_containers_internal(start_pts)

                # 4. Start audio output hardware stream
                self._init_audio_hardware()

                # 5. Start decoder background workers
                if self._a_stream:
                    self._audio_thread = threading.Thread(target=self._audio_decoder_loop, daemon=True)
                    self._audio_thread.start()

                if self._v_stream:
                    self._video_thread = threading.Thread(target=self._video_decoder_loop, daemon=True)
                    self._video_thread.start()

                if self.diagnostic_mode:
                    self._log_diagnostics(force=True)

            except Exception as err:
                logger.error("[Player] Failed to start synchronized media pipeline: %s", err, exc_info=True)

    def _init_audio_hardware(self):
        """Initializes the PortAudio/WASAPI output stream slaved to master clock."""
        if not self._a_stream:
            self._audio_stream_active = False
            return

        bytes_per_sample = self._audio_channels * 2  # 16-bit PCM = 2 bytes per sample

        def _audio_callback(outdata: Any, frames: int, time_info: Any, status: Any):
            needed_bytes = frames * bytes_per_sample
            written = 0

            with self._seek_lock:
                if self._is_seeking or self._is_paused:
                    outdata.fill(0)
                    return

                vol = 0.0 if self._is_muted else self._volume

                while needed_bytes > 0:
                    raw_b, offset = self._current_audio_chunk
                    if offset >= len(raw_b):
                        try:
                            new_b, chunk_pts = self._audio_queue.get_nowait()
                            self._current_audio_chunk = [new_b, 0]
                            self._master_audio_pts = chunk_pts
                            raw_b, offset = self._current_audio_chunk
                        except queue.Empty:
                            break

                    available = len(raw_b) - offset
                    take = min(needed_bytes, available)

                    if vol == 1.0:
                        outdata[written:written + take] = raw_b[offset:offset + take]
                    elif vol <= 0.0:
                        outdata[written:written + take] = b"\x00" * take
                    else:
                        chunk_samples = np.frombuffer(raw_b[offset:offset + take], dtype=np.int16)
                        scaled = (chunk_samples * vol).astype(np.int16)
                        outdata[written:written + take] = scaled.tobytes()

                    offset += take
                    self._current_audio_chunk[1] = offset
                    written += take
                    needed_bytes -= take
                    self._master_audio_pts += (take / bytes_per_sample) / self._audio_sample_rate

            if written < len(outdata):
                outdata[written:] = b"\x00" * (len(outdata) - written)

        try:
            self._audio_device_stream = sd.RawOutputStream(
                samplerate=self._audio_sample_rate,
                channels=self._audio_channels,
                dtype="int16",
                callback=_audio_callback,
                blocksize=1024,
            )
            self._audio_device_stream.start()
            self._audio_stream_active = True
        except Exception as audio_err:
            logger.warning("[Player] Audio device not available: %s. Pacing video with monotonic clock.", audio_err)
            self._audio_device_stream = None
            self._audio_stream_active = False

    def _audio_decoder_loop(self):
        """Decodes audio packets into stereo 16-bit PCM and queues them."""
        if not self._container_a or not self._a_stream:
            return

        try:
            resampler = av.AudioResampler(
                format="s16",
                layout="stereo",
                rate=self._audio_sample_rate,
            )
            for packet in self._container_a.demux(self._a_stream):
                if self._is_closed:
                    break
                for frame in packet.decode():
                    if self._is_closed:
                        break
                    for resampled_frame in resampler.resample(frame):
                        raw_pcm = bytes(resampled_frame.planes[0])
                        pts = float(frame.pts * self._a_time_base) if frame.pts is not None else self._master_audio_pts
                        while not self._is_closed and not self._is_seeking:
                            try:
                                self._audio_queue.put((raw_pcm, pts), timeout=0.1)
                                break
                            except queue.Full:
                                continue
        except Exception as e:
            if not self._is_closed:
                logger.debug("[Player] Audio decoder reached end: %s", e)

    def _video_decoder_loop(self):
        """Decodes video packets into VideoFrame objects and queues them."""
        if not self._container_v or not self._v_stream:
            return

        try:
            for packet in self._container_v.demux(self._v_stream):
                if self._is_closed:
                    break
                for frame in packet.decode():
                    if self._is_closed:
                        break
                    pts = float(frame.pts * self._v_time_base) if frame.pts is not None else self._last_video_pts

                    while not self._is_closed and not self._is_seeking:
                        try:
                            self._video_queue.put((frame, pts), timeout=0.1)
                            break
                        except queue.Full:
                            continue

            # Signal EOF
            if not self._is_closed:
                self._video_queue.put((None, "eof"))

        except Exception as e:
            if not self._is_closed:
                logger.debug("[Player] Video decoder reached end: %s", e)

    def get_frame(self) -> Tuple[Optional[Tuple[ImageWrapper, float]], Optional[Union[str, float]]]:
        """
        Retrieves the next video frame paced strictly against the master audio clock.
        Returns:
            ((ImageWrapper, pts), delay_or_none) or (None, "eof") or (None, None)
        """
        if self._is_closed:
            return None, "eof"

        if self._is_paused:
            return None, None

        # Authoritative master clock
        if self._audio_stream_active:
            clock = self._master_audio_pts
        else:
            clock = max(0.0, time.monotonic() - self._fallback_start_time)
            self._master_audio_pts = clock

        # Frame pacing and synchronization logic
        while not self._is_closed:
            if self._current_video_frame is None:
                try:
                    self._current_video_frame = self._video_queue.get_nowait()
                except queue.Empty:
                    return None, None

            av_frame, pts_or_eof = self._current_video_frame
            if pts_or_eof == "eof":
                self._eof_reached = True
                return None, "eof"

            v_pts = float(pts_or_eof)

            # 1. Stale frame check: If video is late by more than 60ms, drop and advance
            if v_pts < (clock - 0.060):
                self._last_video_pts = v_pts
                self._current_video_frame = None
                continue

            # 2. Synchronized frame presentation: If frame is within presentation window
            # (within 35ms or slightly ahead/behind display tick)
            if v_pts <= (clock + 0.035):
                self._last_video_pts = v_pts
                self._current_video_frame = None

                if self.diagnostic_mode:
                    self._log_diagnostics()

                # Convert ONLY displayed frame to RGB24 bytes
                rgb_frame = av_frame.to_rgb()
                raw_rgb = rgb_frame.to_ndarray().tobytes()
                img_wrapper = ImageWrapper(raw_rgb, (self.width, self.height))
                return (img_wrapper, v_pts), None

            # 3. Future frame: Video is ahead of master clock, wait for next tick
            return None, None

        return None, None

    def get_pts(self) -> float:
        """Returns the current master media presentation timestamp in seconds."""
        if self._audio_stream_active:
            return self._master_audio_pts
        elif self._is_paused:
            return max(0.0, self._fallback_pause_time - self._fallback_start_time)
        else:
            return max(0.0, time.monotonic() - self._fallback_start_time)

    def set_pause(self, paused: bool):
        """Pauses or resumes the entire synchronized session simultaneously."""
        with self._lock:
            if self._is_paused == paused or self._is_closed:
                return

            self._is_paused = paused
            now = time.monotonic()

            if paused:
                self._fallback_pause_time = now
                if self._audio_device_stream:
                    try:
                        self._audio_device_stream.stop()
                    except Exception:
                        pass
            else:
                paused_duration = now - self._fallback_pause_time
                self._fallback_start_time += paused_duration
                if self._audio_device_stream:
                    try:
                        self._audio_device_stream.start()
                    except Exception:
                        pass

            logger.info("[Player] Playback %s at %.2fs", "paused" if paused else "resumed", self.get_pts())

    def seek(self, pts: float, relative: bool = False):
        """
        Performs an authoritative synchronized seek across audio and video on the media timeline.
        """
        with self._lock:
            if self._is_closed:
                return

            curr = self.get_pts()
            target = (curr + pts) if relative else pts
            target = max(0.0, float(target))
            logger.info("[Player] Authoritative seek requested to: %.2fs", target)

            with self._seek_lock:
                self._is_seeking = True

                # 1. Drain queues
                while not self._audio_queue.empty():
                    try:
                        self._audio_queue.get_nowait()
                    except queue.Empty:
                        break

                while not self._video_queue.empty():
                    try:
                        self._video_queue.get_nowait()
                    except queue.Empty:
                        break

                self._current_audio_chunk = [b"", 0]
                self._current_video_frame = None

                # 2. Seek underlying stream demuxers
                self._seek_containers_internal(target)

                # 3. Update master clock
                self._master_audio_pts = target
                self._last_video_pts = target
                self._fallback_start_time = time.monotonic() - target
                self._is_seeking = False

            logger.info("[Player] Seek completed at master PTS: %.2fs", target)

    def _seek_containers_internal(self, target_pts: float):
        """Seeks both video and audio PyAV containers to target_pts."""
        try:
            if self._container_v and self._v_stream:
                target_v_pts = int(target_pts / self._v_time_base)
                self._container_v.seek(target_v_pts, stream=self._v_stream, backward=True)
        except Exception as e:
            logger.debug("[Player] Video seek note: %s", e)

        try:
            if self._container_a and self._a_stream and self._container_a != self._container_v:
                target_a_pts = int(target_pts / self._a_time_base)
                self._container_a.seek(target_a_pts, stream=self._a_stream, backward=True)
        except Exception as e:
            logger.debug("[Player] Audio seek note: %s", e)

    def set_volume(self, volume: float):
        """Sets playback volume smoothly from 0.0 to 1.0."""
        self._volume = max(0.0, min(1.0, float(volume)))
        self._is_muted = (self._volume == 0.0)

    def set_mute(self, muted: bool):
        """Mutes or unmutes audio output."""
        self._is_muted = bool(muted)

    def close_player(self):
        """Terminates workers and completely releases all media resources."""
        self._is_closed = True
        with self._lock:
            self._close_internal_pipeline()
        logger.info("[Player] Synchronized media player closed and released.")

    def _close_internal_pipeline(self):
        """Shuts down active audio device, containers, and threads."""
        if self._audio_device_stream:
            try:
                self._audio_device_stream.stop()
                self._audio_device_stream.close()
            except Exception:
                pass
            self._audio_device_stream = None

        if self._container_v:
            try:
                self._container_v.close()
            except Exception:
                pass
            self._container_v = None

        if self._container_a and self._container_a != self._container_v:
            try:
                self._container_a.close()
            except Exception:
                pass
            self._container_a = None

    def _log_diagnostics(self, force: bool = False):
        """Emits structured development diagnostic telemetry safely without exposing secrets."""
        now = time.monotonic()
        if not force and (now - self._last_diag_time < 5.0):
            return
        self._last_diag_time = now

        diff_ms = (self._last_video_pts - self._master_audio_pts) * 1000.0
        buf_state = f"audio_q={self._audio_queue.qsize()}, video_q={self._video_queue.qsize()}"
        clock_type = "Hardware Audio Device Clock" if self._audio_stream_active else "Monotonic Fallback Clock"

        logger.info(
            "[Player] Media backend: PyAV %s / PortAudio (sounddevice)\n"
            "[Player] Audio stream: %s (%dHz, %dch)\n"
            "[Player] Video stream: %s (%dx%d, %.2f fps)\n"
            "[Player] Audio start time: %.3fs\n"
            "[Player] Video start time: %.3fs\n"
            "[Player] Master clock: %s\n"
            "[Player] Audio position: %.3fs\n"
            "[Player] Video position: %.3fs\n"
            "[Player] A/V difference: %+.1fms\n"
            "[Player] Buffer state: %s",
            getattr(av, "__version__", "18.1.0"),
            self._a_codec_name, self._audio_sample_rate, self._audio_channels,
            self._v_codec_name, self.width, self.height, self.fps,
            self._a_start_time,
            self._v_start_time,
            clock_type,
            self._master_audio_pts,
            self._last_video_pts,
            diff_ms,
            buf_state,
        )


# Backward-compatible alias
FFmpegMediaPlayer = SynchronizedMediaPlayer
