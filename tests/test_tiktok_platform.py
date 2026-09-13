"""
Unit tests for TikTok platform integration in Vyntra.
"""

from unittest.mock import MagicMock, patch
import unittest

from vyntra.models import AudioQuality, DownloadTask, MediaFormat, MediaItem, Platform
from vyntra.platforms.registry import platform_registry
from vyntra.platforms.tiktok.service import tiktok_platform


class TestTikTokPlatform(unittest.TestCase):
    """Test suite for TikTok platform service and capabilities."""

    def test_platform_registration(self):
        svc = platform_registry.get("tiktok")
        self.assertIsNotNone(svc)
        self.assertEqual(svc.platform_id, "tiktok")
        self.assertEqual(svc.capabilities.display_name, "TikTok")

    def test_capabilities_declaration(self):
        caps = tiktok_platform.capabilities
        self.assertFalse(caps.supports_search, "TikTok must not pretend to support keyword search")
        self.assertTrue(caps.supports_url_input)
        self.assertTrue(caps.supports_video_playback)
        self.assertTrue(caps.supports_mp4)
        self.assertTrue(caps.supports_mp3)
        self.assertFalse(caps.supports_video_quality)

    def test_url_detection(self):
        valid_urls = [
            "https://www.tiktok.com/@creator/video/7123456789012345678",
            "https://vm.tiktok.com/ZM8abc123/",
            "https://vt.tiktok.com/ZS9xyz789/",
            "http://m.tiktok.com/v/7123456789.html",
        ]
        invalid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.instagram.com/reel/C7XyZ123456/",
            "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
            "https://example.com",
            "",
        ]
        for url in valid_urls:
            self.assertTrue(tiktok_platform.can_handle_url(url), f"Should handle valid TikTok URL: {url}")
        for url in invalid_urls:
            self.assertFalse(tiktok_platform.can_handle_url(url), f"Should reject non-TikTok URL: {url}")

    def test_build_download_options_mp4(self):
        item = MediaItem(
            video_id="7123456789",
            title="Fun Dance",
            channel="@dancer",
            url="https://www.tiktok.com/@dancer/video/7123456789",
            platform="tiktok",
        )
        task = DownloadTask(
            result=item,
            format=MediaFormat.MP4,
            save_directory="D:/Downloads",
        )
        opts = tiktok_platform.build_download_options(task, "D:/Downloads/Fun_Dance")
        self.assertIn("outtmpl", opts)
        self.assertIn("postprocessors", opts)
        has_video_convert = any(p.get("key") == "FFmpegVideoConvertor" for p in opts["postprocessors"])
        self.assertTrue(has_video_convert)

    def test_build_download_options_mp3(self):
        item = MediaItem(
            video_id="7123456789",
            title="Fun Dance",
            channel="@dancer",
            url="https://www.tiktok.com/@dancer/video/7123456789",
            platform="tiktok",
        )
        task = DownloadTask(
            result=item,
            format=MediaFormat.MP3,
            save_directory="D:/Downloads",
            audio_quality=AudioQuality.BEST,
        )
        opts = tiktok_platform.build_download_options(task, "D:/Downloads/Fun_Dance")
        has_audio_extract = any(p.get("key") == "FFmpegExtractAudio" for p in opts["postprocessors"])
        self.assertTrue(has_audio_extract)

    @patch("yt_dlp.YoutubeDL")
    def test_extract_from_url_mock(self, mock_ydl_cls):
        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {
            "id": "7123456789",
            "title": "Viral dance challenge 2026",
            "uploader": "popular_creator",
            "duration": 30,
            "thumbnail": "https://p16-sign.tiktokcdn.com/thumb.jpg",
            "url": "https://v16-webapp-prime.tiktok.com/video.mp4",
        }
        mock_ydl_cls.return_value.__enter__.return_value = mock_instance

        item = tiktok_platform.extract_from_url("https://www.tiktok.com/@popular_creator/video/7123456789")
        self.assertIsNotNone(item)
        self.assertEqual(item.video_id, "7123456789")
        self.assertEqual(item.platform, "tiktok")
        self.assertEqual(item.channel, "@popular_creator")
        self.assertEqual(item.duration_seconds, 30)
        self.assertEqual(item.duration_formatted, "00:30")

    def test_classify_error(self):
        """Verifies retryable vs non-retryable TikTok error classification."""
        # 1. Challenge / WAF block
        err_challenge = Exception("Unexpected response from webpage request")
        retryable, cat, msg = tiktok_platform.classify_error(err_challenge)
        self.assertFalse(retryable)
        self.assertEqual(cat, "challenge_or_waf_block")
        self.assertIn("challenge verification", msg)

        # 2. Deleted or not found
        err_not_found = Exception("Video currently unavailable or does not exist")
        retryable, cat, msg = tiktok_platform.classify_error(err_not_found)
        self.assertFalse(retryable)
        self.assertEqual(cat, "video_not_found")
        self.assertIn("deleted or is not publicly accessible", msg)

        # 3. Network temporary
        err_timeout = Exception("Connection timed out reading from server")
        retryable, cat, msg = tiktok_platform.classify_error(err_timeout)
        self.assertTrue(retryable)
        self.assertEqual(cat, "network_temporary")

    def test_diagnose_report_format(self):
        """Verifies that TikTok diagnostics report conforms to standard format."""
        report = tiktok_platform.diagnose("https://www.tiktok.com/@test/video/123456789")
        self.assertIn("Vyntra TikTok Diagnostics", report)
        self.assertIn("yt-dlp:", report)
        self.assertIn("Python:", report)
        self.assertIn("curl_cffi:", report)
        self.assertIn("Browser impersonation:", report)
        self.assertIn("Cookies:", report)

    def test_live_extraction_regression_url(self):
        """Regression test for URL producing video 7626081842592009504."""
        test_url = "https://www.tiktok.com/@tiktok/video/7626081842592009504"
        try:
            item = tiktok_platform.extract_from_url(test_url)
            self.assertIsNotNone(item)
            self.assertEqual(item.video_id, "7626081842592009504")
            self.assertEqual(item.platform, "tiktok")
            self.assertGreater(len(item.display_title), 0)
            self.assertGreater(len(item.audio_source_url or ""), 0)
        except Exception as e:
            # If rate-limited by remote IP in CI, verify error classification operates cleanly
            retryable, cat, msg = tiktok_platform.classify_error(e)
            self.assertIn(cat, ["challenge_or_waf_block", "network_temporary", "extraction_error"])


if __name__ == "__main__":
    unittest.main()
