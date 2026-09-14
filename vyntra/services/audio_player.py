"""
Dedicated Audio-Only Player for Vyntra.

Designed specifically for music streaming (Spotify previews and audio streams):
- Pure audio decoding via PyAV and low-latency playback via sounddevice
- Strictly ZERO video containers, ZERO video decoding threads, and ZERO video sync skew
- Thread-safe play, pause, seek, volume control, and EOF detection
- Clean resource reclamation on close
"""

import queue
import threading
import time
from typing import Any, Dict, List, Optional, Union
import av
import numpy as np
import sounddevice as sd

from vyntra.utils.logger import logger


class AudioPlayer:
    """
    Dedicated audio-only player for streaming remote audio (e.g. Spotify 30s previews).
    Avoids opening video pipelines or initializing video decoders entirely.
    """

    def __init__(self, media_payload: Union[Dict[str, Any], str], diagnostic_mode: bool = False):
        if isinstance(media_payload, str):
            self.audio_url = media_payload
            headers = {}
        else:
            self.audio_url = media_payload.get("audio_url", "")
            headers = media_payload.get("http_headers", {})

        self.diagnostic_mode = diagnostic_mode
        self._lock = threading.RLock()
        self._is_closed = False
        self._is_paused = False
        self._is_muted = False
        self._volume: float = 1.0
        self._pts: float = 0.0
        self._is_seeking = False
        self._eof_reached = False
        self._decoder_finished = False

        self._av_options = {
            "probesize": "1000000",
            "analyzeduration": "1000000",
            "timeout": "10000000",  # 10s network timeout
        }
        if headers:
            header_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
            self._av_options["headers"] = header_str

        # Containers and streams
        self._container: Optional[av.container.InputContainer] = None
        self._stream: Optional[Any] = None
        self._time_base: float = 1.0 / 44100.0
        self._sample_rate: int = 44100
        self._channels: int = 2
        self._device_sample_rate: int = 44100
        self._demux_lock = threading.Lock()
        self._demux_iter: Optional[Any] = None

        self._http_headers = headers

        # Queue and buffers (expanded buffer to completely prevent network underruns)
        self._audio_queue: queue.Queue = queue.Queue(maxsize=300)
        self._current_chunk: List[Any] = [b"", 0]  # [raw_pcm, byte_offset]
        self._decoder_thread: Optional[threading.Thread] = None
        self._device_stream: Optional[sd.RawOutputStream] = None

        logger.info("[AudioPlayer] Initializing audio-only pipeline for URL: %s", self.audio_url[:60] if self.audio_url else "empty")
        self._start_pipeline(start_pts=0.0)

    def _start_pipeline(self, start_pts: float = 0.0):
        with self._lock:
            self._close_internal_pipeline()
            self._pts = max(0.0, float(start_pts))
            self._is_seeking = False
            self._eof_reached = False
            self._decoder_finished = False

            if not self.audio_url or not self.audio_url.strip():
                raise ValueError("AudioPlayer requires a valid non-empty audio_url.")

            try:
                # Resolve audio source: for remote previews, cache locally to guarantee zero network jitter
                source_target = self.audio_url
                if self.audio_url.startswith("http://") or self.audio_url.startswith("https://"):
                    try:
                        import hashlib
                        import urllib.request
                        from pathlib import Path
                        cache_dir = Path.home() / ".vyntra" / "cache"
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        url_hash = hashlib.md5(self.audio_url.encode("utf-8")).hexdigest()
                        ext = ".m4a" if (".m4a" in self.audio_url or "aac" in self.audio_url) else ".mp3"
                        cached_file = cache_dir / f"spotify_{url_hash}{ext}"
                        if cached_file.is_file() and cached_file.stat().st_size > 5000:
                            source_target = str(cached_file)
                        else:
                            req = urllib.request.Request(
                                self.audio_url,
                                headers=self._http_headers or {"User-Agent": "Mozilla/5.0"},
                            )
                            with urllib.request.urlopen(req, timeout=8) as resp, open(cached_file, "wb") as f:
                                f.write(resp.read())
                            source_target = str(cached_file)
                    except Exception as cache_err:
                        logger.debug("[AudioPlayer] Direct stream fallback (cache note: %s)", cache_err)
                        source_target = self.audio_url

                # 1. Open strictly audio container
                opts = self._av_options if source_target == self.audio_url else {}
                self._container = av.open(source_target, options=opts)
                if not self._container.streams.audio:
                    raise ValueError("Container does not contain any audio streams.")

                self._stream = self._container.streams.audio[0]
                self._time_base = float(self._stream.time_base)
                self._sample_rate = self._stream.rate or 44100
                self._channels = 2
                self._demux_iter = self._container.demux(self._stream)

                # Query default hardware sample rate
                dev_rate = self._sample_rate
                try:
                    dev_info = sd.query_devices(kind="output")
                    if dev_info and dev_info.get("default_samplerate"):
                        dev_rate = int(dev_info["default_samplerate"])
                except Exception:
                    pass
                self._device_sample_rate = dev_rate

                # 2. Seek if requested
                if start_pts > 0.0:
                    target_ts = int(start_pts / self._time_base)
                    with self._demux_lock:
                        self._container.seek(target_ts, stream=self._stream)
                        self._demux_iter = self._container.demux(self._stream)

                # 3. Launch decoder worker thread
                self._decoder_thread = threading.Thread(target=self._decoder_loop, daemon=True, name="AudioPlayerDecoder")
                self._decoder_thread.start()

                # Pre-buffer: build at least ~400ms buffer before starting hardware playback
                deadline = time.monotonic() + 0.8
                while time.monotonic() < deadline and self._audio_queue.qsize() < 16 and not self._decoder_finished and not self._is_closed:
                    time.sleep(0.015)

                # 4. Open audio output stream
                self._open_device_stream()

            except Exception as e:
                logger.error("[AudioPlayer] Failed to start audio pipeline: %s", e)
                self._close_internal_pipeline()
                raise

    def _open_device_stream(self):
        bytes_per_sample = self._channels * 2

        def _audio_callback(outdata, frames, time_info, status):
            if self._is_closed or self._is_paused or self._is_seeking:
                outdata[:] = b"\x00" * len(outdata)
                return

            written = 0
            needed_bytes = frames * bytes_per_sample
            vol = 0.0 if self._is_muted else self._volume

            while needed_bytes > 0:
                raw_b, offset = self._current_chunk
                if offset >= len(raw_b):
                    try:
                        new_b, chunk_pts = self._audio_queue.get_nowait()
                        self._current_chunk = [new_b, 0]
                        self._pts = chunk_pts
                        raw_b, offset = self._current_chunk
                    except queue.Empty:
                        if self._decoder_finished:
                            self._eof_reached = True
                        break

                avail = len(raw_b) - offset
                take = min(needed_bytes, avail)
                take = (take // bytes_per_sample) * bytes_per_sample
                if take == 0:
                    self._current_chunk = [b"", 0]
                    continue

                if vol >= 1.0:
                    outdata[written:written + take] = raw_b[offset:offset + take]
                elif vol <= 0.0:
                    outdata[written:written + take] = b"\x00" * take
                else:
                    chunk_samples = np.frombuffer(raw_b[offset:offset + take], dtype=np.int16)
                    scaled = (chunk_samples * vol).astype(np.int16)
                    outdata[written:written + take] = scaled.tobytes()

                offset += take
                self._current_chunk[1] = offset
                written += take
                needed_bytes -= take
                self._pts += (take / bytes_per_sample) / self._device_sample_rate

            if written < len(outdata):
                outdata[written:] = b"\x00" * (len(outdata) - written)

        self._device_stream = sd.RawOutputStream(
            samplerate=self._device_sample_rate,
            channels=self._channels,
            dtype="int16",
            callback=_audio_callback,
            blocksize=1024,
        )
        self._device_stream.start()

    def _decoder_loop(self):
        """Demuxes audio packets, resamples to stereo 16-bit PCM, and queues them."""
        if not self._container or not self._stream:
            return

        try:
            resampler = av.AudioResampler(
                format="s16",
                layout="stereo",
                rate=self._device_sample_rate,
            )

            while not self._is_closed:
                if self._is_seeking:
                    time.sleep(0.01)
                    continue

                with self._demux_lock:
                    if self._demux_iter is None:
                        break
                    try:
                        packet = next(self._demux_iter)
                    except StopIteration:
                        break
                    except Exception as demux_err:
                        if not self._is_closed:
                            logger.debug("[AudioPlayer] Demux finished: %s", demux_err)
                        break

                frames = packet.decode()
                if not frames:
                    time.sleep(0.002)
                    continue

                for frame in frames:
                    if self._is_closed:
                        break
                    for resampled in resampler.resample(frame):
                        # Slice exact valid sample bytes to discard 128-byte memory alignment padding
                        valid_bytes = resampled.samples * (self._channels * 2)
                        raw_pcm = bytes(resampled.planes[0])[:valid_bytes]
                        pts = float(frame.pts * self._time_base) if frame.pts is not None else self._pts

                        while not self._is_closed and not self._is_seeking:
                            try:
                                self._audio_queue.put((raw_pcm, pts), timeout=0.05)
                                break
                            except queue.Full:
                                continue

            self._decoder_finished = True
        except Exception as e:
            if not self._is_closed:
                logger.debug("[AudioPlayer] Decoder reached end: %s", e)
            self._decoder_finished = True

    def get_pts(self) -> float:
        """Returns current media playback position in seconds."""
        return max(0.0, self._pts)

    def set_pause(self, paused: bool):
        """Pauses or resumes audio playback."""
        with self._lock:
            if self._is_paused == paused or self._is_closed:
                return
            self._is_paused = paused
            if self._device_stream:
                try:
                    if paused:
                        self._device_stream.stop()
                    else:
                        self._device_stream.start()
                except Exception:
                    pass

    def seek(self, target_pts: float):
        """Seeks the audio container to the desired timestamp in seconds."""
        with self._lock:
            if self._is_closed:
                return

            self._is_seeking = True
            self._pts = max(0.0, float(target_pts))
            self._eof_reached = False
            self._decoder_finished = False

            # Drain queue and current chunk
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break
            self._current_chunk = [b"", 0]

            if self._container and self._stream:
                with self._demux_lock:
                    try:
                        target_ts = int(self._pts / self._time_base)
                        self._container.seek(target_ts, stream=self._stream)
                        self._demux_iter = self._container.demux(self._stream)
                        if hasattr(self._stream, "codec_context") and self._stream.codec_context:
                            self._stream.codec_context.flush_buffers()
                    except Exception as e:
                        logger.warning("[AudioPlayer] Seek failed: %s", e)

            self._is_seeking = False

    def set_volume(self, volume: float):
        """Adjusts playback volume between 0.0 and 1.0."""
        with self._lock:
            self._volume = max(0.0, min(1.0, float(volume)))

    def is_eof(self) -> bool:
        """Returns True if the entire stream has finished playing."""
        return self._eof_reached

    def is_playing(self) -> bool:
        return not self._is_paused and not self._is_closed and not self._eof_reached

    def _close_internal_pipeline(self):
        if self._device_stream:
            try:
                self._device_stream.stop()
                self._device_stream.close()
            except Exception:
                pass
            self._device_stream = None

        if self._container:
            with self._demux_lock:
                self._demux_iter = None
                try:
                    self._container.close()
                except Exception:
                    pass
            self._container = None
            self._stream = None

    def close(self):
        """Safely shuts down the audio player and releases all hardware/file resources."""
        with self._lock:
            if self._is_closed:
                return
            self._is_closed = True
            self._close_internal_pipeline()

            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break
            self._current_chunk = [b"", 0]
            logger.info("[AudioPlayer] Closed audio player successfully.")
