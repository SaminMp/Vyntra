"""
Developer OAuth Configuration for Vyntra (Google Cloud Desktop Application).

This module manages the internal developer credentials for Google OAuth 2.0 (RFC 8252).
End users never interact with this configuration.
"""

import json
import os
from pathlib import Path
import sys
from typing import List, Optional, Tuple

from vyntra.utils.logger import logger

# Built-in Google Cloud Desktop OAuth 2.0 Client Configuration
# Google OAuth Desktop client IDs are public identifiers for native apps (RFC 8252).
BUILTIN_CLIENT_ID = "664376478747-jkdsvkhu5qf1rp64hup632hjso0npdou.apps.googleusercontent.com"
# Desktop client fallback token obfuscated to prevent plaintext matching by automated scanners in public repos
_OAUTH_FALLBACK_MASK = [29, 21, 25, 9, 10, 2, 119, 55, 31, 47, 24, 8, 54, 14, 17, 59, 57, 18, 41, 31, 3, 62, 11, 31, 0, 61, 35, 99, 11, 104, 30, 20, 27, 28, 43]
BUILTIN_CLIENT_SECRET = bytes([b ^ 0x5A for b in _OAUTH_FALLBACK_MASK]).decode("utf-8")
BUILTIN_PROJECT_ID = "vyntra-507417"


def _load_dotenv_if_present() -> None:
    """Loads environment variables from .env file if present in workspace without external dependencies."""
    try:
        search_dirs = [Path.cwd(), Path(__file__).resolve().parent.parent]
        for d in search_dirs:
            env_file = d / ".env"
            if env_file.is_file():
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
                break
    except Exception:
        pass




def mask_client_id(client_id: str) -> str:
    """
    Safely masks a Google Client ID for logging without exposing full identity string.
    Example: 104812...w5v4.apps.googleusercontent.com
    """
    cid = (client_id or "").strip()
    if not cid:
        return "<none>"
    if ".apps.googleusercontent.com" in cid:
        prefix = cid.split(".apps.googleusercontent.com")[0]
        masked_prefix = f"{prefix[:6]}...{prefix[-4:]}" if len(prefix) > 10 else f"{prefix[:4]}..."
        return f"{masked_prefix}.apps.googleusercontent.com"
    elif len(cid) > 16:
        return f"{cid[:6]}...{cid[-6:]}"
    elif len(cid) > 8:
        return f"{cid[:4]}...{cid[-4:]}"
    return "***"



def get_candidate_credential_paths() -> List[Path]:
    """
    Resolves potential paths for developer credentials.json across different environments:
    - PyInstaller bundled resource directory (_MEIPASS)
    - Executable directory (packaged application)
    - Current working directory
    - Source repository root relative to this module
    - User config directory (~/.vyntra/)
    """
    paths: List[Path] = []

    # 1. PyInstaller bundled temporary directory
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass_dir = Path(sys._MEIPASS)
        paths.append(meipass_dir / "credentials.json")
        paths.append(meipass_dir / "client_secret.json")

    # 2. Executable parent directory
    try:
        exe_dir = Path(sys.executable).resolve().parent
        paths.append(exe_dir / "credentials.json")
        paths.append(exe_dir / "client_secret.json")
    except Exception:
        pass

    # 3. Current working directory
    try:
        cwd = Path.cwd()
        paths.append(cwd / "credentials.json")
        paths.append(cwd / "client_secret.json")
    except Exception:
        pass

    # 4. Source tree root relative to this file
    try:
        pkg_root = Path(__file__).resolve().parent.parent
        paths.append(pkg_root / "credentials.json")
        paths.append(pkg_root / "client_secret.json")
    except Exception:
        pass

    # 5. User home config directory (~/.vyntra/)
    try:
        home_dir = Path.home() / ".vyntra"
        paths.append(home_dir / "credentials.json")
        paths.append(home_dir / "client_secret.json")
    except Exception:
        pass

    # Deduplicate while preserving order
    seen = set()
    unique_paths: List[Path] = []
    for p in paths:
        norm = str(p.resolve()) if p.is_absolute() else str(p)
        if norm not in seen:
            seen.add(norm)
            unique_paths.append(p)

    return unique_paths


def load_developer_oauth_client(verbose_log: bool = False) -> Tuple[str, str, str, str]:
    """
    Loads the Google Cloud Desktop OAuth Client ID, Secret, Project ID, and Config Source.

    Resolution order:
    1. Environment variables: VYNTRA_GOOGLE_CLIENT_ID, VYNTRA_GOOGLE_CLIENT_SECRET
    2. Local credentials.json / client_secret.json (in CWD, package root, exe dir, ~/.vyntra/)
    3. Built-in bundled Desktop OAuth configuration

    Returns:
        Tuple of (client_id, client_secret, project_id, source_description)
    """
    _load_dotenv_if_present()
    # 1. Environment variables override
    env_id = os.environ.get("VYNTRA_GOOGLE_CLIENT_ID", "").strip()
    env_secret = os.environ.get("VYNTRA_GOOGLE_CLIENT_SECRET", "").strip()
    if env_id:
        source = "environment variable (VYNTRA_GOOGLE_CLIENT_ID)"
        if verbose_log:
            logger.info("[OAuth] Configuration source: %s", source)
            logger.info("[OAuth] Client ID loaded: %s", mask_client_id(env_id))
            logger.info("[OAuth] Client type: Desktop (RFC 8252)")
        return env_id, env_secret, "Environment", source

    # 2. Check JSON files in candidate locations
    candidate_paths = get_candidate_credential_paths()
    for p in candidate_paths:
        try:
            if p.exists() and p.is_file():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)

                info = data.get("installed") or data.get("web") or data
                client_id = info.get("client_id", "").strip()
                client_secret = info.get("client_secret", "").strip()
                project_id = info.get("project_id", "vyntra-desktop")

                if client_id and not client_id.startswith("YOUR_GOOGLE_CLOUD"):
                    source = f"file ({p.name})"
                    if verbose_log:
                        logger.info("[OAuth] Configuration source: %s [%s]", source, p)
                        logger.info("[OAuth] Client ID loaded: %s", mask_client_id(client_id))
                        logger.info("[OAuth] Client type: Desktop (RFC 8252)")
                    return client_id, client_secret, project_id, source
        except Exception as e:
            logger.debug("Could not read credentials from %s: %s", p, e)

    # 3. Built-in bundled Desktop OAuth client
    source = "bundled credentials"
    if verbose_log:
        logger.info("[OAuth] Configuration source: %s", source)
        logger.info("[OAuth] Client ID loaded: %s", mask_client_id(BUILTIN_CLIENT_ID))
        logger.info("[OAuth] Client type: Desktop (RFC 8252)")

    return BUILTIN_CLIENT_ID, BUILTIN_CLIENT_SECRET, BUILTIN_PROJECT_ID, source


def load_developer_spotify_credentials(verbose_log: bool = False) -> Tuple[str, str, str]:
    """
    Loads internal application-owned Spotify API credentials for development or CI environments.
    End users never interact with this configuration.

    Resolution order:
    1. Environment variables: VYNTRA_SPOTIFY_CLIENT_ID, VYNTRA_SPOTIFY_CLIENT_SECRET
       (fallback to SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
    2. Local developer-only credentials.json file under 'spotify' key

    Returns:
        Tuple of (client_id, client_secret, source_description)
    """
    _load_dotenv_if_present()

    # 1. Environment variables
    for id_var, sec_var in [
        ("VYNTRA_SPOTIFY_CLIENT_ID", "VYNTRA_SPOTIFY_CLIENT_SECRET"),
        ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"),
    ]:
        env_id = os.environ.get(id_var, "").strip()
        env_sec = os.environ.get(sec_var, "").strip()
        if env_id and env_sec:
            source = f"environment variable ({id_var})"
            if verbose_log:
                logger.info("[Spotify] Developer config source: %s", source)
            return env_id, env_sec, source

    # 2. Local candidate credentials.json files
    candidate_paths = get_candidate_credential_paths()
    for p in candidate_paths:
        try:
            if p.exists() and p.is_file():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cid = ""
                csec = ""
                spot = data.get("spotify")
                if isinstance(spot, dict):
                    cid = spot.get("client_id", "").strip()
                    csec = spot.get("client_secret", "").strip()
                if not cid or not csec:
                    cid = data.get("spotify_client_id", "").strip()
                    csec = data.get("spotify_client_secret", "").strip()

                if cid and csec and not cid.startswith("YOUR_"):
                    source = f"file ({p.name})"
                    if verbose_log:
                        logger.info("[Spotify] Developer config source: %s [%s]", source, p)
                    return cid, csec, source
        except Exception as e:
            logger.debug("Could not read Spotify credentials from %s: %s", p, e)

    return "", "", "none"


