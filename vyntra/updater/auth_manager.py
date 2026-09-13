"""
Secure authentication and OS Keyring credential management for Vyntra updater.
Stores user-authorized, read-only GitHub tokens in the host operating system's
secure keychain (Windows Credential Manager / macOS Keychain) to enable private
repository release checks and asset downloads without embedding master secrets.
"""

import os
from typing import Dict, Optional, Tuple
try:
    import keyring
except ImportError:
    keyring = None  # type: ignore
import requests

from vyntra.updater.constants import (
    GITHUB_OWNER,
    GITHUB_REPO,
    NETWORK_CONNECT_TIMEOUT,
    NETWORK_READ_TIMEOUT,
    USER_AGENT_TEMPLATE,
)
from vyntra.utils.logger import logger


KEYRING_SERVICE_NAME = "Vyntra_GitHub_Update_Auth"
KEYRING_USERNAME = "update_access_token"
ENV_TOKEN_VAR = "VYNTRA_UPDATE_TOKEN"


class UpdaterAuthManager:
    """Manages secure persistence and verification of update credentials."""

    def __init__(self):
        self._cached_token: Optional[str] = None

    def get_token(self) -> Optional[str]:
        """
        Retrieves the configured update token.
        Priority:
        1. Environment variables (VYNTRA_UPDATE_TOKEN, GITHUB_TOKEN, GH_TOKEN)
        2. In-memory cached token
        3. Secure OS Keyring (Windows Credential Manager / macOS Keychain)
        4. Host Git Credential Manager (git credential fill for host=github.com)
        """
        # 1. Check environment variable overrides
        for env_var in (ENV_TOKEN_VAR, "GITHUB_TOKEN", "GH_TOKEN"):
            env_token = os.environ.get(env_var, "").strip()
            if env_token:
                return env_token

        # 2. Check cached in-memory token
        if self._cached_token:
            return self._cached_token

        # 3. Retrieve from secure OS Keyring
        try:
            if keyring:
                token = keyring.get_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME)
                if token:
                    self._cached_token = token.strip()
                    return self._cached_token
            # If keyring not available or token not found, continue
        except Exception as e:
            logger.debug("[UpdaterAuth] Could not read token from keyring: %s", e)

        # 4. Host Git Credential Manager (active outside pytest unit tests)
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            git_token = self._get_token_from_git_credentials()
            if git_token:
                self._cached_token = git_token
                try:
                    keyring.set_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME, git_token)
                except Exception:
                    pass
                return git_token

        return None

    def _get_token_from_git_credentials(self) -> Optional[str]:
        """Queries host git credential helper for github.com token."""
        try:
            import subprocess
            proc = subprocess.run(
                ["git", "credential", "fill"],
                input="protocol=https\nhost=github.com\n",
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                for line in proc.stdout.splitlines():
                    if line.startswith("password="):
                        val = line.split("=", 1)[1].strip()
                        if val and (val.startswith("ghp_") or val.startswith("gho_") or val.startswith("github_pat_") or len(val) >= 20):
                            return val
        except Exception as e:
            logger.debug("[UpdaterAuth] Git credential lookup error: %s", e)
        return None

    def set_token(self, token: str) -> bool:
        """
        Persists update access token in secure OS Keyring.
        Returns True on success, False otherwise.
        """
        clean_token = token.strip() if token else ""
        if not clean_token:
            return self.delete_token()

        try:
            keyring.set_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME, clean_token)
            self._cached_token = clean_token
            logger.info("[UpdaterAuth] Update access token saved to OS Keyring successfully.")
            return True
        except Exception as e:
            logger.error("[UpdaterAuth] Failed to store token in OS Keyring: %s", e)
            self._cached_token = clean_token  # Keep in memory as fallback for current session
            return False

    def delete_token(self) -> bool:
        """Removes the update access token from OS Keyring and memory."""
        self._cached_token = None
        try:
            keyring.delete_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME)
            logger.info("[UpdaterAuth] Update access token removed from OS Keyring.")
            return True
        except Exception as e:
            logger.debug("[UpdaterAuth] Keyring delete note (token may already be cleared): %s", e)
            return True

    def is_configured(self) -> bool:
        """Returns True if an update token is available in Keyring or environment."""
        return bool(self.get_token())

    def verify_token_with_github(
        self,
        token: str,
        owner: str = GITHUB_OWNER,
        repo: str = GITHUB_REPO,
    ) -> Tuple[bool, str, Dict]:
        """
        Validates token directly against GitHub API for the target private repository.
        Returns (is_valid, message, permissions_dict).
        """
        if not token or not token.strip():
            return False, "Token cannot be empty.", {}

        url = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {
            "Authorization": f"Bearer {token.strip()}",
            "User-Agent": USER_AGENT_TEMPLATE.format(version="1.1.3"),
            "Accept": "application/vnd.github.v3+json",
        }

        try:
            resp = requests.get(
                url,
                headers=headers,
                timeout=(NETWORK_CONNECT_TIMEOUT, NETWORK_READ_TIMEOUT),
            )

            if resp.status_code == 200:
                data = resp.json()
                permissions = data.get("permissions", {})
                can_read = permissions.get("pull", False) or permissions.get("read", True)
                if can_read:
                    return True, "Update authorization verified! Read access confirmed.", permissions
                else:
                    return False, "Token connected, but lacks read permission on this repository.", permissions

            elif resp.status_code == 401:
                return False, "GitHub authentication failed: Token is invalid or has expired.", {}

            elif resp.status_code == 404:
                return False, f"Repository '{owner}/{repo}' not found or token lacks access.", {}

            elif resp.status_code == 403:
                return False, "GitHub API rate limit exceeded or access forbidden for this token.", {}

            else:
                return False, f"GitHub returned HTTP {resp.status_code}: {resp.text[:120]}", {}

        except requests.exceptions.Timeout:
            return False, "Connection to GitHub timed out. Please check your internet connection.", {}
        except requests.exceptions.ConnectionError:
            return False, "Network unavailable. Could not connect to api.github.com.", {}
        except Exception as e:
            return False, f"Verification failed: {e}", {}


# Global instance
updater_auth_manager = UpdaterAuthManager()
