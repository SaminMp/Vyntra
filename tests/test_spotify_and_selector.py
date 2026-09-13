"""
Unit and integration tests for SpotifyPage lifecycle safety,
ImageService async fetching, and prominent PlatformSelector redesign.
"""

import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
import customtkinter as ctk

from vyntra.models import MediaItem, Platform
from vyntra.services.image_service import image_service
from vyntra.ui.app import VyntraApp
from vyntra.ui.components.platform_selector import PLATFORM_METADATA, PlatformSelector
from vyntra.ui.pages import InstagramPage, SpotifyPage, TikTokPage, YouTubePage


class TestSpotifyAndPlatformSelector(unittest.TestCase):
    """Tests Spotify lifecycle, artwork loading, and navigation bar visibility."""

    def test_image_service_get_image_async(self):
        """Verifies ImageService.get_image_async handles cache, success, and error gracefully."""
        # 1. Test empty URL error handling
        error_called = []
        image_service.get_image_async(
            "",
            on_success=lambda img: None,
            on_error=lambda err: error_called.append(err),
        )
        self.assertTrue(len(error_called) > 0)
        self.assertIsInstance(error_called[0], ValueError)

        # 2. Test cached image retrieval
        test_pil = Image.new("RGBA", (50, 50), color=(255, 0, 0, 255))
        image_service._cache["https://test.example/cached.png"] = test_pil
        success_img = []
        image_service.get_image_async(
            "https://test.example/cached.png",
            on_success=lambda img: success_img.append(img),
        )
        self.assertTrue(len(success_img) > 0)
        self.assertEqual(success_img[0].size, (50, 50))

    def test_platform_selector_metadata_and_buttons(self):
        """Verifies that all 4 platforms are represented in PlatformSelector with prominent buttons."""
        root = ctk.CTk()
        try:
            changed_platforms = []
            selector = PlatformSelector(
                root,
                current_platform="youtube",
                on_platform_changed=lambda p: changed_platforms.append(p),
            )
            self.assertEqual(selector.get_selected_platform(), "youtube")

            # Verify buttons exist for all 4 platforms
            for pid in ["youtube", "instagram", "tiktok", "spotify"]:
                self.assertIn(pid, selector._buttons)
                btn = selector._buttons[pid]
                self.assertTrue(btn.winfo_exists())

            # Test switching platform updates internal selection and triggers callback
            selector._select_platform("spotify")
            self.assertEqual(selector.get_selected_platform(), "spotify")
            self.assertEqual(changed_platforms, ["spotify"])

            # Verify active button styling has bold/accent formatting
            spotify_btn = selector._buttons["spotify"]
            self.assertIn("Spotify", spotify_btn.cget("text"))
            self.assertEqual(spotify_btn.cget("border_width"), 2)
            self.assertEqual(spotify_btn.cget("border_color"), PLATFORM_METADATA["spotify"].accent_color)
        finally:
            root.destroy()

    def test_spotify_page_placeholder_preservation_across_multiple_searches(self):
        """Verifies that clearing or displaying search results never destroys placeholder_label."""
        app = VyntraApp()
        try:
            app._switch_platform("spotify")
            spotify_page = app._pages["spotify"]
            self.assertTrue(spotify_page.placeholder_label.winfo_exists())

            mock_items = [
                MediaItem(
                    video_id="track1",
                    title="Get Lucky",
                    channel="Daft Punk",
                    album="Random Access Memories",
                    duration_seconds=248,
                    duration_formatted="4:08",
                    thumbnail_url="https://test.example/art.jpg",
                    url="https://open.spotify.com/track/track1",
                    platform="spotify",
                ),
                MediaItem(
                    video_id="track2",
                    title="Starboy",
                    channel="The Weeknd",
                    album="Starboy",
                    duration_seconds=230,
                    duration_formatted="3:50",
                    thumbnail_url="",
                    url="https://open.spotify.com/track/track2",
                    platform="spotify",
                ),
            ]

            # 1. First search display
            gen1 = spotify_page.next_generation()
            spotify_page._display_results(mock_items, gen1)
            self.assertEqual(len(spotify_page._cards), 2)
            # placeholder_label MUST still exist and not be destroyed
            self.assertTrue(spotify_page.placeholder_label.winfo_exists())

            # 2. Second search query simulation
            spotify_page.search_entry.delete(0, "end")
            spotify_page.search_entry.insert(0, "New Search Query")
            # Clear cards directly
            spotify_page._clear_cards()
            self.assertEqual(len(spotify_page._cards), 0)
            self.assertTrue(spotify_page.placeholder_label.winfo_exists())

            # 3. Third search returning empty results
            gen2 = spotify_page.next_generation()
            spotify_page._display_results([], gen2)
            self.assertTrue(spotify_page.placeholder_label.winfo_exists())
            self.assertIn("No tracks found", spotify_page.placeholder_label.cget("text"))
        finally:
            app.destroy()

    def test_rapid_platform_switching_stability(self):
        """Verifies that switching platforms rapidly does not cause TclErrors or state leaks."""
        app = VyntraApp()
        try:
            cycle = ["youtube", "spotify", "tiktok", "instagram", "spotify", "youtube", "tiktok"]
            for target in cycle:
                app._switch_platform(target)
                self.assertEqual(app._current_platform, target)
                self.assertTrue(app._pages[target].is_page_active)

            # Confirm final state is intact
            self.assertEqual(app.platform_selector.get_selected_platform(), "tiktok")
            self.assertTrue(bool(app._pages["tiktok"].grid_info()))
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
