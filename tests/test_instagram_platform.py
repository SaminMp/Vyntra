"""
Unit tests for Instagram platform integration in Vyntra.
"""

from unittest.mock import MagicMock, patch
import unittest

from vyntra.models import AudioQuality, DownloadTask, MediaFormat, MediaItem, Platform
from vyntra.platforms.instagram.service import instagram_platform
from vyntra.platforms.registry import platform_registry


class TestInstagramPlatform(unittest.TestCase):
    """Test suite for Instagram platform service and capabilities."""

    def test_platform_registration(self):
        svc = platform_registry.get("instagram")
        self.assertIsNotNone(svc)
        self.assertEqual(svc.platform_id, "instagram")
        self.assertEqual(svc.capabilities.display_name, "Instagram")

    def test_capabilities_declaration(self):
        caps = instagram_platform.capabilities
        self.assertFalse(caps.supports_search, "Instagram must not pretend to support keyword search")
        self.assertTrue(caps.supports_url_input)
        self.assertTrue(caps.supports_video_playback)
        self.assertTrue(caps.supports_mp4)
        self.assertTrue(caps.supports_mp3)
        self.assertFalse(caps.supports_video_quality)

    def test_url_detection(self):
        valid_urls = [
            "https://www.instagram.com/reel/C7XyZ123456/",
            "https://instagram.com/p/B_123456789/",
            "https://www.instagram.com/tv/C987654321/",
            "http://instagr.am/reel/abcde123/",
        ]
        invalid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.tiktok.com/@user/video/123456789",
            "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
            "https://example.com",
            "",
        ]
        for url in valid_urls:
            self.assertTrue(instagram_platform.can_handle_url(url), f"Should handle valid IG URL: {url}")
        for url in invalid_urls:
            self.assertFalse(instagram_platform.can_handle_url(url), f"Should reject non-IG URL: {url}")

    def test_build_download_options_mp4(self):
        item = MediaItem(
            video_id="C7XyZ123456",
            title="Cool Reel",
            channel="@creator",
            url="https://www.instagram.com/reel/C7XyZ123456/",
            platform="instagram",
        )
        task = DownloadTask(
            result=item,
            format=MediaFormat.MP4,
            save_directory="D:/Downloads",
        )
        opts = instagram_platform.build_download_options(task, "D:/Downloads/Cool_Reel")
        self.assertIn("outtmpl", opts)
        self.assertIn("postprocessors", opts)
        has_video_convert = any(p.get("key") == "FFmpegVideoConvertor" for p in opts["postprocessors"])
        self.assertTrue(has_video_convert)

    def test_build_download_options_mp3(self):
        item = MediaItem(
            video_id="C7XyZ123456",
            title="Cool Reel",
            channel="@creator",
            url="https://www.instagram.com/reel/C7XyZ123456/",
            platform="instagram",
        )
        task = DownloadTask(
            result=item,
            format=MediaFormat.MP3,
            save_directory="D:/Downloads",
            audio_quality=AudioQuality.BEST,
        )
        opts = instagram_platform.build_download_options(task, "D:/Downloads/Cool_Reel")
        has_audio_extract = any(p.get("key") == "FFmpegExtractAudio" for p in opts["postprocessors"])
        self.assertTrue(has_audio_extract)

    @patch("yt_dlp.YoutubeDL")
    def test_extract_from_url_mock(self, mock_ydl_cls):
        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {
            "id": "C7XyZ123456",
            "title": "Amazing scenic view in Norway",
            "uploader": "travel_photographer",
            "duration": 45,
            "thumbnail": "https://instagram.fcdn.net/thumb.jpg",
            "url": "https://instagram.fcdn.net/video.mp4",
        }
        mock_ydl_cls.return_value.__enter__.return_value = mock_instance

        item = instagram_platform.extract_from_url("https://www.instagram.com/reel/C7XyZ123456/")
        self.assertIsNotNone(item)
        self.assertEqual(item.video_id, "C7XyZ123456")
        self.assertEqual(item.platform, "instagram")
        self.assertEqual(item.channel, "@travel_photographer")
        self.assertEqual(item.duration_seconds, 45)
        self.assertEqual(item.duration_formatted, "00:45")


if __name__ == "__main__":
    unittest.main()
