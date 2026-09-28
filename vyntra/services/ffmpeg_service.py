"""
FFmpeg detection, path resolution, and capability diagnostics for Vyntra.
"""

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from vyntra.config import config_manager
from vyntra.utils.logger import logger


@dataclass
class FFmpegStatus:
    """Diagnostic state of FFmpeg installation."""
    is_available: bool
    ffmpeg_path: Optional[str] = None
    ffprobe_path: Optional[str] = None
    version: Optional[str] = None
    install_guide: str = ""


class FFmpegService:
    """Handles auto-detection and validation of FFmpeg binary."""

    def __init__(self):
        self._status: Optional[FFmpegStatus] = None

    def get_status(self, force_refresh: bool = False) -> FFmpegStatus:
        """Returns cached or freshly detected FFmpeg status."""
        if self._status is None or force_refresh:
            self._status = self._detect_ffmpeg()
        return self._status

    def _get_candidate_paths(self) -> List[str]:
        """Returns standard locations where FFmpeg might reside based on OS."""
        candidates = []

        # 1. Custom user path from config
        custom_path = config_manager.config.custom_ffmpeg_path
        if custom_path and os.path.exists(custom_path):
            candidates.append(custom_path)

        # 2. System PATH lookup
        path_which = shutil.which("ffmpeg")
        if path_which:
            candidates.append(path_which)

        # 3. Executable / portable directory lookup
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).parent
            candidates.extend([
                str(exe_dir / "ffmpeg.exe"),
                str(exe_dir / "bin" / "ffmpeg.exe"),
                str(exe_dir / "ffmpeg"),
            ])
            if hasattr(sys, "_MEIPASS"):
                candidates.extend([
                    str(Path(sys._MEIPASS) / "ffmpeg.exe"),
                    str(Path(sys._MEIPASS) / "ffmpeg"),
                ])
        else:
            candidates.extend([
                str(Path.cwd() / "ffmpeg.exe"),
                str(Path.cwd() / "bin" / "ffmpeg.exe"),
            ])

        # 3. macOS standard paths (Homebrew, MacPorts, local)
        if platform.system() == "Darwin":
            candidates.extend([
                "/opt/homebrew/bin/ffmpeg",
                "/usr/local/bin/ffmpeg",
                "/opt/local/bin/ffmpeg",
                str(Path.home() / "bin" / "ffmpeg"),
            ])
        # 4. Windows standard paths
        elif platform.system() == "Windows":
            candidates.extend([
                r"C:\ffmpeg\bin\ffmpeg.exe",
                r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
            ])
        # 5. Linux standard paths
        elif platform.system() == "Linux":
            candidates.extend([
                "/usr/bin/ffmpeg",
                "/usr/local/bin/ffmpeg",
                "/snap/bin/ffmpeg",
            ])

        return [c for c in candidates if os.path.isfile(c) and os.access(c, os.X_OK)]

    def _detect_ffmpeg(self) -> FFmpegStatus:
        """Performs detection and executes quick probe."""
        candidates = self._get_candidate_paths()

        system_name = platform.system()
        if system_name == "Darwin":
            guide = "Run 'brew install ffmpeg' in your Terminal to enable MP3 conversion and high-res video muxing."
        elif system_name == "Windows":
            guide = "Run 'winget install Gyan.FFmpeg' in PowerShell or download from https://ffmpeg.org."
        else:
            guide = "Run 'sudo apt install ffmpeg' or equivalent package manager command."

        for path in candidates:
            try:
                # Test executing ffmpeg -version
                result = subprocess.run(
                    [path, "-version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=3,
                )
                if result.returncode == 0:
                    first_line = result.stdout.splitlines()[0] if result.stdout else "FFmpeg (detected)"
                    
                    # Also look for ffprobe alongside ffmpeg
                    ffmpeg_dir = Path(path).parent
                    ffprobe_candidate = ffmpeg_dir / ("ffprobe.exe" if system_name == "Windows" else "ffprobe")
                    ffprobe_path = str(ffprobe_candidate) if ffprobe_candidate.is_file() else shutil.which("ffprobe")

                    logger.info("FFmpeg detected successfully: %s (%s)", path, first_line)
                    return FFmpegStatus(
                        is_available=True,
                        ffmpeg_path=path,
                        ffprobe_path=ffprobe_path,
                        version=first_line,
                        install_guide=guide,
                    )
            except Exception as err:
                logger.debug("Failed checking candidate path %s: %s", path, err)

        logger.warning("FFmpeg was not detected on this system.")
        return FFmpegStatus(
            is_available=False,
            ffmpeg_path=None,
            ffprobe_path=None,
            version=None,
            install_guide=guide,
        )

    def inspect_media_file(self, file_path: str) -> dict:
        """
        Inspects resulting media file properties to verify height, resolution, and codecs.
        Returns a dictionary with width, height, resolution, video_codec, audio_codec,
        container, has_video, and has_audio.
        """
        info = {
            "width": 0,
            "height": 0,
            "resolution": "",
            "video_codec": "",
            "audio_codec": "",
            "container": "",
            "has_video": False,
            "has_audio": False,
        }
        p = Path(file_path)
        if not p.is_file():
            return info

        info["container"] = p.suffix.lstrip(".").lower()

        # 1. Try PyAV inspection
        try:
            import av
            with av.open(str(p)) as container:
                if container.format and container.format.name:
                    info["container"] = container.format.name.split(",")[0]
                if container.streams.video:
                    v = container.streams.video[0]
                    info["has_video"] = True
                    info["width"] = v.width or 0
                    info["height"] = v.height or 0
                    if v.width and v.height:
                        info["resolution"] = f"{v.width}x{v.height}"
                    if v.codec_context and v.codec_context.name:
                        info["video_codec"] = v.codec_context.name
                if container.streams.audio:
                    info["has_audio"] = True
                    a = container.streams.audio[0]
                    if a.codec_context and a.codec_context.name:
                        info["audio_codec"] = a.codec_context.name
            return info
        except Exception as av_err:
            logger.debug("[FFmpeg] PyAV media inspection exception: %s", av_err)

        # 2. Fallback to ffprobe if available
        status = self.get_status()
        if status.ffprobe_path and os.path.isfile(status.ffprobe_path):
            try:
                import json
                cmd = [
                    status.ffprobe_path,
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams",
                    str(p),
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    data = json.loads(res.stdout)
                    for stream in data.get("streams", []):
                        codec_type = stream.get("codec_type")
                        if codec_type == "video" and not info["has_video"]:
                            info["has_video"] = True
                            info["width"] = int(stream.get("width") or 0)
                            info["height"] = int(stream.get("height") or 0)
                            if info["width"] and info["height"]:
                                info["resolution"] = f"{info['width']}x{info['height']}"
                            info["video_codec"] = stream.get("codec_name") or ""
                        elif codec_type == "audio" and not info["has_audio"]:
                            info["has_audio"] = True
                            info["audio_codec"] = stream.get("codec_name") or ""
            except Exception as probe_err:
                logger.debug("[FFmpeg] ffprobe inspection fallback exception: %s", probe_err)

        return info


# Global singleton instance
ffmpeg_service = FFmpegService()
