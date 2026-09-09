"""
Robust Native Media Player Engine for Vyntra using FFmpeg and FFplay.
Provides smooth video frame decoding and synchronized audio playback
without requiring external C-extensions (like ffpyplayer).
"""

import ctypes
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional, Tuple, Union

from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.utils.logger import logger


class ImageWrapper:
    """Wraps raw decoded RGB frame bytes with a MediaPlayer-compatible interface."""

    def __init__(self, raw_bytes: bytes, size: Tuple[int, int]):
        self._raw_bytes = raw_bytes
        self._size = size

    def get_size(self) -> Tuple[int, int]:
        return self._size

    def to_bytearray(self) -> list:
        return [self._raw_bytes]


class FFmpegMediaPlayer:
    """
    MediaPlayer-compatible video and audio playback engine.
    Uses FFmpeg for frame extraction and FFplay for synchronized audio.
    """

    def __init__(self, media_path: str, ff_opts: Optional[Dict[str, Any]] = None):
        self.media_path = str(media_path)
        self.ff_opts = ff_opts or {}
        self.width = 640
        self.height = 360
        self.fps = 30
        self.frame_size = self.width * self.height * 3  # rgb24

        self._volume = 1.0  # 0.0 to 1.0
        self._is_paused = False
        self._is_closed = False
        self._current_pts = 0.0
        self._start_mono_time = time.monotonic()
        self._pause_mono_time = 0.0
        self._generation = 0
        self._clock_started = False

        self._video_proc: Optional[subprocess.Popen] = None
        self._audio_proc: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._frame_queue: queue.Queue = queue.Queue(maxsize=15)
        self._lock = threading.RLock()

        # Locate binaries
        status = ffmpeg_service.get_status()
        self._ffmpeg_bin = status.ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"
        ffmpeg_parent = Path(self._ffmpeg_bin).parent if self._ffmpeg_bin else Path(".")
        ffplay_cand = ffmpeg_parent / ("ffplay.exe" if sys.platform == "win32" else "ffplay")
        self._ffplay_bin = str(ffplay_cand) if ffplay_cand.is_file() else (shutil.which("ffplay") or "ffplay")

        logger.info("[Player] Initializing FFmpegMediaPlayer for: %s", self.media_path)
        self._start_pipeline(start_pts=0.0)

    def _start_pipeline(self, start_pts: float = 0.0):
        """Starts or restarts the FFmpeg video reader and FFplay audio player from start_pts."""
        with self._lock:
            self._generation += 1
            current_gen = self._generation
            self._stop_procs_internal()
            self._current_pts = max(0.0, float(start_pts))
            self._clock_started = False
            self._start_mono_time = time.monotonic() - self._current_pts
            self._is_paused = False

            # Drain any old frames from queue
            while not self._frame_queue.empty():
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    break

            headers_str = self.ff_opts.get("headers")
            if not headers_str and (self.media_path.startswith("http://") or self.media_path.startswith("https://")):
                ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
                headers_str = f"User-Agent: {ua}\r\n"

            # 1. Spawn FFmpeg video decoder pipe
            v_cmd = [
                self._ffmpeg_bin,
                "-nostdin",
                "-loglevel", "error",
            ]
            if headers_str:
                v_cmd.extend(["-headers", headers_str])
            if self._current_pts > 0:
                v_cmd.extend(["-ss", f"{self._current_pts:.3f}"])

            v_cmd.extend([
                "-i", self.media_path,
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "-s", f"{self.width}x{self.height}",
                "-r", str(self.fps),
                "pipe:1"
            ])

            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            try:
                self._video_proc = subprocess.Popen(
                    v_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=self.frame_size * 5,
                    startupinfo=startupinfo,
                )
            except Exception as e:
                logger.error("[Player] Failed to spawn FFmpeg video process: %s", e)
                self._video_proc = None

            # 2. Spawn FFplay audio player (audio only with -nodisp)
            vol_int = max(0, min(100, int(self._volume * 100)))
            a_cmd = [
                self._ffplay_bin,
                "-nodisp",
                "-autoexit",
                "-loglevel", "quiet",
                "-volume", str(vol_int),
            ]
            if headers_str:
                a_cmd.extend(["-headers", headers_str])
            if self._current_pts > 0:
                a_cmd.extend(["-ss", f"{self._current_pts:.3f}"])
            a_cmd.extend(["-i", self.media_path])

            try:
                self._audio_proc = subprocess.Popen(
                    a_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    startupinfo=startupinfo,
                )
            except Exception as e:
                logger.debug("[Player] FFplay audio not available or failed: %s", e)
                self._audio_proc = None

            # 3. Start background frame reader thread associated with current_gen
            if self._video_proc and self._video_proc.stdout:
                self._reader_thread = threading.Thread(
                    target=self._frame_reader_loop,
                    args=(current_gen, self._video_proc),
                    daemon=True,
                )
                self._reader_thread.start()

    def _frame_reader_loop(self, gen: int, proc: subprocess.Popen):
        """Reads decoded raw RGB frames from FFmpeg stdout and queues them."""
        if not proc or not proc.stdout:
            return

        pts_interval = 1.0 / self.fps
        current_pts = self._current_pts

        try:
            while not self._is_closed and self._generation == gen and proc.poll() is None:
                raw_frame = proc.stdout.read(self.frame_size)
                if not raw_frame or len(raw_frame) < self.frame_size:
                    break

                current_pts += pts_interval
                # Put frame into bounded queue, checking generation on timeouts
                while not self._is_closed and self._generation == gen:
                    try:
                        self._frame_queue.put((raw_frame, current_pts), timeout=0.2)
                        break
                    except queue.Full:
                        continue

            # Signal EOF ONLY if this reader is still the active generation and not closed
            if not self._is_closed and self._generation == gen:
                self._frame_queue.put((None, "eof"))
        except Exception as err:
            logger.debug("[Player] Reader thread (gen %d) terminated: %s", gen, err)
        finally:
            try:
                if proc.stdout and not proc.stdout.closed:
                    proc.stdout.close()
            except Exception:
                pass

    def get_pts(self) -> float:
        """Returns the current presentation timestamp in seconds."""
        return self._current_pts

    def get_frame(self) -> Tuple[Optional[Tuple[ImageWrapper, float]], Optional[Union[str, float]]]:
        """
        Retrieves the next video frame paced according to playback clock.
        Returns:
            ((ImageWrapper, pts), delay_or_none) or (None, "eof") or (None, None)
        """
        if self._is_closed:
            return None, "eof"

        if self._is_paused:
            return None, None

        try:
            item = self._frame_queue.get_nowait()
        except queue.Empty:
            return None, None

        raw_bytes, pts_or_eof = item
        if pts_or_eof == "eof":
            return None, "eof"

        frame_pts = float(pts_or_eof)
        now = time.monotonic()

        # Calibrate monotonic clock upon first frame arrival after start/seek
        if not self._clock_started:
            self._start_mono_time = now - frame_pts
            self._clock_started = True

        elapsed = now - self._start_mono_time

        # If audio/system clock is ahead, drop stale frames to keep lip-sync
        while frame_pts < (elapsed - 0.15):
            try:
                next_item = self._frame_queue.get_nowait()
                if next_item[1] == "eof":
                    return None, "eof"
                raw_bytes, pts_or_eof = next_item
                frame_pts = float(pts_or_eof)
            except queue.Empty:
                break

        self._current_pts = frame_pts
        img_wrapper = ImageWrapper(raw_bytes, (self.width, self.height))
        return (img_wrapper, self._current_pts), None

    def set_pause(self, paused: bool):
        """Pauses or resumes audio and video decoding."""
        with self._lock:
            if self._is_paused == paused or self._is_closed:
                return

            self._is_paused = paused
            now = time.monotonic()

            if paused:
                self._pause_mono_time = now
                self._suspend_procs()
            else:
                paused_duration = now - self._pause_mono_time
                self._start_mono_time += paused_duration
                self._resume_procs()

    def _suspend_procs(self):
        """Suspends FFmpeg and FFplay worker processes on Windows/Unix."""
        if sys.platform == "win32":
            ntdll = getattr(ctypes.windll, "ntdll", None)
            if ntdll:
                for proc in (self._video_proc, self._audio_proc):
                    if proc and proc.poll() is None and hasattr(proc, "_handle"):
                        try:
                            ntdll.NtSuspendProcess(int(proc._handle))
                        except Exception:
                            pass
        else:
            import signal
            for proc in (self._video_proc, self._audio_proc):
                if proc and proc.poll() is None:
                    try:
                        proc.send_signal(signal.SIGSTOP)
                    except Exception:
                        pass

    def _resume_procs(self):
        """Resumes FFmpeg and FFplay worker processes on Windows/Unix."""
        if sys.platform == "win32":
            ntdll = getattr(ctypes.windll, "ntdll", None)
            if ntdll:
                for proc in (self._video_proc, self._audio_proc):
                    if proc and proc.poll() is None and hasattr(proc, "_handle"):
                        try:
                            ntdll.NtResumeProcess(int(proc._handle))
                        except Exception:
                            pass
        else:
            import signal
            for proc in (self._video_proc, self._audio_proc):
                if proc and proc.poll() is None:
                    try:
                        proc.send_signal(signal.SIGCONT)
                    except Exception:
                        pass

    def seek(self, pts: float, relative: bool = False):
        """Seeks playback to the specified presentation timestamp."""
        with self._lock:
            if self._is_closed:
                return

            curr = self._current_pts
            target = (curr + pts) if relative else pts
            target = max(0.0, target)
            logger.info("[Player] Seek requested: %.1fs", target)
            logger.info("[Player] Current position: %.1fs", curr)
            logger.info("[Player] Performing seek...")
            try:
                self._start_pipeline(start_pts=target)
                logger.info("[Player] Seek completed")
            except Exception:
                import traceback
                logger.error("[Player] Seek failed\n%s", traceback.format_exc())
                raise

    def set_volume(self, volume: float):
        """Sets playback volume from 0.0 to 1.0."""
        self._volume = max(0.0, min(1.0, float(volume)))

    def close_player(self):
        """Terminates all worker processes and frees playback resources."""
        self._is_closed = True
        with self._lock:
            self._stop_procs_internal()
        logger.info("[Player] Media player closed and resources freed.")

    def _stop_procs_internal(self):
        """Stops active processes (must be called with lock held)."""
        # Resume before terminating in case they were suspended
        if self._is_paused:
            self._resume_procs()

        for proc in (self._video_proc, self._audio_proc):
            if proc is not None:
                try:
                    if proc.stdout and not proc.stdout.closed:
                        proc.stdout.close()
                except Exception:
                    pass
                try:
                    proc.terminate()
                    proc.kill()
                    proc.wait(timeout=0.2)
                except Exception:
                    pass
        self._video_proc = None
        self._audio_proc = None
