"""
YouTube Authentication Service for Vyntra.

Coordinates Google OAuth 2.0 Native Desktop authentication, OS Keyring tokens,
and yt-dlp media extraction configuration.
"""

from typing import Callable, Optional, Tuple

from vyntra.config import config_manager
from vyntra.services.auth_manager import auth_manager
from vyntra.utils.logger import logger


class AuthService:
    """Facade for managing YouTube authentication across Vyntra UI and backend services."""

    def launch_google_signin(self, on_complete: Callable[[bool, str], None]) -> None:
        """
        Launches official Google OAuth 2.0 sign-in via system browser and local loopback server.
        """
        def _on_oauth_done(success: bool, msg: str, profile: Optional[dict]):
            if success:
                email = (profile or {}).get("email", "")
                label = f"✓ Connected ({email})" if email else "✓ YouTube account connected successfully!"
                on_complete(True, label)
            else:
                on_complete(False, msg)

        auth_manager.start_login(_on_oauth_done)

    def disconnect(self) -> None:
        """Logs out and deletes credentials from OS Keyring."""
        auth_manager.logout()

    def get_connection_status(self) -> Tuple[str, str, str]:
        """
        Returns (status_key, display_label, details_message).
        """
        if auth_manager.is_authenticated():
            profile = auth_manager.get_user_profile() or {}
            email = profile.get("email", "")
            name = profile.get("name", "")
            user_label = email or name or "Connected"
            return (
                "connected",
                f"● YouTube: {user_label}",
                f"Connected with verified Google / YouTube session for {user_label}",
            )
        elif config_manager.config.auth_status == "expired":
            return (
                "expired",
                "⚠️ YouTube: Session Expired",
                "Google authentication expired. Please reconnect your account.",
            )
        else:
            return (
                "disconnected",
                "○ YouTube: Guest",
                "Not signed in to Google / YouTube (Guest mode)",
            )

    def get_ydl_cookie_opts(self) -> dict:
        """
        Returns options for yt-dlp.
        """
        token = auth_manager.get_access_token()
        if token:
            # Pass OAuth authorization header where supported
            return {
                "http_headers": {
                    "Authorization": f"Bearer {token}",
                }
            }
        return {}

    def test_connection(self) -> Tuple[bool, str]:
        """
        Tests whether the current OAuth authentication session is valid with Google and YouTube.
        """
        return auth_manager.test_connection()

    def translate_error(self, err: Exception) -> str:
        """Translates raw exceptions into actionable human guidance."""
        raw = str(err).strip()

        if "Sign in to confirm you’re not a bot" in raw or "confirm you're not a bot" in raw:
            return (
                "YouTube requires sign-in verification. Click 'Sign In with Google' in Settings (⚙️) "
                "or the header account badge to connect your YouTube account."
            )
        if "Private video" in raw:
            return "This video is private or restricted and cannot be accessed."
        if "This video is unavailable" in raw or "Video unavailable" in raw:
            return "This video is unavailable or has been removed from YouTube."
        if "HTTP Error 429" in raw or "Too Many Requests" in raw:
            return "YouTube is rate-limiting requests. Please reconnect your YouTube account in Settings."
        if "network" in raw.lower() or "timed out" in raw.lower() or "connection" in raw.lower():
            return "Network connection issue. Please check your internet connection."

        return raw.replace("ERROR: [youtube]", "").strip()


# Global singleton instance
auth_service = AuthService()
