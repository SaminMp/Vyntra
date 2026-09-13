"""
Integration test verifying platform switching across YouTube, Instagram, TikTok, and Spotify.
"""

from unittest.mock import MagicMock, patch
import unittest
import customtkinter as ctk

from vyntra.models import Platform
from vyntra.ui.app import VyntraApp
from vyntra.ui.pages import InstagramPage, SpotifyPage, TikTokPage, YouTubePage


class TestPlatformSwitching(unittest.TestCase):
    """Verifies that platform switching dynamically updates pages, titles, and controls."""

    def test_complete_platform_cycle(self):
        app = VyntraApp()
        try:
            # 1. Initial State: YouTube
            self.assertEqual(app._current_platform, "youtube")
            self.assertIn("YouTube", app.title())
            self.assertIsInstance(app._pages["youtube"], YouTubePage)
            self.assertTrue(bool(app._pages["youtube"].grid_info()))

            # 2. Switch to Instagram
            app._switch_platform("instagram")
            self.assertEqual(app._current_platform, "instagram")
            self.assertIn("Instagram", app.title())
            self.assertIsInstance(app._pages["instagram"], InstagramPage)
            self.assertFalse(bool(app._pages["youtube"].grid_info()))
            self.assertTrue(bool(app._pages["instagram"].grid_info()))

            # 3. Switch to TikTok
            app._switch_platform("tiktok")
            self.assertEqual(app._current_platform, "tiktok")
            self.assertIn("TikTok", app.title())
            self.assertIsInstance(app._pages["tiktok"], TikTokPage)
            self.assertFalse(bool(app._pages["instagram"].grid_info()))
            self.assertTrue(bool(app._pages["tiktok"].grid_info()))

            # 4. Switch to Spotify
            app._switch_platform("spotify")
            self.assertEqual(app._current_platform, "spotify")
            self.assertIn("Spotify", app.title())
            spotify_page = app._pages["spotify"]
            self.assertIsInstance(spotify_page, SpotifyPage)
            self.assertTrue(bool(spotify_page.grid_info()))
            # Verify Spotify page has NO MP4 controls
            self.assertFalse(hasattr(spotify_page, "dl_mp4_btn"))
            self.assertTrue(hasattr(spotify_page, "download_mp3_btn"))
            self.assertTrue(hasattr(spotify_page, "preview_btn"))
            self.assertTrue(hasattr(spotify_page, "quality_segmented"))

            # 5. Switch back to YouTube
            app._switch_platform("youtube")
            self.assertEqual(app._current_platform, "youtube")
            self.assertIn("YouTube", app.title())
            self.assertTrue(bool(app._pages["youtube"].grid_info()))

            # Verify Watch Later toggle works from any platform
            app._toggle_watch_later_view()
            self.assertTrue(app._is_watch_later_active)
            app._toggle_watch_later_view()
            self.assertFalse(app._is_watch_later_active)

        finally:
            app._on_app_close()


if __name__ == "__main__":
    unittest.main()
