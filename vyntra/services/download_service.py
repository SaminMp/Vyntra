"""
Robust download engine and media conversion service using yt-dlp.
"""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import shutil
import threading
from typing import Callable, Dict, Optional
import yt_dlp

from vyntra.config import config_manager
from vyntra.models import DownloadStatus, DownloadTask, MediaFormat, ProgressInfo
from vyntra.services.auth_service import auth_service
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.utils.filename import get_unique_filepath, sanitize_filename
from vyntra.utils.formatters import format_bytes, format_duration, format_eta, format_speed
from vyntra.utils.logger import logger


class DownloadCancelledException(Exception):
    """Raised when a download is actively cancelled by the user."""
    pass


class DownloadService:
    """Orchestrates YouTube media downloads, transcoding, and status tracking."""

    def __init__(self, max_concurrent: int = 3):
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent, thread_name_prefix="DownloadWorker")
        self._active_tasks: Dict[str, DownloadTask] = {}
        self._lock = threading.Lock()

    def start_download(
        self,
        task: DownloadTask,
        on_progress: Callable[[ProgressInfo], None],
        on_complete: Callable[[str], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        """
        Starts downloading a task on a background worker thread.
        """
        with self._lock:
            self._active_tasks[task.task_id] = task

        def _worker():
            try:
                out_path = self._execute_download(task, on_progress)
                with self._lock:
                    self._active_tasks.pop(task.task_id, None)
                task.status = DownloadStatus.COMPLETED
                task.output_filepath = out_path
                on_complete(out_path)
            except DownloadCancelledException:
                logger.info("Download task %s was cancelled.", task.task_id)
                task.status = DownloadStatus.CANCELLED
                self._cleanup_temp_files(task)
                with self._lock:
                    self._active_tasks.pop(task.task_id, None)
            except Exception as err:
                translated_msg = auth_service.translate_error(err)
                logger.error("Download error for task %s: %s", task.task_id, translated_msg)
                task.status = DownloadStatus.ERROR
                task.error_message = translated_msg
                self._cleanup_temp_files(task)
                with self._lock:
                    self._active_tasks.pop(task.task_id, None)
                on_error(RuntimeError(translated_msg))

        self._executor.submit(_worker)

    def cancel_download(self, task_id: str) -> bool:
        """Flags an active download task for immediate cancellation."""
        with self._lock:
            task = self._active_tasks.get(task_id)
            if task:
                task.is_cancelled = True
                task.status = DownloadStatus.CANCELLED
                logger.info("Flagged download task %s for cancellation.", task_id)
                return True
        return False

    def is_downloading(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._active_tasks

    def build_ydl_options(self, task: DownloadTask, out_base_without_ext: str) -> dict:
        """Builds yt-dlp option dictionary configured for format, quality, metadata and cookies."""
        ffmpeg_status = ffmpeg_service.get_status()
        ffmpeg_bin_dir = str(Path(ffmpeg_status.ffmpeg_path).parent) if ffmpeg_status.ffmpeg_path else None

        # Base yt-dlp options
        ydl_opts = {
            "outtmpl": f"{out_base_without_ext}.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "retries": 5,
            "fragment_retries": 5,
            "socket_timeout": 15,
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)",
        }

        # Apply YouTube cookie options
        ydl_opts.update(auth_service.get_ydl_cookie_opts())

        if ffmpeg_bin_dir:
            ydl_opts["ffmpeg_location"] = ffmpeg_bin_dir

        # Format & Post-Processor configuration
        if task.format == MediaFormat.MP3:
            # Resolve bitrate (e.g. "320 kbps" -> "320")
            raw_q = str(getattr(task, "selected_quality", "") or getattr(task.audio_quality, "value", "320"))
            digits = "".join(filter(str.isdigit, raw_q))
            bitrate = digits if digits in ("128", "192", "256", "320") else "320"

            if ffmpeg_status.is_available:
                ydl_opts.update({
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": bitrate,
                        },
                        {
                            "key": "FFmpegMetadata",
                            "add_metadata": True,
                        },
                    ],
                })
            else:
                logger.warning("FFmpeg unavailable. Falling back to native audio stream.")
                ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
        else:
            # Video (MP4) - Resolve requested height with fallback
            raw_q = str(getattr(task, "selected_quality", "") or getattr(task.video_quality, "value", "best")).lower()
            height_match = re.search(r"(\d{3,4})", raw_q)
            target_height = int(height_match.group(1)) if height_match else None

            if ffmpeg_status.is_available:
                if target_height:
                    # Dynamically target <= height with fallback to closest available resolution
                    format_spec = (
                        f"bestvideo[height<={target_height}][ext=mp4]+bestaudio[ext=m4a]/"
                        f"bestvideo[height<={target_height}][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                        f"bestvideo[height<={target_height}]+bestaudio/"
                        f"best[height<={target_height}][ext=mp4]/"
                        f"best[height<={target_height}]/best"
                    )
                else:
                    format_spec = (
                        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                        "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                        "bestvideo+bestaudio/best[ext=mp4]/best"
                    )

                ydl_opts.update({
                    "format": format_spec,
                    "merge_output_format": "mp4",
                    "postprocessors": [
                        {
                            "key": "FFmpegMetadata",
                            "add_metadata": True,
                        }
                    ],
                })
            else:
                logger.warning("FFmpeg unavailable. Falling back to native stream without muxing.")
                if target_height:
                    ydl_opts["format"] = f"best[height<={target_height}][ext=mp4]/best[height<={target_height}]/best"
                else:
                    ydl_opts["format"] = "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"

        return ydl_opts

    def _execute_download(
        self,
        task: DownloadTask,
        on_progress: Callable[[ProgressInfo], None],
    ) -> str:
        """Synchronous core download execution using yt-dlp."""
        task.status = DownloadStatus.CONNECTING
        progress_info = ProgressInfo(
            status=DownloadStatus.CONNECTING,
            status_message="Connecting to YouTube...",
            filename=task.result.display_title,
        )
        on_progress(progress_info)

        # Prepare save folder & base filename
        save_dir = Path(task.save_directory)
        save_dir.mkdir(parents=True, exist_ok=True)

        target_ext = "mp3" if task.format == MediaFormat.MP3 else "mp4"
        unique_file_path = get_unique_filepath(save_dir, task.result.display_title, target_ext)
        out_base_without_ext = str(unique_file_path.with_suffix(""))

        ffmpeg_status = ffmpeg_service.get_status()

        # Base yt-dlp options
        ydl_opts = self.build_ydl_options(task, out_base_without_ext)

        # Safe diagnostic format inspection logging
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl_probe:
                meta = ydl_probe.extract_info(task.result.url, download=False)
                if meta:
                    v_h = meta.get("height")
                    v_res = f"{v_h}p" if v_h else (meta.get("resolution") or "audio only")
                    v_codec = meta.get("vcodec") or "none"
                    a_codec = meta.get("acodec") or "none"
                    abr = meta.get("abr")
                    a_str = f"{int(abr)}kbps" if abr else a_codec
                    logger.info(
                        "[Download] Requested output: %s\n"
                        "[Download] Selected video: %s\n"
                        "[Download] Selected audio: %s\n"
                        "[Download] Container: %s",
                        task.format.value,
                        v_res,
                        a_str,
                        target_ext,
                    )
        except Exception as probe_err:
            logger.debug("Format pre-inspection skipped: %s", probe_err)

        # Attach progress hook
        def _hook(d: dict):
            if task.is_cancelled:
                raise DownloadCancelledException("Download cancelled by user.")

            status_str = d.get("status")
            if status_str == "downloading":
                task.status = DownloadStatus.DOWNLOADING
                downloaded = d.get("downloaded_bytes") or 0
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0

                percent = (downloaded / total * 100.0) if total > 0 else 0.0
                speed = d.get("speed")
                eta = d.get("eta")

                prog = ProgressInfo(
                    status=DownloadStatus.DOWNLOADING,
                    percent=percent,
                    downloaded_bytes=downloaded,
                    total_bytes=total,
                    speed_str=format_speed(speed),
                    eta_str=format_eta(eta),
                    status_message=f"Downloading {task.format.value}... ({format_bytes(downloaded)} / {format_bytes(total)})",
                    filename=unique_file_path.name,
                )
                task.progress = prog
                on_progress(prog)

            elif status_str == "finished":
                task.status = DownloadStatus.CONVERTING
                prog = ProgressInfo(
                    status=DownloadStatus.CONVERTING,
                    percent=100.0,
                    downloaded_bytes=d.get("total_bytes") or 0,
                    total_bytes=d.get("total_bytes") or 0,
                    speed_str="Processing",
                    eta_str="00:00",
                    status_message="Processing & converting media..." if ffmpeg_status.is_available else "Finalizing file...",
                    filename=unique_file_path.name,
                )
                task.progress = prog
                on_progress(prog)

        ydl_opts["progress_hooks"] = [_hook]

        logger.info("Starting download for '%s' to '%s'", task.result.title, unique_file_path)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([task.result.url])

        # Resolve final produced file path
        expected_output = unique_file_path
        if not expected_output.exists():
            # If native fallback created .m4a or .webm
            candidates = list(save_dir.glob(f"{sanitize_filename(task.result.display_title)}*.*"))
            if candidates:
                expected_output = candidates[0]

        logger.info("Download completed successfully: %s", expected_output)
        return str(expected_output)

    def _cleanup_temp_files(self, task: DownloadTask) -> None:
        """Removes leftover .part, .ytdl, or intermediate files for a task."""
        try:
            save_dir = Path(task.save_directory)
            if not save_dir.exists():
                return

            base_name = sanitize_filename(task.result.display_title)
            # Find matching part/temp files
            for temp_file in save_dir.glob(f"{base_name}*"):
                if temp_file.suffix in [".part", ".ytdl", ".temp", ".tmp"]:
                    try:
                        temp_file.unlink(missing_ok=True)
                        logger.info("Cleaned up temp file: %s", temp_file)
                    except Exception as e:
                        logger.debug("Failed deleting temp file %s: %s", temp_file, e)
        except Exception as err:
            logger.debug("Error during temp cleanup: %s", err)


# Global singleton instance
download_service = DownloadService()
