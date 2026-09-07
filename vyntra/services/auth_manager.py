"""
Native Desktop Google OAuth 2.0 and OS Keyring Authentication Manager for Vyntra (RFC 8252).
"""

import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import socket
import threading
import time
from typing import Callable, Dict, Optional, Tuple
import urllib.parse
import webbrowser
import keyring
import requests

from vyntra.config import config_manager
from vyntra.developer_config import load_developer_oauth_client, mask_client_id
from vyntra.utils.logger import logger

KEYRING_SERVICE_NAME = "Vyntra_YouTube_Auth"
KEYRING_USERNAME = "current_user_credentials"

# Google OAuth 2.0 Endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/youtube.readonly",
]


class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handles the loopback OAuth redirect from Google."""

    def log_message(self, format, *args):
        # Suppress default HTTP server stdout spam
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        self.server.query_params = params

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

        error = params.get("error", [None])[0]
        if error:
            html = f"""
            <!DOCTYPE html>
            <html>
            <head><title>Vyntra - Sign-In Cancelled</title></head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0B0E14; color: #FFFFFF; display: flex; align-items: center; justify-content: center; height: 90vh; margin: 0;">
                <div style="background: #151A23; border: 1px solid #FF5252; padding: 40px; border-radius: 16px; text-align: center; max-width: 440px;">
                    <div style="font-size: 48px; margin-bottom: 12px;">⚠️</div>
                    <h2 style="margin: 0 0 10px 0; color: #FF5252;">Sign-In Cancelled</h2>
                    <p style="color: #8C9BAE; font-size: 14px;">Google sign-in was cancelled ({error}). You can close this tab and return to Vyntra.</p>
                </div>
            </body>
            </html>
            """
        else:
            html = """
            <!DOCTYPE html>
            <html>
            <head><title>Vyntra - Connected</title></head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0B0E14; color: #FFFFFF; display: flex; align-items: center; justify-content: center; height: 90vh; margin: 0;">
                <div style="background: #151A23; border: 1px solid #22C55E; padding: 40px; border-radius: 16px; text-align: center; max-width: 440px;">
                    <div style="font-size: 48px; margin-bottom: 12px;">🎉</div>
                    <h2 style="margin: 0 0 10px 0; color: #22C55E;">Sign-In Successful!</h2>
                    <p style="color: #8C9BAE; font-size: 14px;">Your YouTube account is now connected to Vyntra. You can close this tab and return to the application.</p>
                </div>
            </body>
            </html>
            """
        self.wfile.write(html.encode("utf-8"))


class YouTubeAuthManager:
    """Manages Native Desktop OAuth 2.0 lifecycle, PKCE, token exchange, and OS Keyring persistence."""

    def __init__(self):
        self._current_tokens: Optional[Dict] = None
        self._user_profile: Optional[Dict] = None
        self._lock = threading.Lock()
        # Log diagnostic status on startup
        load_developer_oauth_client(verbose_log=True)
        self.load_credentials()

    def get_client_credentials(self) -> Tuple[str, str]:
        """
        Retrieves the Google Cloud Desktop OAuth Client credentials.
        """
        client_id, client_secret, _, _ = load_developer_oauth_client()
        return client_id, client_secret

    def has_valid_client_id(self) -> bool:
        """Checks if a genuine non-placeholder Google Client ID is configured."""
        cid, _ = self.get_client_credentials()
        return bool(cid and not cid.startswith("YOUR_GOOGLE_CLOUD") and ".apps.googleusercontent.com" in cid)

    def _generate_pkce(self) -> Tuple[str, str]:
        """Generates RFC 7636 PKCE code_verifier and code_challenge."""
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return verifier, challenge

    def start_login(self, on_complete: Callable[[bool, str, Optional[Dict]], None]) -> None:
        """
        Launches standard RFC 8252 native desktop OAuth flow on a local loopback server.
        """
        client_id, client_secret = self.get_client_credentials()

        if not self.has_valid_client_id():
            logger.warning("[OAuth] Google Cloud Desktop Client ID not configured.")
            on_complete(
                False,
                "Sign-in service is currently unavailable. Please try again later.",
                None,
            )
            return

        def _worker():
            try:
                server = http.server.HTTPServer(("127.0.0.1", 0), _OAuthCallbackHandler)
                server.query_params = {}
                port = server.server_address[1]
                redirect_uri = f"http://127.0.0.1:{port}/"

                verifier, challenge = self._generate_pkce()
                state = secrets.token_urlsafe(32)

                query = {
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "response_type": "code",
                    "scope": " ".join(SCOPES),
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "state": state,
                    "access_type": "offline",
                    "prompt": "consent",
                }
                auth_url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(query)}"

                # Log non-sensitive OAuth request parameters with masked client ID
                masked_client_id = mask_client_id(client_id)
                logger.info(
                    "[OAuth] Starting Authorization Request:\n"
                    "  • Client ID: %s\n"
                    "  • Redirect URI: %s\n"
                    "  • Response Type: code\n"
                    "  • Scope: %s\n"
                    "  • Access Type: offline\n"
                    "  • Prompt: consent\n"
                    "  • PKCE Method: S256",
                    masked_client_id,
                    redirect_uri,
                    " ".join(SCOPES),
                )

                webbrowser.open(auth_url)

                server.timeout = 120
                server.handle_request()
                params = getattr(server, "query_params", {})
                server.server_close()

                if not params:
                    on_complete(False, "Sign-in timed out. Please try again.", None)
                    return

                error = params.get("error", [None])[0]
                if error:
                    on_complete(False, f"Sign-in cancelled: {error}", None)
                    return

                received_state = params.get("state", [None])[0]
                if received_state != state:
                    on_complete(False, "Security validation failed. Please try again.", None)
                    return

                code = params.get("code", [None])[0]
                if not code:
                    on_complete(False, "Authorization code was not received.", None)
                    return

                success, msg, profile = self._exchange_code(code, verifier, redirect_uri, client_id, client_secret)
                on_complete(success, msg, profile)

            except Exception as err:
                logger.error("[OAuth] Loopback server error: %s", err)
                on_complete(False, f"Sign-in error: {err}", None)

        threading.Thread(target=_worker, daemon=True).start()

    def _exchange_code(
        self,
        code: str,
        verifier: str,
        redirect_uri: str,
        client_id: str,
        client_secret: str,
    ) -> Tuple[bool, str, Optional[Dict]]:
        """Exchanges authorization code for access and refresh tokens."""
        logger.info("[OAuth] Exchanging authorization code with %s...", GOOGLE_TOKEN_URL)
        token_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }

        try:
            resp = requests.post(GOOGLE_TOKEN_URL, data=token_data, timeout=15)
            if resp.status_code != 200:
                logger.error("[OAuth] Token exchange failed (%d): %s", resp.status_code, resp.text)
                return (False, "Google sign-in could not be completed. Please try again.", None)

            token_json = resp.json()
            access_token = token_json.get("access_token")
            refresh_token = token_json.get("refresh_token")
            expires_in = token_json.get("expires_in", 3600)
            expires_at = time.time() + expires_in

            user_profile = self._fetch_userinfo(access_token)

            stored_data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "profile": user_profile,
            }

            with self._lock:
                self._current_tokens = stored_data
                self._user_profile = user_profile
                self._save_to_keyring(stored_data)

            config_manager.update(auth_connected=True, auth_status="connected")
            email = user_profile.get("email", "Google User")
            logger.info("[OAuth] Login successful for: %s", email)
            return (True, f"✓ Signed in as {email}", user_profile)

        except Exception as err:
            logger.error("[OAuth] Network error during token exchange: %s", err)
            return (False, f"Network error during authentication: {err}", None)

    def _fetch_userinfo(self, access_token: str) -> Dict:
        """Fetches user profile (email, name, picture) using OAuth access token."""
        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            resp = requests.get(GOOGLE_USERINFO_URL, headers=headers, timeout=8)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning("[OAuth] Could not fetch user profile: %s", e)
        return {"email": "Connected Account", "name": "Google User"}

    def _save_to_keyring(self, token_data: Dict) -> None:
        """Saves encrypted credentials in OS Keyring."""
        try:
            payload = json.dumps(token_data)
            keyring.set_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME, payload)
            logger.info("[Keyring] Credentials securely saved to OS Keyring.")
        except Exception as e:
            logger.error("[Keyring] Failed to save credentials to OS Keyring: %s", e)

    def load_credentials(self) -> Optional[Dict]:
        """Loads and auto-refreshes credentials from OS Keyring on application launch."""
        try:
            stored = keyring.get_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME)
            if not stored:
                config_manager.update(auth_connected=False, auth_status="disconnected")
                return None

            data = json.loads(stored)
            with self._lock:
                self._current_tokens = data
                self._user_profile = data.get("profile", {})

            expires_at = data.get("expires_at", 0)
            if time.time() >= expires_at - 120:
                logger.info("[OAuth] Stored access token expired; auto-refreshing in background...")
                self.refresh_credentials()

            config_manager.update(auth_connected=True, auth_status="connected")
            logger.info("[Keyring] Loaded active credentials for: %s", self._user_profile.get("email", ""))
            return self._current_tokens

        except Exception as e:
            logger.warning("[Keyring] Could not load credentials: %s", e)
            return None

    def refresh_credentials(self) -> bool:
        """Refreshes expired access token using refresh_token."""
        with self._lock:
            if not self._current_tokens or not self._current_tokens.get("refresh_token"):
                return False
            refresh_token = self._current_tokens["refresh_token"]
            client_id = self._current_tokens.get("client_id")
            client_secret = self._current_tokens.get("client_secret", "")

        if not client_id:
            client_id, client_secret = self.get_client_credentials()

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            resp = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=12)
            if resp.status_code == 200:
                new_tokens = resp.json()
                with self._lock:
                    self._current_tokens["access_token"] = new_tokens["access_token"]
                    self._current_tokens["expires_at"] = time.time() + new_tokens.get("expires_in", 3600)
                    self._save_to_keyring(self._current_tokens)

                logger.info("[OAuth] Token refreshed successfully.")
                return True
            else:
                logger.warning("[OAuth] Session expired (%d). Re-authentication required.", resp.status_code)
                config_manager.update(auth_status="expired")
                return False
        except Exception as e:
            logger.error("[OAuth] Token refresh network error: %s", e)
            return False

    def is_authenticated(self) -> bool:
        """Returns True if valid non-expired credentials exist."""
        with self._lock:
            return bool(self._current_tokens and self._current_tokens.get("access_token"))

    def get_access_token(self) -> Optional[str]:
        """Returns the current valid access token, auto-refreshing if needed."""
        with self._lock:
            if not self._current_tokens:
                return None
            if time.time() >= self._current_tokens.get("expires_at", 0) - 60:
                pass
            else:
                return self._current_tokens.get("access_token")

        if self.refresh_credentials():
            with self._lock:
                return self._current_tokens.get("access_token") if self._current_tokens else None
        return None

    def get_user_profile(self) -> Optional[Dict]:
        """Returns user profile dictionary."""
        with self._lock:
            return self._user_profile

    def logout(self) -> None:
        """Wipes credentials from OS Keyring and clears in-memory state."""
        with self._lock:
            token = self._current_tokens.get("access_token") if self._current_tokens else None
            self._current_tokens = None
            self._user_profile = None

        if token:
            try:
                requests.post(GOOGLE_REVOKE_URL, params={"token": token}, timeout=5)
            except Exception:
                pass

        try:
            keyring.delete_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME)
            logger.info("[Keyring] Deleted credentials from OS Keyring.")
        except Exception as e:
            logger.debug("[Keyring] Note: %s", e)

        config_manager.update(auth_connected=False, auth_status="disconnected")

    def test_connection(self) -> Tuple[bool, str]:
        """
        Verifies active OAuth token against Google Identity and YouTube APIs.
        """
        token = self.get_access_token()
        if not token:
            return (False, "⚠️ Not signed in: Please sign in with your Google account.")

        try:
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get(GOOGLE_USERINFO_URL, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                email = data.get("email", "Google User")
                return (True, f"✓ Google Account Connected: {email}")
            elif resp.status_code == 401:
                if self.refresh_credentials():
                    return self.test_connection()
                return (False, "⚠️ Session Expired: Please click 'Sign In with Google' to reconnect.")
            else:
                return (False, f"Google API error ({resp.status_code})")
        except Exception as err:
            return (False, f"Network error during test: {err}")


# Global singleton instance
auth_manager = YouTubeAuthManager()
