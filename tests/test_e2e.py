"""
End-to-end verification and headless UI initialization test for Vyntra.
"""

import unittest
from vyntra.config import config_manager
from vyntra.models import MediaFormat, SearchResult
from vyntra.services.download_service import download_service
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.services.search_service import search_service
from vyntra.ui.app import VyntraApp


class TestVyntraE2E(unittest.TestCase):
    """End-to-End integration and smoke test."""

    def test_app_initialization_and_components(self):
        """Verify VyntraApp builds all component trees without errors."""
        app = VyntraApp()
        self.assertIsNotNone(app.search_bar)
        self.assertIsNotNone(app.results_list)
        self.assertIsNotNone(app.download_panel)
        self.assertIsNotNone(app.status_banner)

        # Test selecting a mock search result
        mock_result = SearchResult(
            video_id="dQw4w9WgXcQ",
            title="Rick Astley - Never Gonna Give You Up",
            channel="Rick Astley",
            duration_seconds=212,
            duration_formatted="03:32",
            views=1500000000,
            views_formatted="1.5B views",
            thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )

        from unittest.mock import patch
        with patch.object(search_service, "get_available_resolutions_async"):
            app._handle_result_selected(mock_result)
            self.assertEqual(app.download_panel.selected_result, mock_result)
            self.assertIn("Never Gonna Give You Up", app.download_panel.selected_title_label.cget("text"))

        # Close Tkinter instance cleanly
        app._on_app_close()


if __name__ == "__main__":
    unittest.main()
