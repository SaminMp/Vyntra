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

    def __init__(self):
        self._listener_map = {}

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

    def add_auth_listener(self, listener: Callable[[], None]) -> None:
        """Registers a listener that is notified whenever authentication state changes."""
        if listener not in self._listener_map:
            def _wrapper(state, message):
                listener()
            self._listener_map[listener] = _wrapper
            auth_manager.add_state_listener(_wrapper)

    def remove_auth_listener(self, listener: Callable[[], None]) -> None:
        """Unregisters an authentication state listener."""
        wrapper = self._listener_map.pop(listener, None)
        if wrapper:
            auth_manager.remove_state_listener(wrapper)

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
                f"● Google: {user_label}",
                f"Signed in as {user_label} (Google Identity & Playlists)",
            )
        elif config_manager.config.auth_status == "expired":
            return (
                "expired",
                "⚠️ Google: Session Expired",
                "Google authentication expired. Please reconnect your account.",
            )
        else:
            return (
                "disconnected",
                "○ Google: Guest",
                "Not signed in to Google (Guest mode)",
            )

    def get_media_access_status(self) -> Tuple[str, str, str]:
        """
        Returns (status_key, display_label, details_message) for YouTube Media Session.
        Guarantees zero leakage of cookies or secrets.
        """
        from vyntra.services.youtube_service import youtube_service
        mode_label, detail_str = youtube_service.get_media_auth_summary()
        status = getattr(config_manager.config, "youtube_media_status", "unconfigured")

        if status == "ready":
            return ("ready", f"● Media Access: {mode_label} (Ready)", detail_str)
        elif status == "failed":
            msg = getattr(config_manager.config, "youtube_media_status_message", "Setup required")
            return ("failed", f"⚠️ Media Access: {mode_label} (Action Needed)", msg)
        else:
            return ("unconfigured", f"○ Media Access: {mode_label}", detail_str)

    def get_ydl_cookie_opts(self) -> dict:
        """
        Returns options for yt-dlp from the centralized extraction service.
        """
        from vyntra.services.youtube_service import youtube_service
        return youtube_service.get_base_ydl_options()

    def test_connection(self) -> Tuple[bool, str]:
        """
        Tests both Google Account OAuth Identity and YouTube Media Access extraction.
        Returns overall success and a clear multi-line report distinguishing both layers.
        """
        from vyntra.services.youtube_service import youtube_service

        # 1. Google OAuth Identity check
        if auth_manager.is_authenticated():
            google_ok, google_msg = auth_manager.test_connection()
        else:
            google_ok, google_msg = (False, "○ Google Account: Not connected (Optional)")

        # 2. YouTube Media Access check
        media_ok, media_msg = youtube_service.test_youtube_media_access()

        lines = [google_msg, media_msg]
        overall_ok = media_ok or (google_ok and media_ok)
        return (overall_ok, "\n".join(lines))

    def translate_error(self, err: Exception) -> str:
        """Translates raw exceptions into actionable human guidance via YouTubeService."""
        from vyntra.services.youtube_service import youtube_service
        return youtube_service.classify_error(err)


# Global singleton instance
auth_service = AuthService()
