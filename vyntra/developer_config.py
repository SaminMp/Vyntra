"""
Developer OAuth Configuration for Vyntra (Google Cloud Desktop Application).

This module manages the internal developer credentials for Google OAuth 2.0.
End users never interact with this configuration.
"""

import json
import os
from pathlib import Path
from typing import Optional, Tuple

from vyntra.utils.logger import logger

# Developer Credentials File Paths
DEV_CREDENTIALS_PATHS = [
    Path(__file__).parent.parent / "credentials.json",
    Path(__file__).parent.parent / "client_secret.json",
    Path.home() / ".vyntra" / "credentials.json",
    Path.home() / ".vyntra" / "client_secret.json",
]


def load_developer_oauth_client() -> Tuple[str, str, str]:
    """
    Loads the Google Cloud Desktop OAuth Client ID and Secret.

    Resolution order:
    1. Environment variables: VYNTRA_GOOGLE_CLIENT_ID, VYNTRA_GOOGLE_CLIENT_SECRET
    2. Local credentials.json / client_secret.json in project root
    3. User config directory (~/.vyntra/credentials.json)
    4. Fallback default

    Returns:
        Tuple of (client_id, client_secret, project_id)
    """
    # 1. Environment variables
    env_id = os.environ.get("VYNTRA_GOOGLE_CLIENT_ID", "").strip()
    env_secret = os.environ.get("VYNTRA_GOOGLE_CLIENT_SECRET", "").strip()
    if env_id:
        return env_id, env_secret, "Environment"

    # 2. Check JSON files in project root & ~/.vyntra/
    for p in DEV_CREDENTIALS_PATHS:
        if p.exists() and p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)

                info = data.get("installed") or data.get("web") or data
                client_id = info.get("client_id", "").strip()
                client_secret = info.get("client_secret", "").strip()
                project_id = info.get("project_id", "Google Cloud Project")

                if client_id:
                    logger.debug("Loaded developer OAuth client from: %s", p)
                    return client_id, client_secret, project_id
            except Exception as e:
                logger.warning("Could not read developer credentials from %s: %s", p, e)

    # 3. Fallback placeholder
    return "", "", "Unconfigured"
