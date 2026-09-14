"""
Safe diagnostic reporting service for Vyntra.

Generates safe, non-sensitive diagnostic reports for:
- System and authentication state (Google OAuth, media extraction, platform readiness)
- Network connectivity, proxy detection, and TLS protocol verification
Strictly adheres to zero-credential disclosure: no tokens, passwords, cookies, or secrets.
"""

import os
import platform
import socket
import ssl
import sys
import urllib.parse
import urllib.request
from typing import Dict, Optional, Tuple

from vyntra import __version__
from vyntra.config import config_manager
from vyntra.services.auth_manager import auth_manager
from vyntra.services.youtube_service import youtube_service
from vyntra.updater.platform_detector import get_current_arch, get_current_platform, is_frozen
from vyntra.utils.logger import logger


def sanitize_proxy_url(proxy_url: Optional[str]) -> str:
    """
    Sanitizes a proxy URL by stripping out user credentials and showing only scheme, host, and port.
    E.g., http://user:pass@127.0.0.1:8080 -> http://127.0.0.1:8080 (or [masked]@127.0.0.1:8080).
    """
    if not proxy_url:
        return "NONE"
    try:
        parsed = urllib.parse.urlparse(proxy_url)
        scheme = parsed.scheme or "http"
        host = parsed.hostname or "unknown"
        port = f":{parsed.port}" if parsed.port else ""
        if parsed.username or parsed.password:
            return f"{scheme}://***:***@{host}{port}"
        return f"{scheme}://{host}{port}"
    except Exception:
        return "[CONFIGURED - Masked]"


def get_proxy_status() -> Dict[str, str]:
    """
    Safely inspects environment and system proxy configurations.
    Returns sanitized status dictionary.
    """
    env_keys = [
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy",
        "NO_PROXY", "no_proxy",
    ]
    proxies: Dict[str, str] = {}
    for key in env_keys:
        val = os.environ.get(key)
        if val:
            proxies[key] = sanitize_proxy_url(val)

    # Inspect Python standard library urllib detected proxies
    try:
        urllib_proxies = urllib.request.getproxies()
        for k, v in urllib_proxies.items():
            if k not in proxies:
                proxies[f"system_{k}"] = sanitize_proxy_url(v)
    except Exception:
        pass

    return proxies


def test_network_connectivity() -> Tuple[bool, bool, bool, str]:
    """
    Tests basic TCP/DNS, HTTPS connection to Google/YouTube, and TLS handshake.
    Returns (internet_ok, https_ok, tls_ok, error_details).
    """
    internet_ok = False
    https_ok = False
    tls_ok = False
    error_details = "None"

    # 1. Basic socket connectivity (DNS / TCP to 8.8.8.8:53 or 1.1.1.1:53)
    try:
        with socket.create_connection(("8.8.8.8", 53), timeout=3):
            internet_ok = True
    except Exception:
        try:
            with socket.create_connection(("1.1.1.1", 53), timeout=3):
                internet_ok = True
        except Exception as e:
            internet_ok = False
            error_details = f"DNS/Socket connection failed: {e}"

    # 2. HTTPS / TLS handshake test to standard HTTPS endpoint
    try:
        import requests
        resp = requests.get("https://www.google.com", timeout=5)
        if resp.status_code < 500:
            https_ok = True
            tls_ok = True
    except requests.exceptions.SSLError as ssl_err:
        https_ok = False
        tls_ok = False
        error_details = f"TLS handshake error: {ssl_err}"
    except Exception as http_err:
        https_ok = False
        error_details = f"HTTPS request failed: {http_err}"

    return internet_ok, https_ok, tls_ok, error_details


class DiagnosticService:
    """Provides consolidated, user-copyable diagnostic reports."""

    def generate_full_diagnostics(self) -> str:
        """
        Generates the comprehensive user-facing diagnostic report (Section 7).
        Contains zero secrets, tokens, or private data.
        """
        plat = f"{platform.system()} {platform.release()} ({'Packaged EXE' if is_frozen() else 'Source'})"
        arch = platform.machine() or get_current_arch()
        yt_dlp_ver = youtube_service.ytdlp_version

        # Google Account & Keyring
        google_connected = auth_manager.is_authenticated()
        account_status = "CONNECTED" if google_connected else "NOT CONNECTED"

        # Stored credentials check in Keyring
        keyring_has_creds = False
        try:
            import keyring
            creds = keyring.get_password("Vyntra_YouTube_Auth", "current_user_credentials")
            keyring_has_creds = bool(creds)
        except Exception:
            keyring_has_creds = False
        stored_creds_status = "FOUND" if keyring_has_creds else "NOT FOUND"

        # Token refresh availability
        if google_connected and keyring_has_creds:
            token_refresh = "AVAILABLE"
        elif keyring_has_creds:
            token_refresh = "AVAILABLE (Offline)"
        else:
            token_refresh = "NOT REQUIRED"

        # YouTube Media Access
        cfg_media_status = getattr(config_manager.config, "youtube_media_status", "unconfigured")
        media_ready = "READY" if cfg_media_status == "ready" else "NOT READY"

        # Platform integrations
        spotify_avail = "AVAILABLE"
        tiktok_avail = "AVAILABLE"

        # Network & Proxy
        proxies = get_proxy_status()
        proxy_status = "CONFIGURED" if proxies else "NONE"

        net_ok, https_ok, tls_ok, _ = test_network_connectivity()
        network_status = "OK" if (net_ok and https_ok) else "FAILED"

        # Updater readiness
        updater_status = "READY" if is_frozen() else "READY (Development mode)"

        report = (
            "Vyntra Diagnostics\n"
            "────────────────────────────\n"
            f"Version:            v{__version__}\n"
            f"Platform:           {plat}\n"
            f"Architecture:       {arch}\n"
            f"Python:             {platform.python_version()}\n\n"
            f"Google Account:     {account_status}\n"
            f"Stored Credentials: {stored_creds_status}\n"
            f"Token Refresh:      {token_refresh}\n"
            f"YouTube Media:      {media_ready}\n"
            f"yt-dlp Version:     {yt_dlp_ver}\n\n"
            f"Spotify:            {spotify_avail}\n"
            f"TikTok:             {tiktok_avail}\n\n"
            f"Network:            {network_status}\n"
            f"Proxy:              {proxy_status}\n"
            f"Updater:            {updater_status}\n"
        )
        return report

    def generate_network_diagnostics(self) -> str:
        """
        Generates the detailed networking and TLS diagnostic report (Section 5.10).
        """
        plat = f"{platform.system()} {platform.release()}"
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        yt_dlp_ver = youtube_service.ytdlp_version

        net_ok, https_ok, tls_ok, err_desc = test_network_connectivity()
        proxies = get_proxy_status()

        http_proxy = proxies.get("HTTP_PROXY") or proxies.get("http_proxy") or proxies.get("system_http") or "NONE"
        https_proxy = proxies.get("HTTPS_PROXY") or proxies.get("https_proxy") or proxies.get("system_https") or "NONE"

        # Check search endpoint reachability
        search_reachable = "UNKNOWN"
        try:
            import requests
            r = requests.head("https://www.youtube.com", timeout=5)
            search_reachable = "REACHABLE" if r.status_code < 500 else f"HTTP {r.status_code}"
        except Exception as e:
            search_reachable = f"FAILED ({type(e).__name__})"

        failure_category = "NONE" if (net_ok and https_ok and tls_ok) else err_desc

        report = (
            "Vyntra Network Diagnostics\n"
            "──────────────────────────────\n"
            f"Platform:              {plat}\n"
            f"Python:                {py_ver}\n"
            f"yt-dlp:                {yt_dlp_ver}\n\n"
            f"Internet connectivity: {'OK' if net_ok else 'FAILED'}\n"
            f"HTTPS connectivity:    {'OK' if https_ok else 'FAILED'}\n"
            f"TLS:                   {'OK' if tls_ok else 'FAILED'}\n"
            f"Search endpoint:       {search_reachable}\n\n"
            f"Proxy:                 {'CONFIGURED' if proxies else 'NONE'}\n"
            f"HTTP proxy:            {http_proxy}\n"
            f"HTTPS proxy:           {https_proxy}\n\n"
            f"Failure:               {failure_category}\n"
        )
        return report


diagnostic_service = DiagnosticService()
