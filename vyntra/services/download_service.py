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
from vyntra.services.youtube_service import youtube_service
from vyntra.utils.filename import get_unique_filepath, sanitize_filename
from vyntra.utils.formatters import format_bytes, format_duration, format_eta, format_speed
from vyntra.utils.logger import logger


class DownloadCancelledException(Exception):
    """Raised when a download is actively cancelled by the user."""
    pass


class DownloadService:
    """Orchestrates YouTube media downloads, transcoding, and status tracking."""

    def __init__(self, max_concurrent: int = 3):
        self._max_concurrent = max_concurrent
        self._executor: Optional[ThreadPoolExecutor] = None
        self._active_tasks: Dict[str, DownloadTask] = {}
        self._lock = threading.Lock()
        self._ensure_executor()

    def _ensure_executor(self):
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=self._max_concurrent, thread_name_prefix="DownloadWorker")

    def shutdown(self, wait: bool = True, cancel_futures: bool = True) -> None:
        """Shuts down background download workers cleanly."""
        executor = None
        with self._lock:
            executor = self._executor
            self._executor = None

        if executor is not None:
            try:
                executor.shutdown(wait=wait, cancel_futures=cancel_futures)
            except TypeError:
                executor.shutdown(wait=wait)

    def reset(self) -> None:
        """Resets download service state and worker pool."""
        self.shutdown(wait=True)
        with self._lock:
            self._active_tasks.clear()
        self._ensure_executor()

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
        self._ensure_executor()
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
        """Builds yt-dlp option dictionary configured for format, quality, and metadata via platform service."""
        try:
            from vyntra.platforms.registry import platform_registry
            platform_svc = platform_registry.get(getattr(task, "platform", "youtube"))
            return platform_svc.build_download_options(task, out_base_without_ext)
        except Exception:
            return youtube_service.build_download_options(task, out_base_without_ext)

    def _execute_download(
        self,
        task: DownloadTask,
        on_progress: Callable[[ProgressInfo], None],
    ) -> str:
        """Synchronous core download execution using yt-dlp."""
        task.status = DownloadStatus.CONNECTING
        platform_name = str(getattr(task, "platform", "YouTube")).capitalize()
        progress_info = ProgressInfo(
            status=DownloadStatus.CONNECTING,
            status_message=f"Connecting to {platform_name}...",
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

        # Resolve effective download URL (match Spotify metadata to full song audio stream)
        download_url = task.result.url
        if getattr(task.result, "platform", "") == "spotify":
            artist = getattr(task.result, "channel", "") or ""
            title = getattr(task.result, "title", "") or task.result.display_title
            query = f"{artist} - {title} audio".strip(" -")
            download_url = f"ytsearch1:{query}"

        # Safe diagnostic format inspection logging
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl_probe:
                meta = ydl_probe.extract_info(download_url, download=False)
                if meta and "entries" in meta and meta["entries"]:
                    meta = meta["entries"][0]
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

        final_output_path = [None]

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
                fn = d.get("filename")
                if fn and Path(fn).is_file():
                    final_output_path[0] = Path(fn).resolve()

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

        def _pp_hook(d: dict):
            if d.get("status") == "finished":
                info_dict = d.get("info_dict") or {}
                fp = info_dict.get("filepath") or info_dict.get("_filename")
                if fp and Path(fp).is_file():
                    final_output_path[0] = Path(fp).resolve()

        ydl_opts["postprocessor_hooks"] = [_pp_hook]

        configured_dir = Path(task.save_directory).resolve()
        logger.info("[Download] Configured directory: %s", configured_dir)
        logger.info("Starting download for '%s' to '%s'", task.result.title, unique_file_path)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([download_url])
            except Exception as dl_err:
                if download_url != task.result.url and getattr(task.result, "preview_url", None):
                    logger.warning("[Download] Full song audio search failed (%s), falling back to preview URL", dl_err)
                    ydl.download([task.result.preview_url])
                else:
                    raise

        # Resolve final produced file path
        if final_output_path[0] and final_output_path[0].is_file():
            expected_output = final_output_path[0]
        elif unique_file_path.is_file():
            expected_output = unique_file_path.resolve()
        else:
            # Look for matching file in save_dir
            candidates = sorted(
                save_dir.glob(f"{sanitize_filename(task.result.display_title)}*.*"),
                key=lambda p: p.stat().st_mtime if p.is_file() else 0,
                reverse=True
            )
            valid_candidates = [p for p in candidates if p.suffix not in (".part", ".ytdl", ".tmp")]
            if valid_candidates:
                expected_output = valid_candidates[0].resolve()
            else:
                expected_output = unique_file_path.resolve()

        logger.info("[Download] Actual output file: %s", expected_output)
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
