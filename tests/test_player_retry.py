"""
Unit tests for the Video Player Retry button and error recovery pipeline.
"""

import unittest
from unittest.mock import MagicMock, patch

from vyntra.models import SearchResult
from vyntra.services.youtube_service import YouTubeService, youtube_service
from vyntra.ui.theme import Theme
from vyntra.ui.views.player_modal import VideoPlayerModal


class TestYouTubeServiceClearFailedCache(unittest.TestCase):
    """Verifies that clear_failed_cache cleans up negative caches on user retry."""

    def setUp(self):
        self.service = YouTubeService()
        self.video_id = "failed_vid_999"
        self.url = f"https://www.youtube.com/watch?v={self.video_id}"

    def test_clear_failed_cache_specific_id(self):
        """Negative cache for a specific video is purged cleanly."""
        self.service._failed_cache[self.video_id] = (1000.0, RuntimeError("Extraction error"))
        self.service._resolution_cache[self.url] = []
        self.assertIn(self.video_id, self.service._failed_cache)

        self.service.clear_failed_cache(self.video_id)
        self.assertNotIn(self.video_id, self.service._failed_cache)
        self.assertNotIn(self.url, self.service._resolution_cache)

    def test_clear_failed_cache_all(self):
        """All negative failure caches and failed resolutions are purged when clearing without key."""
        self.service._failed_cache["vid1"] = (1000.0, RuntimeError("Err 1"))
        self.service._failed_cache["vid2"] = (1000.0, RuntimeError("Err 2"))
        self.service._resolution_cache["https://youtube.com/watch?v=vid1"] = []
        self.service._resolution_cache["https://youtube.com/watch?v=valid"] = ["1080p", "720p"]

        self.service.clear_failed_cache()
        self.assertEqual(len(self.service._failed_cache), 0)
        self.assertNotIn("https://youtube.com/watch?v=vid1", self.service._resolution_cache)
        self.assertIn("https://youtube.com/watch?v=valid", self.service._resolution_cache)


class TestVideoPlayerRetryButton(unittest.TestCase):
    """Verifies VideoPlayerModal status overlay and Retry button behavior."""

    def setUp(self):
        self.result = SearchResult(
            video_id="sample_retry_vid",
            title="Sample Video for Retry",
            channel="Test Channel",
            duration_seconds=180,
            duration_formatted="03:00",
            thumbnail_url="https://example.com/thumb.jpg",
            url="https://www.youtube.com/watch?v=sample_retry_vid",
        )

    def test_modal_show_error_displays_retry_button(self):
        """_show_error displays the error message and reveals the retry button."""
        modal = MagicMock(spec=VideoPlayerModal)
        modal.loading_label = MagicMock()
        modal.retry_btn = MagicMock()
        modal.status_frame = MagicMock()

        VideoPlayerModal._show_error(modal, "Connection timed out.")

        modal.loading_label.configure.assert_called_with(
            text="Connection timed out.", text_color=Theme.ERROR
        )
        modal.loading_label.grid.assert_called()
        modal.retry_btn.grid.assert_called_with(row=1, column=0)
        modal.retry_btn.lift.assert_called()
        modal.status_frame.grid.assert_called()
        modal.status_frame.lift.assert_called()

    def test_modal_show_loading_hides_retry_button(self):
        """_show_loading displays the loading indicator and hides the retry button."""
        modal = MagicMock(spec=VideoPlayerModal)
        modal.loading_label = MagicMock()
        modal.retry_btn = MagicMock()
        modal.status_frame = MagicMock()

        VideoPlayerModal._show_loading(modal, "Loading video...")

        modal.loading_label.configure.assert_called_with(
            text="Loading video...", text_color=Theme.TEXT_MUTED
        )
        modal.loading_label.grid.assert_called()
        modal.retry_btn.grid_remove.assert_called()
        modal.status_frame.grid.assert_called()
        modal.status_frame.lift.assert_called()

    def test_modal_hide_status(self):
        """_hide_status removes all loading/error elements once playback begins."""
        modal = MagicMock(spec=VideoPlayerModal)
        modal.loading_label = MagicMock()
        modal.retry_btn = MagicMock()
        modal.status_frame = MagicMock()

        VideoPlayerModal._hide_status(modal)

        modal.retry_btn.grid_remove.assert_called()
        modal.loading_label.grid_remove.assert_called()
        modal.status_frame.grid_remove.assert_called()

    @patch.object(youtube_service, "clear_failed_cache")
    def test_modal_on_retry_clears_cache_and_reloads(self, mock_clear_cache):
        """_on_retry clears failure cache and calls load_video for the current item."""
        modal = MagicMock(spec=VideoPlayerModal)
        modal.result = self.result
        modal._is_closed = False
        modal.load_video = MagicMock()

        VideoPlayerModal._on_retry(modal)

        mock_clear_cache.assert_any_call("sample_retry_vid")
        modal.load_video.assert_called_once_with(self.result)

    def test_modal_on_retry_when_closed(self):
        """_on_retry does nothing if modal is closed."""
        modal = MagicMock(spec=VideoPlayerModal)
        modal.result = self.result
        modal._is_closed = True
        modal.load_video = MagicMock()

        VideoPlayerModal._on_retry(modal)

        modal.load_video.assert_not_called()


if __name__ == "__main__":
    unittest.main()
