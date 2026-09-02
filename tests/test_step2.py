"""
Unit and integration tests for Step 2 services: FFmpeg, Image, and Search.
"""

import unittest
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.services.image_service import image_service
from vyntra.services.search_service import search_service


class TestStep2(unittest.TestCase):
    """Test suite for Step 2 services."""

    def test_ffmpeg_detection(self):
        """Verify FFmpegService runs diagnostic check without crashing."""
        status = ffmpeg_service.get_status(force_refresh=True)
        self.assertIsNotNone(status.install_guide)
        self.assertIsInstance(status.install_guide, str)

    def test_image_placeholder(self):
        """Verify ImageService generates placeholder PIL image."""
        img = image_service.create_placeholder(160, 90)
        self.assertEqual(img.size, (160, 90))
        self.assertEqual(img.mode, "RGBA")

    def test_youtube_url_detection(self):
        """Verify search service distinguishes between URLs and text queries."""
        # URLs
        self.assertTrue(search_service.is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(search_service.is_youtube_url("http://youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(search_service.is_youtube_url("https://youtu.be/dQw4w9WgXcQ"))
        self.assertTrue(search_service.is_youtube_url("https://www.youtube.com/shorts/3jZp4E7n_8c"))

        # Free text queries
        self.assertFalse(search_service.is_youtube_url("lofi music for studying"))
        self.assertFalse(search_service.is_youtube_url("Alan Walker Faded"))
        self.assertFalse(search_service.is_youtube_url("آهنگ آرامش بخش"))

    def test_live_search_query(self):
        """Verify yt-dlp search query returns results."""
        results = search_service.search("Alan Walker Faded", max_results=2)
        self.assertGreaterEqual(len(results), 1)
        first = results[0]
        self.assertTrue(len(first.video_id) > 0)
        self.assertTrue(len(first.title) > 0)
        self.assertTrue(len(first.url) > 0)


if __name__ == "__main__":
    unittest.main()
