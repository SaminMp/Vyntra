"""
Live On-The-Fly Transmuxing and Local Streaming Service for Full Video Playback.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import multiprocessing
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from typing import Dict, Optional, Tuple
import urllib.parse
import yt_dlp

from vyntra.models import SearchResult
from vyntra.services.auth_service import auth_service
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.utils.logger import logger


class StreamState:
    """Holds active video metadata and extracted direct stream URLs."""
    def __init__(self):
        self.lock = threading.Lock()
        self.current_video_id: str = ""
        self.title: str = ""
        self.channel: str = ""
        self.duration: int = 0
        self.video_url: str = ""
        self.audio_url: str = ""
        self.http_headers: Dict[str, str] = {}
        self.active_ffmpeg_proc: Optional[subprocess.Popen] = None

    def update(self, video_id: str, title: str, channel: str, duration: int, video_url: str, audio_url: str, headers: dict):
        with self.lock:
            self.current_video_id = video_id
            self.title = title
            self.channel = channel
            self.duration = duration
            self.video_url = video_url
            self.audio_url = audio_url
            self.http_headers = headers

    def stop_active_ffmpeg(self):
        with self.lock:
            if self.active_ffmpeg_proc:
                try:
                    self.active_ffmpeg_proc.terminate()
                    self.active_ffmpeg_proc.kill()
                except Exception:
                    pass
                self.active_ffmpeg_proc = None


stream_state = StreamState()


def generate_player_page(video_id: str, title: str, channel: str, duration_secs: int, stream_port: int) -> str:
    """Generates the full-featured modern Vyntra video player web page."""
    safe_title = title.replace('"', '&quot;').replace("'", "&#39;")
    safe_channel = channel.replace('"', '&quot;').replace("'", "&#39;")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_title} - Vyntra Player</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            user-select: none;
        }}
        body {{
            background-color: #0B0F19;
            color: #F8FAFC;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}
        .header {{
            background-color: #111827;
            padding: 12px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #1F2937;
            flex-shrink: 0;
            z-index: 10;
        }}
        .title-group {{
            display: flex;
            flex-direction: column;
            overflow: hidden;
            padding-right: 16px;
        }}
        .video-title {{
            font-size: 15px;
            font-weight: 600;
            color: #F8FAFC;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 600px;
        }}
        .video-channel {{
            font-size: 12px;
            color: #818CF8;
            margin-top: 2px;
        }}
        .brand-badge {{
            font-size: 12px;
            font-weight: 700;
            background-color: #1E293B;
            color: #38BDF8;
            padding: 5px 10px;
            border-radius: 6px;
            border: 1px solid #334155;
            white-space: nowrap;
        }}
        .player-wrapper {{
            flex: 1;
            position: relative;
            background-color: #000000;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }}
        video {{
            width: 100%;
            height: 100%;
            object-fit: contain;
            background-color: #000000;
        }}
        .controls-overlay {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background: linear-gradient(transparent, rgba(11, 15, 25, 0.95));
            padding: 20px 20px 14px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            transition: opacity 0.3s ease;
            opacity: 1;
            z-index: 20;
        }}
        .controls-overlay.hidden {{
            opacity: 0;
            pointer-events: none;
        }}
        .progress-container {{
            position: relative;
            width: 100%;
            height: 8px;
            background-color: rgba(51, 65, 85, 0.6);
            border-radius: 4px;
            cursor: pointer;
        }}
        .progress-container:hover {{
            height: 10px;
        }}
        .progress-bar {{
            height: 100%;
            background-color: #6366F1;
            border-radius: 4px;
            width: 0%;
            position: relative;
            transition: width 0.1s linear;
        }}
        .progress-bar::after {{
            content: '';
            position: absolute;
            right: -6px;
            top: 50%;
            transform: translateY(-50%);
            width: 12px;
            height: 12px;
            background-color: #FFFFFF;
            border-radius: 50%;
            box-shadow: 0 0 6px rgba(0,0,0,0.5);
            opacity: 0;
            transition: opacity 0.2s;
        }}
        .progress-container:hover .progress-bar::after {{
            opacity: 1;
        }}
        .controls-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .left-controls, .right-controls {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}
        .ctrl-btn {{
            background: transparent;
            border: none;
            color: #F8FAFC;
            font-size: 16px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            border-radius: 6px;
            transition: background 0.2s, color 0.2s;
        }}
        .ctrl-btn:hover {{
            background-color: rgba(255, 255, 255, 0.1);
            color: #38BDF8;
        }}
        .time-display {{
            font-size: 13px;
            color: #94A3B8;
            font-variant-numeric: tabular-nums;
            margin-left: 6px;
        }}
        .time-display .current {{
            color: #F8FAFC;
            font-weight: 600;
        }}
        .volume-box {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .volume-slider {{
            width: 80px;
            height: 4px;
            -webkit-appearance: none;
            background: #475569;
            border-radius: 2px;
            outline: none;
            cursor: pointer;
        }}
        .volume-slider::-webkit-slider-thumb {{
            -webkit-appearance: none;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #6366F1;
            cursor: pointer;
        }}
        .speed-select {{
            background: #1E293B;
            color: #F8FAFC;
            border: 1px solid #334155;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 12px;
            outline: none;
            cursor: pointer;
        }}
        .loading-spinner {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 48px;
            height: 48px;
            border: 4px solid rgba(99, 102, 241, 0.2);
            border-top-color: #6366F1;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            display: block;
            z-index: 15;
            pointer-events: none;
        }}
        @keyframes spin {{
            to {{ transform: translate(-50%, -50%) rotate(360deg); }}
        }}
        .center-indicator {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) scale(0.5);
            background: rgba(15, 23, 42, 0.75);
            width: 70px;
            height: 70px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 32px;
            color: #FFFFFF;
            opacity: 0;
            transition: transform 0.2s, opacity 0.2s;
            pointer-events: none;
            z-index: 18;
        }}
        .center-indicator.show {{
            opacity: 1;
            transform: translate(-50%, -50%) scale(1);
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title-group">
            <div class="video-title">{safe_title}</div>
            <div class="video-channel">👤 {safe_channel}</div>
        </div>
        <div class="brand-badge">🎵 Vyntra HD Player</div>
    </div>

    <div class="player-wrapper" id="player-box">
        <video id="video-elem" preload="auto" playsinline>
            <source src="http://127.0.0.1:{stream_port}/stream.mp4" type="video/mp4">
            Your system does not support the video tag.
        </video>

        <div class="loading-spinner" id="spinner"></div>
        <div class="center-indicator" id="center-ind">▶</div>

        <div class="controls-overlay" id="controls">
            <div class="progress-container" id="seek-bar">
                <div class="progress-bar" id="progress-filled"></div>
            </div>

            <div class="controls-row">
                <div class="left-controls">
                    <button class="ctrl-btn" id="play-btn" title="Play/Pause (Space)">▶</button>
                    <button class="ctrl-btn" id="rw-btn" title="Rewind 10s (Left Arrow)">⏪</button>
                    <button class="ctrl-btn" id="ff-btn" title="Forward 10s (Right Arrow)">⏩</button>

                    <div class="volume-box">
                        <button class="ctrl-btn" id="mute-btn" title="Mute/Unmute (M)">🔊</button>
                        <input type="range" class="volume-slider" id="vol-slider" min="0" max="1" step="0.05" value="1">
                    </div>

                    <div class="time-display">
                        <span class="current" id="curr-time">00:00</span> / <span id="dur-time">00:00</span>
                    </div>
                </div>

                <div class="right-controls">
                    <select class="speed-select" id="speed-select" title="Playback Speed">
                        <option value="0.75">0.75x</option>
                        <option value="1.0" selected>1.0x</option>
                        <option value="1.25">1.25x</option>
                        <option value="1.5">1.5x</option>
                        <option value="2.0">2.0x</option>
                    </select>

                    <button class="ctrl-btn" id="fs-btn" title="Fullscreen (F)">⛶</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const video = document.getElementById('video-elem');
        const spinner = document.getElementById('spinner');
        const centerInd = document.getElementById('center-ind');
        const controls = document.getElementById('controls');
        const playBtn = document.getElementById('play-btn');
        const muteBtn = document.getElementById('mute-btn');
        const volSlider = document.getElementById('vol-slider');
        const seekBar = document.getElementById('seek-bar');
        const progressFilled = document.getElementById('progress-filled');
        const currTime = document.getElementById('curr-time');
        const durTime = document.getElementById('dur-time');
        const speedSelect = document.getElementById('speed-select');
        const fsBtn = document.getElementById('fs-btn');
        const rwBtn = document.getElementById('rw-btn');
        const ffBtn = document.getElementById('ff-btn');
        const playerBox = document.getElementById('player-box');

        const totalDuration = {duration_secs};
        durTime.textContent = formatTime(totalDuration);

        function formatTime(secs) {{
            if (isNaN(secs) || secs < 0) return "00:00";
            const h = Math.floor(secs / 3600);
            const m = Math.floor((secs % 3600) / 60);
            const s = Math.floor(secs % 60);
            if (h > 0) {{
                return `${{h < 10 ? '0' : ''}}${{h}}:${{m < 10 ? '0' : ''}}${{m}}:${{s < 10 ? '0' : ''}}${{s}}`;
            }}
            return `${{m < 10 ? '0' : ''}}${{m}}:${{s < 10 ? '0' : ''}}${{s}}`;
        }}

        let virtualCurrentTime = 0;
        let isSeeking = false;
        let hideTimeout;

        function togglePlay() {{
            if (video.paused) {{
                video.play();
                playBtn.textContent = '⏸';
                showCenterIndicator('▶');
            }} else {{
                video.pause();
                playBtn.textContent = '▶';
                showCenterIndicator('⏸');
            }}
        }}

        function showCenterIndicator(icon) {{
            centerInd.textContent = icon;
            centerInd.classList.add('show');
            setTimeout(() => centerInd.classList.remove('show'), 400);
        }}

        function updateProgress() {{
            const current = virtualCurrentTime + video.currentTime;
            const dur = totalDuration > 0 ? totalDuration : (video.duration || 1);
            const pct = Math.min(100, (current / dur) * 100);
            progressFilled.style.width = pct + '%';
            currTime.textContent = formatTime(current);
        }}

        function seekTo(targetSeconds) {{
            targetSeconds = Math.max(0, Math.min(totalDuration, targetSeconds));
            virtualCurrentTime = targetSeconds;
            spinner.style.display = 'block';
            video.src = `http://127.0.0.1:{stream_port}/stream.mp4?start=${{Math.floor(targetSeconds)}}`;
            video.load();
            video.play();
            playBtn.textContent = '⏸';
        }}

        // Event Listeners
        playBtn.addEventListener('click', togglePlay);
        video.addEventListener('click', togglePlay);

        video.addEventListener('playing', () => {{
            spinner.style.display = 'none';
            playBtn.textContent = '⏸';
        }});

        video.addEventListener('waiting', () => {{
            spinner.style.display = 'block';
        }});

        video.addEventListener('timeupdate', updateProgress);

        video.addEventListener('loadeddata', () => {{
            spinner.style.display = 'none';
            video.play().catch(() => {{}});
        }});

        // Seek Bar Click
        seekBar.addEventListener('click', (e) => {{
            const rect = seekBar.getBoundingClientRect();
            const clickPos = (e.clientX - rect.left) / rect.width;
            const targetSec = clickPos * totalDuration;
            seekTo(targetSec);
        }});

        rwBtn.addEventListener('click', () => {{
            const cur = virtualCurrentTime + video.currentTime;
            seekTo(cur - 10);
        }});

        ffBtn.addEventListener('click', () => {{
            const cur = virtualCurrentTime + video.currentTime;
            seekTo(cur + 10);
        }});

        // Volume
        volSlider.addEventListener('input', (e) => {{
            video.volume = e.target.value;
            video.muted = (video.volume === 0);
            muteBtn.textContent = video.muted ? '🔇' : (video.volume > 0.5 ? '🔊' : '🔉');
        }});

        muteBtn.addEventListener('click', () => {{
            video.muted = !video.muted;
            muteBtn.textContent = video.muted ? '🔇' : '🔊';
            volSlider.value = video.muted ? 0 : video.volume;
        }});

        // Speed
        speedSelect.addEventListener('change', (e) => {{
            video.playbackRate = parseFloat(e.target.value);
        }});

        // Fullscreen
        fsBtn.addEventListener('click', () => {{
            if (!document.fullscreenElement) {{
                playerBox.requestFullscreen().catch(() => {{}});
            }} else {{
                document.exitFullscreen().catch(() => {{}});
            }}
        }});

        // Auto hide controls
        function resetControlsTimer() {{
            controls.classList.remove('hidden');
            clearTimeout(hideTimeout);
            hideTimeout = setTimeout(() => {{
                if (!video.paused) {{
                    controls.classList.add('hidden');
                }}
            }}, 3000);
        }}

        playerBox.addEventListener('mousemove', resetControlsTimer);

        // Keyboard Controls
        window.addEventListener('keydown', (e) => {{
            if (e.code === 'Space') {{
                e.preventDefault();
                togglePlay();
            }} else if (e.code === 'ArrowRight') {{
                seekTo(virtualCurrentTime + video.currentTime + 5);
            }} else if (e.code === 'ArrowLeft') {{
                seekTo(virtualCurrentTime + video.currentTime - 5);
            }} else if (e.code === 'ArrowUp') {{
                video.volume = Math.min(1, video.volume + 0.1);
                volSlider.value = video.volume;
            }} else if (e.code === 'ArrowDown') {{
                video.volume = Math.max(0, video.volume - 0.1);
                volSlider.value = video.volume;
            }} else if (e.code === 'KeyM') {{
                muteBtn.click();
            }} else if (e.code === 'KeyF') {{
                fsBtn.click();
            }}
        }});

        // Auto start
        video.play().catch(() => {{
            spinner.style.display = 'none';
        }});
    </script>
</body>
</html>
"""


class StreamHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for live media stream transmuxing and player interface."""

    def log_message(self, format, *args):
        # Silence default server stdout logging
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/player":
            self._serve_player()
        elif path == "/stream.mp4":
            start_secs = 0
            if "start" in query:
                try:
                    start_secs = max(0, int(query["start"][0]))
                except ValueError:
                    start_secs = 0
            self._serve_live_stream(start_secs)
        else:
            self.send_error(404, "Not Found")

    def _serve_player(self):
        """Serves the HTML player page."""
        stream_port = self.server.server_address[1]
        html = generate_player_page(
            video_id=stream_state.current_video_id,
            title=stream_state.title,
            channel=stream_state.channel,
            duration_secs=stream_state.duration,
            stream_port=stream_port,
        )
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_live_stream(self, start_seconds: int = 0):
        """Transmuxes video and audio on-the-fly and streams directly via chunked HTTP."""
        with stream_state.lock:
            v_url = stream_state.video_url
            a_url = stream_state.audio_url
            headers = stream_state.http_headers

        if not v_url:
            self.send_error(503, "No active video stream")
            return

        ffmpeg_status = ffmpeg_service.get_status()
        ffmpeg_bin = ffmpeg_status.ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"

        user_agent = headers.get("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
        header_arg = f"User-Agent: {user_agent}\r\n"

        cmd = [ffmpeg_bin, "-nostdin", "-loglevel", "warning"]

        if start_seconds > 0:
            cmd.extend(["-ss", str(start_seconds)])

        cmd.extend(["-headers", header_arg, "-i", v_url])

        if a_url and a_url != v_url:
            if start_seconds > 0:
                cmd.extend(["-ss", str(start_seconds)])
            cmd.extend(["-headers", header_arg, "-i", a_url])

        # Fast transmux with stream copy (no re-encoding)
        cmd.extend([
            "-c", "copy",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "-f", "mp4",
            "pipe:1"
        ])

        logger.info("Spawning FFmpeg stream worker: start=%ds", start_seconds)

        # Stop previous ffmpeg instance if any
        stream_state.stop_active_ffmpeg()

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=65536)
            with stream_state.lock:
                stream_state.active_ffmpeg_proc = proc

            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-cache, no-store")
            self.end_headers()

            # Stream chunks in real-time
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()

        except (BrokenPipeError, ConnectionResetError):
            logger.debug("Client closed stream connection.")
        except Exception as err:
            logger.debug("Streaming error: %s", err)
        finally:
            try:
                proc.terminate()
                proc.kill()
            except Exception:
                pass


class StreamServer:
    """Manages the background HTTP streaming server on a localhost port."""

    def __init__(self):
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._port: int = 0
        self._lock = threading.Lock()

    def start(self) -> int:
        """Starts the server on an available localhost port."""
        with self._lock:
            if self._server is None:
                # Find available ephemeral port
                self._server = ThreadingHTTPServer(("127.0.0.1", 0), StreamHandler)
                self._port = self._server.server_address[1]
                self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
                self._thread.start()
                logger.info("Started Local Stream Server on http://127.0.0.1:%d", self._port)
            return self._port

    def stop(self):
        """Stops the streaming server."""
        with self._lock:
            if self._server is not None:
                stream_state.stop_active_ffmpeg()
                self._server.shutdown()
                self._server.server_close()
                self._server = None
                self._thread = None
                self._port = 0
                logger.info("Stopped Local Stream Server.")

    @property
    def port(self) -> int:
        return self._port


stream_server = StreamServer()


def _run_player_window(port: int, title: str):
    """Subprocess runner for the dedicated hardware-accelerated player window."""
    try:
        import webview
        url = f"http://127.0.0.1:{port}/player"
        window = webview.create_window(
            title=f"Vyntra Player - {title[:50]}",
            url=url,
            width=900,
            height=600,
            resizable=True,
            background_color="#0B0F19",
        )
        webview.start()
    except Exception as e:
        print(f"Player window error: {e}", file=sys.stderr)


class StreamService:
    """Orchestrates stream extraction, transmuxing, and playback window."""

    def __init__(self):
        self._current_player_proc: Optional[multiprocessing.Process] = None
        self._lock = threading.Lock()

    def extract_stream_urls(self, video_id_or_url: str) -> Tuple[str, str, dict, int, str, str]:
        """
        Extracts direct video stream URL, audio stream URL, and headers using yt-dlp.
        Returns (video_url, audio_url, headers, duration_secs, title, channel).
        """
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "no_warnings": True,
        }
        ydl_opts.update(auth_service.get_ydl_cookie_opts())

        url = video_id_or_url if video_id_or_url.startswith("http") else f"https://www.youtube.com/watch?v={video_id_or_url}"
        logger.info("Extracting stream URLs for: %s", url)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise RuntimeError("Failed to extract video streams from YouTube.")

            formats = info.get("formats", [])
            headers = info.get("http_headers", {})
            title = info.get("title", "YouTube Video")
            channel = info.get("uploader", "YouTube Channel")
            duration = int(info.get("duration") or 0)

            # 1. Prefer combined progressive MP4 (720p/360p) if available
            v_url = None
            a_url = None

            for f in formats:
                if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("protocol") == "https" and f.get("ext") == "mp4":
                    v_url = f.get("url")
                    a_url = f.get("url")
                    break

            # 2. Otherwise pick best separate video MP4 and best separate audio
            if not v_url:
                for f in reversed(formats):
                    if not v_url and f.get("vcodec") != "none" and f.get("protocol") == "https" and f.get("ext") == "mp4":
                        v_url = f.get("url")
                    if not a_url and f.get("vcodec") == "none" and f.get("acodec") != "none" and f.get("protocol") == "https":
                        a_url = f.get("url")
                    if v_url and a_url:
                        break

            # Fallback if MP4 video not found: pick any video format
            if not v_url:
                for f in reversed(formats):
                    if f.get("vcodec") != "none" and f.get("protocol") == "https":
                        v_url = f.get("url")
                        break

            if not v_url:
                raise RuntimeError("No compatible video stream found for this video.")

            if not a_url:
                a_url = v_url  # Single stream fallback

            return (v_url, a_url, headers, duration, title, channel)

    def play_video(self, result: SearchResult) -> None:
        """Extracts streams and launches the full player window."""
        self.stop_playback()

        def _worker():
            try:
                v_url, a_url, headers, duration, title, channel = self.extract_stream_urls(result.url or result.video_id)
                stream_state.update(
                    video_id=result.video_id,
                    title=result.display_title or title,
                    channel=result.channel or channel,
                    duration=duration or result.duration_seconds,
                    video_url=v_url,
                    audio_url=a_url,
                    headers=headers,
                )

                port = stream_server.start()

                with self._lock:
                    self._current_player_proc = multiprocessing.Process(
                        target=_run_player_window,
                        args=(port, result.display_title),
                        daemon=True,
                    )
                    self._current_player_proc.start()

            except Exception as err:
                logger.error("Failed to start video playback for '%s': %s", result.title, err)

        threading.Thread(target=_worker, daemon=True).start()

    def stop_playback(self) -> None:
        """Terminates active player window and FFmpeg stream processes."""
        stream_state.stop_active_ffmpeg()
        with self._lock:
            if self._current_player_proc is not None:
                if self._current_player_proc.is_alive():
                    logger.info("Terminating active player window.")
                    self._current_player_proc.terminate()
                    self._current_player_proc.join(timeout=1.0)
                self._current_player_proc = None


# Global singleton instance
stream_service = StreamService()
