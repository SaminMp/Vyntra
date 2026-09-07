"""
Centralized YouTube Service for Vyntra.

Single source of truth for all YouTube operations:
- Authentication & session management (user-consented cookies, Google OAuth distinction)
- Proof of Origin (PO) Token inspection & tracking
- JavaScript runtime detection (Node.js >= 22.0.0) and EJS remote challenge solving
- Player client configuration
- Real format and resolution probing (NO fake fallbacks)
- Playback media buffering & preparation
- Download options configuration
- Comprehensive diagnostic mode (Section 9) with strict privacy guarantees
"""

import datetime
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple

import yt_dlp

from vyntra.config import config_manager
from vyntra.models import DownloadTask, MediaFormat, SearchResult
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.utils.filename import sanitize_filename
from vyntra.utils.logger import logger


class YouTubeService:
    """Unified YouTube extraction, authentication, format probing, and playback engine."""

    def __init__(self):
        self._resolution_cache: Dict[str, List[str]] = {}
        self._node_path: Optional[str] = None
        self._node_checked: bool = False

    # ----------------------------------------------------------------------
    # 1. Environment & Runtime Detection
    # ----------------------------------------------------------------------

    @property
    def ytdlp_version(self) -> str:
        """Returns the exact installed yt-dlp version."""
        try:
            from yt_dlp.version import __version__
            return str(__version__)
        except Exception:
            return getattr(yt_dlp, "__version__", "unknown")

    def get_node_path(self) -> Optional[str]:
        """Discovers a Node.js binary satisfying yt-dlp requirements (version >= 22.0.0)."""
        if self._node_checked:
            return self._node_path

        candidates = [
            "/opt/homebrew/bin/node",
            "/usr/local/bin/node",
            shutil.which("node"),
        ]

        for cand in candidates:
            if not cand or not Path(cand).is_file():
                continue
            try:
                res = subprocess.run(
                    [cand, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if res.returncode == 0:
                    ver_str = res.stdout.strip().lstrip("v")
                    major_ver = int(ver_str.split(".")[0])
                    if major_ver >= 22:
                        self._node_path = cand
                        self._node_checked = True
                        return cand
            except Exception:
                continue

        self._node_checked = True
        return None

    # ----------------------------------------------------------------------
    # 2. Authentication & Cookie Management (Explicit & User-Consented)
    # ----------------------------------------------------------------------

    def get_cookie_file_path(self) -> Optional[str]:
        """
        Resolves explicit, user-consented cookie file path.
        Checks custom configured cookie file or standard ~/.vyntra/cookies.txt.
        Vyntra strictly DOES NOT silently scrape browser cookies behind the user's back.
        """
        custom_path = getattr(config_manager.config, "custom_cookie_path", "")
        if custom_path and Path(custom_path).is_file() and Path(custom_path).stat().st_size > 10:
            return str(custom_path)

        standard_path = Path.home() / ".vyntra" / "cookies.txt"
        if standard_path.is_file() and standard_path.stat().st_size > 10:
            return str(standard_path)

        return None

    def is_cookies_available(self) -> bool:
        """Returns True if a valid user-consented cookie file is available."""
        return self.get_cookie_file_path() is not None

    def is_google_oauth_connected(self) -> bool:
        """Checks if Google Identity OAuth is connected in Vyntra."""
        try:
            from vyntra.services.auth_manager import auth_manager
            return auth_manager.is_authenticated()
        except Exception:
            return False

    # ----------------------------------------------------------------------
    # 3. PO Token Inspection
    # ----------------------------------------------------------------------

    def get_po_token_info(self) -> Tuple[str, bool, bool]:
        """
        Returns (provider_name, is_generated, is_attached).
        Audits whether a real PO Token exists and will be attached to YouTube requests.
        """
        po_token_file = Path.home() / ".vyntra" / "po_token.json"
        if po_token_file.is_file():
            try:
                with open(po_token_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    token = data.get("po_token")
                    if token:
                        return ("Manual PO Token (~/.vyntra/po_token.json)", True, True)
            except Exception:
                pass

        return ("None (No PO Token Provider Configured)", False, False)

    # ----------------------------------------------------------------------
    # 4. Centralized yt-dlp Options Construction
    # ----------------------------------------------------------------------

    def get_player_clients(self) -> List[str]:
        """Returns the prioritized Innertube player client chain."""
        return ["tv_embedded", "web_embedded", "android", "ios", "web"]

    def get_base_ydl_options(self, purpose: str = "general") -> Dict[str, Any]:
        """
        Constructs the unified, hardened yt-dlp options dictionary used by:
        - Format probing
        - Video playback
        - Media downloads
        """
        ydl_opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "socket_timeout": 15 if purpose == "download" else 10,
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)",
            "extractor_args": {
                "youtube": {
                    "player_client": self.get_player_clients(),
                }
            },
        }

        # 1. Attach Node.js runtime and EJS remote challenge solver if available
        node_path = self.get_node_path()
        if node_path:
            ydl_opts["js_runtimes"] = {
                "node": {"path": node_path}
            }
            ydl_opts["remote_components"] = ["ejs:github"]

        # 2. Attach explicit user-consented cookie file if available
        cookie_file = self.get_cookie_file_path()
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file

        # 3. Attach manual PO Token if configured
        po_token_file = Path.home() / ".vyntra" / "po_token.json"
        if po_token_file.is_file():
            try:
                with open(po_token_file, "r", encoding="utf-8") as f:
                    pot_data = json.load(f)
                    po_token = pot_data.get("po_token")
                    visitor_data = pot_data.get("visitor_data")
                    if po_token:
                        ydl_opts["extractor_args"]["youtube"]["po_token"] = [f"web+{po_token}"]
                    if visitor_data:
                        ydl_opts["extractor_args"]["youtube"]["visitor_data"] = [visitor_data]
            except Exception as e:
                logger.debug("Could not load ~/.vyntra/po_token.json: %s", e)

        return ydl_opts

    # ----------------------------------------------------------------------
    # 5. Error Classification
    # ----------------------------------------------------------------------

    def classify_error(self, err: Exception) -> str:
        """Classifies YouTube extraction exceptions into clear, actionable human categories."""
        raw = str(err).strip()

        if "Sign in to confirm you’re not a bot" in raw or "confirm you're not a bot" in raw or "LOGIN_REQUIRED" in raw:
            return (
                "YouTube requires sign-in verification for this video. "
                "Export your YouTube cookies to ~/.vyntra/cookies.txt to enable access."
            )
        if "Private video" in raw:
            return "This video is private and cannot be accessed."
        if "This video is unavailable" in raw or "Video unavailable" in raw:
            return "This video is unavailable or has been removed from YouTube."
        if "Requested format is not available" in raw or "format is not available" in raw:
            return "No compatible format is available from YouTube for this video."
        if "HTTP Error 429" in raw or "Too Many Requests" in raw:
            return "YouTube is rate-limiting requests from your network. Please try again later or provide cookies."
        if "network" in raw.lower() or "timed out" in raw.lower() or "connection" in raw.lower():
            return "Network connection issue. Please check your internet connection."

        cleaned = raw.replace("ERROR: [youtube]", "").replace("ERROR:", "").strip()
        return cleaned or "An unexpected error occurred while communicating with YouTube."

    # ----------------------------------------------------------------------
    # 6. Real Format Probing (No Fake Fallbacks)
    # ----------------------------------------------------------------------

    def get_available_resolutions(self, video_id_or_url: str) -> Tuple[List[str], Optional[str]]:
        """
        Probes the video for available video stream resolutions.
        Returns:
            (resolutions_list, None) on success
            ([], error_message) on failure

        CRITICAL: Never returns fake fallbacks like ['1080p', '720p'] when probing fails!
        """
        url = video_id_or_url if video_id_or_url.startswith("http") else f"https://www.youtube.com/watch?v={video_id_or_url}"
        video_id = video_id_or_url if not video_id_or_url.startswith("http") else video_id_or_url.split("v=")[-1].split("&")[0]

        if url in self._resolution_cache:
            return (self._resolution_cache[url], None)

        ydl_opts = self.get_base_ydl_options(purpose="probe")
        ydl_opts.update({
            "skip_download": True,
            "socket_timeout": 10,
        })

        provider_name, po_gen, po_att = self.get_po_token_info()
        logger.info("[YouTube] Probing formats for %s", video_id)
        logger.info("[YouTube] Authentication method: %s", "Cookie File" if self.is_cookies_available() else "Guest")
        logger.info("[YouTube] Player client: %s", ",".join(self.get_player_clients()))
        logger.info("[YouTube] PO Token provider: %s", provider_name)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    logger.warning("[YouTube] Format probe returned no info for %s", video_id)
                    return ([], "No metadata received from YouTube.")

                formats = info.get("formats", [])
                logger.info("[YouTube] Formats found: %d", len(formats))

                heights = set()
                for f in formats:
                    h = f.get("height")
                    vcodec = f.get("vcodec")
                    if h and vcodec and vcodec != "none":
                        heights.add(int(h))

                if not heights:
                    logger.warning("[YouTube] No video streams with height found for %s", video_id)
                    return ([], "No video formats available for this video.")

                sorted_heights = sorted(heights, reverse=True)
                labels = ["Best (Auto)"]
                for h in sorted_heights:
                    if h >= 2160:
                        labels.append(f"{h}p (4K)")
                    elif h >= 1440:
                        labels.append(f"{h}p (2K)")
                    elif h >= 1080:
                        labels.append(f"{h}p (FHD)")
                    elif h >= 720:
                        labels.append(f"{h}p (HD)")
                    elif h >= 480:
                        labels.append(f"{h}p (SD)")
                    elif h >= 144:
                        labels.append(f"{h}p")

                # Deduplicate while preserving order
                seen = set()
                unique_labels = []
                for lbl in labels:
                    if lbl not in seen:
                        seen.add(lbl)
                        unique_labels.append(lbl)

                self._resolution_cache[url] = unique_labels
                return (unique_labels, None)

        except Exception as err:
            classified_err = self.classify_error(err)
            sanitized_log = str(err).split("\n")[0]
            logger.warning("[YouTube] Format probe failed for %s: %s", video_id, sanitized_log)
            return ([], classified_err)

    # ----------------------------------------------------------------------
    # 7. Diagnostics Mode (Section 9)
    # ----------------------------------------------------------------------

    def diagnose_video(self, video_id_or_url: str) -> str:
        """
        Executes an end-to-end diagnostic trace on a YouTube URL and generates
        the exact formatted diagnostic report requested in Section 9.
        Guarantees zero leakage of cookies, tokens, authorization codes, or passwords.
        """
        url = video_id_or_url if video_id_or_url.startswith("http") else f"https://www.youtube.com/watch?v={video_id_or_url}"
        video_id = video_id_or_url if not video_id_or_url.startswith("http") else video_id_or_url.split("v=")[-1].split("&")[0]

        po_provider, po_gen, po_att = self.get_po_token_info()
        oauth_status = "CONNECTED" if self.is_google_oauth_connected() else "NOT CONNECTED"
        cookies_status = f"AVAILABLE ({Path(self.get_cookie_file_path()).name})" if self.is_cookies_available() else "NOT AVAILABLE"
        player_clients = ", ".join(self.get_player_clients())

        format_probe_status = "PENDING"
        formats_found_str = "0"
        playback_status = "PENDING"
        download_status = "PENDING"

        # 1. Test Format Probing
        resolutions, probe_err = self.get_available_resolutions(url)
        if resolutions:
            format_probe_status = "SUCCESS"
            formats_found_str = f"{len(resolutions)} resolutions ({', '.join(resolutions[:4])}...)"
        else:
            format_probe_status = "FAILED"
            formats_found_str = f"FAILED: {probe_err}"

        # 2. Test Playback Media Extraction Capability
        ydl_opts_play = self.get_base_ydl_options(purpose="playback")
        ydl_opts_play.update({
            "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best",
            "skip_download": True,
        })
        try:
            with yt_dlp.YoutubeDL(ydl_opts_play) as ydl:
                info = ydl.extract_info(url, download=False)
                if info and info.get("formats"):
                    playback_status = "SUCCESS"
                else:
                    playback_status = "FAILED (No formats)"
        except Exception as e:
            playback_status = f"FAILED ({self.classify_error(e)})"

        # 3. Test Download Extraction Capability
        ydl_opts_dl = self.get_base_ydl_options(purpose="download")
        ydl_opts_dl.update({
            "format": "bestaudio/best",
            "skip_download": True,
        })
        try:
            with yt_dlp.YoutubeDL(ydl_opts_dl) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    download_status = "SUCCESS"
                else:
                    download_status = "FAILED (No info)"
        except Exception as e:
            download_status = f"FAILED ({self.classify_error(e)})"

        # Format exact output as requested in Section 9
        report = (
            "YouTube Diagnostics\n"
            "──────────────────────────────\n\n"
            f"yt-dlp version: {self.ytdlp_version}\n"
            f"Video ID: {video_id}\n\n"
            "Authentication:\n"
            f"  Google OAuth: {oauth_status}\n"
            f"  yt-dlp cookies: {cookies_status}\n\n"
            "Player client:\n"
            f"  {player_clients}\n\n"
            "PO Token provider:\n"
            f"  {po_provider}\n\n"
            "PO Token generated:\n"
            f"  {'YES' if po_gen else 'NO'}\n\n"
            "PO Token attached:\n"
            f"  {'YES' if po_att else 'NO'}\n\n"
            "Format probe:\n"
            f"  {format_probe_status}\n\n"
            "Formats found:\n"
            f"  {formats_found_str}\n\n"
            "Playback extraction:\n"
            f"  {playback_status}\n\n"
            "Download extraction:\n"
            f"  {download_status}\n"
        )
        return report

    # ----------------------------------------------------------------------
    # 8. Unified Playback Media Preparation
    # ----------------------------------------------------------------------

    def prepare_playback_stream(
        self,
        result: SearchResult,
        on_ready: Callable[[str, int], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        """
        Prepares video media for playback using the unified extraction layer.
        Checks pre-existing downloads, cache, or buffers fast stream via yt-dlp.
        """
        cache_dir = Path.home() / ".vyntra" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{result.video_id}.mp4"

        # Check existing downloads
        download_dir = Path(config_manager.config.download_directory)
        if download_dir.exists():
            safe_title = sanitize_filename(result.display_title)
            for ext in (".mp4", ".m4v", ".mkv"):
                exact_path = download_dir / f"{safe_title}{ext}"
                if exact_path.is_file() and exact_path.stat().st_size > 100000:
                    on_ready(str(exact_path), result.duration_seconds or 0)
                    return

        # Check existing cache
        if cache_file.is_file() and cache_file.stat().st_size > 100000:
            on_ready(str(cache_file), result.duration_seconds or 0)
            return

        import threading

        def _worker():
            try:
                url = result.url if (result.url and result.url.startswith("http")) else f"https://www.youtube.com/watch?v={result.video_id}"
                outtmpl = str(cache_dir / f"{result.video_id}.%(ext)s")

                ydl_opts = self.get_base_ydl_options(purpose="playback")
                ydl_opts.update({
                    "outtmpl": outtmpl,
                    "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=720]/best",
                    "merge_output_format": "mp4",
                    "retries": 5,
                    "socket_timeout": 15,
                })

                ffmpeg_status = ffmpeg_service.get_status()
                if ffmpeg_status.ffmpeg_path:
                    ydl_opts["ffmpeg_location"] = str(Path(ffmpeg_status.ffmpeg_path).parent)

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    duration = int(info.get("duration") or result.duration_seconds or 0)

                final_path = None
                if cache_file.is_file():
                    final_path = str(cache_file)
                else:
                    candidates = list(cache_dir.glob(f"{result.video_id}.*"))
                    if candidates:
                        final_path = str(candidates[0])

                if not final_path or not Path(final_path).is_file():
                    raise RuntimeError("Prepared media file could not be verified on disk.")

                on_ready(final_path, duration)
            except Exception as err:
                on_error(err)

        threading.Thread(target=_worker, daemon=True).start()

    # ----------------------------------------------------------------------
    # 9. Unified Download Options Construction
    # ----------------------------------------------------------------------

    def build_download_options(self, task: DownloadTask, out_base_without_ext: str) -> Dict[str, Any]:
        """
        Constructs yt-dlp download options configured for media format,
        bitrate/resolution, metadata, and the unified extraction engine.
        """
        ffmpeg_status = ffmpeg_service.get_status()
        ffmpeg_bin_dir = str(Path(ffmpeg_status.ffmpeg_path).parent) if ffmpeg_status.ffmpeg_path else None

        ydl_opts = self.get_base_ydl_options(purpose="download")
        ydl_opts.update({
            "outtmpl": f"{out_base_without_ext}.%(ext)s",
            "retries": 5,
            "fragment_retries": 5,
        })

        if ffmpeg_bin_dir:
            ydl_opts["ffmpeg_location"] = ffmpeg_bin_dir

        if task.format == MediaFormat.MP3:
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
                ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
        else:
            raw_q = str(getattr(task, "selected_quality", "") or getattr(task.video_quality, "value", "best")).lower()
            height_match = re.search(r"(\d{3,4})", raw_q)
            target_height = int(height_match.group(1)) if height_match else None

            if ffmpeg_status.is_available:
                if target_height:
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
                if target_height:
                    ydl_opts["format"] = f"best[height<={target_height}][ext=mp4]/best[height<={target_height}]/best"
                else:
                    ydl_opts["format"] = "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"

        return ydl_opts


# Global singleton instance
youtube_service = YouTubeService()
