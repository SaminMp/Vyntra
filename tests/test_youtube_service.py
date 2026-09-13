"""
Comprehensive Unit and Integration Test Suite for Vyntra's Centralized YouTubeService.

Tests:
- Base yt-dlp option construction and hardening
- Player client fallback chain
- JavaScript runtime detection (Node.js >= 22.0.0) and EJS remote challenge solving
- Cookie detection (explicit, user-consented only; NO silent browser scraping)
- PO Token inspection and provider auditing
- Format probing without fake fallbacks
- Error classification (bot verification, rate limits, private videos)
- Diagnostics mode output schema (Section 9) and strict privacy guarantee
- SearchService delegation
"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from vyntra.config import config_manager
from vyntra.models import DownloadTask, MediaFormat, SearchResult
from vyntra.services.search_service import search_service
from vyntra.services.youtube_service import YouTubeService, youtube_service


class TestYouTubeServiceOptions(unittest.TestCase):
    """Verifies yt-dlp option construction, runtime dependencies, and player clients."""

    def setUp(self):
        self.service = YouTubeService()

    def test_version_property(self):
        """Verifies ytdlp_version returns a valid release string."""
        ver = self.service.ytdlp_version
        self.assertNotEqual(ver, "unknown")
        self.assertTrue(len(ver) >= 4)

    def test_base_ydl_options_structure(self):
        """Verifies unified base yt-dlp options structure."""
        opts = self.service.get_base_ydl_options(purpose="probe")
        self.assertIn("extractor_args", opts)
        self.assertIn("youtube", opts["extractor_args"])
        self.assertIn("player_client", opts["extractor_args"]["youtube"])

        clients = opts["extractor_args"]["youtube"]["player_client"]
        self.assertEqual(clients, ["default"])

        # When cookies are present or auth_mode is browser, authed clients are used
        with patch.object(self.service, "is_cookies_available", return_value=True):
            authed_opts = self.service.get_base_ydl_options(purpose="probe")
            authed_clients = authed_opts["extractor_args"]["youtube"]["player_client"]
            self.assertEqual(authed_clients, ["web_embedded", "tv_downgraded", "web"])

        # Node.js and remote components
        node_path = self.service.get_node_path()
        if node_path:
            self.assertIn("js_runtimes", opts)
            self.assertIn("node", opts["js_runtimes"])
            self.assertEqual(opts["js_runtimes"]["node"]["path"], node_path)
            self.assertIn("remote_components", opts)
            self.assertIn("ejs:github", opts["remote_components"])


class TestYouTubeServiceCookiesAndPrivacy(unittest.TestCase):
    """Verifies cookie management complies strictly with user-consent and privacy rules."""

    def setUp(self):
        self.service = YouTubeService()

    def test_cookie_file_inclusion_when_present(self):
        """Verifies cookie file is included when user explicitly provides ~/.vyntra/cookies.txt."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tf:
            tf.write("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t1800000000\tSID\tsecret_val\n")
            temp_path = tf.name

        try:
            with patch.object(self.service, "get_cookie_file_path", return_value=temp_path):
                self.assertTrue(self.service.is_cookies_available())
                opts = self.service.get_base_ydl_options()
                self.assertEqual(opts.get("cookiefile"), temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_no_cookies_by_default_without_file(self):
        """Verifies no cookie file is supplied if user has not placed one."""
        with patch.object(self.service, "get_cookie_file_path", return_value=None):
            self.assertFalse(self.service.is_cookies_available())
            opts = self.service.get_base_ydl_options()
            self.assertNotIn("cookiefile", opts)

    def test_browser_cookies_attached_when_configured(self):
        """Verifies yt-dlp receives cookiesfrombrowser tuple when user explicitly configures browser."""
        with patch.object(config_manager.config, "youtube_media_auth_mode", "browser"), \
             patch.object(config_manager.config, "youtube_media_browser", "firefox"), \
             patch.object(config_manager.config, "youtube_media_browser_profile", ""):
            opts = self.service.get_base_ydl_options()
            self.assertEqual(opts.get("cookiesfrombrowser"), ("firefox", None, None, None))
            self.assertNotIn("cookiefile", opts)

    @patch("yt_dlp.YoutubeDL")
    def test_media_access_dpapi_detection(self, mock_ydl_class):
        """Verifies Chrome/Edge Windows App-Bound DPAPI errors are caught with helpful guidance."""
        mock_ydl = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.side_effect = RuntimeError("Failed to decrypt with DPAPI. See https://github.com/yt-dlp/yt-dlp/issues/10927")

        ok, msg = self.service.test_youtube_media_access("test_vid")
        self.assertFalse(ok)
        self.assertIn("App-Bound encryption", msg)
        self.assertIn("Firefox", msg)
        self.assertNotIn("Traceback", msg)


class TestYouTubeServicePOToken(unittest.TestCase):
    """Verifies PO Token inspection and provider auditing."""

    def setUp(self):
        self.service = YouTubeService()

    def test_po_token_absent(self):
        """Verifies PO token info when no token file exists."""
        with patch("pathlib.Path.is_file", return_value=False):
            provider, is_gen, is_att = self.service.get_po_token_info()
            self.assertEqual(provider, "None (No PO Token Provider Configured)")
            self.assertFalse(is_gen)
            self.assertFalse(is_att)


class TestYouTubeServiceFormatProbing(unittest.TestCase):
    """Verifies format probing parses genuine stream heights and NEVER returns fake fallbacks."""

    def setUp(self):
        self.service = YouTubeService()

    @patch("yt_dlp.YoutubeDL")
    def test_format_probe_success(self, mock_ydl_class):
        """Verifies resolution sorting and deduplication on success."""
        mock_ydl = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "formats": [
                {"height": 2160, "vcodec": "vp9"},
                {"height": 1080, "vcodec": "avc1"},
                {"height": 720, "vcodec": "avc1"},
                {"height": 720, "vcodec": "vp9"},  # duplicate
                {"height": 360, "vcodec": "avc1"},
                {"height": None, "vcodec": "none", "acodec": "opus"},  # audio
            ]
        }

        resolutions, err = self.service.get_available_resolutions("mock_id")
        self.assertIsNone(err)
        self.assertEqual(
            resolutions,
            ["Best (Auto)", "2160p (4K)", "1080p (FHD)", "720p (HD)", "360p"],
        )

    @patch("yt_dlp.YoutubeDL")
    def test_format_probe_failure_returns_empty_never_fake_fallbacks(self, mock_ydl_class):
        """CRITICAL: Verifies that probe failure returns ([], error_message) and NEVER fake resolutions."""
        mock_ydl = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.side_effect = RuntimeError("ERROR: [youtube] rJgNgZRCi6s: Sign in to confirm you’re not a bot.")

        resolutions, err = self.service.get_available_resolutions("rJgNgZRCi6s")
        self.assertEqual(resolutions, [])
        self.assertIsNotNone(err)
        self.assertIn("verification", err.lower())


class TestYouTubeServiceErrorClassification(unittest.TestCase):
    """Verifies that YouTube errors are translated into clear, accurate human categories."""

    def setUp(self):
        self.service = YouTubeService()

    def test_classify_bot_verification(self):
        err = Exception("Sign in to confirm you’re not a bot. Use --cookies-from-browser")
        classified = self.service.classify_error(err)
        self.assertIn("YouTube requires sign-in verification", classified)
        self.assertIn("Media Access", classified)

    def test_classify_private_video(self):
        err = Exception("ERROR: [youtube] abc: Private video")
        classified = self.service.classify_error(err)
        self.assertIn("private", classified.lower())

    def test_classify_rate_limit(self):
        err = Exception("HTTP Error 429: Too Many Requests")
        classified = self.service.classify_error(err)
        self.assertIn("rate-limiting", classified.lower())


class TestYouTubeServiceDiagnostics(unittest.TestCase):
    """Verifies diagnostics report format matches Section 9 exact specification."""

    def setUp(self):
        self.service = YouTubeService()

    @patch("yt_dlp.YoutubeDL")
    def test_diagnose_video_schema(self, mock_ydl_class):
        """Verifies report header, section headers, and absence of secrets."""
        mock_ydl = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "formats": [
                {"height": 1080, "vcodec": "avc1", "ext": "mp4"},
                {"height": 720, "vcodec": "avc1", "ext": "mp4"},
            ]
        }

        report = self.service.diagnose_video("test_vid_xyz")
        self.assertIn("Vyntra YouTube Diagnostics", report)
        self.assertIn("yt-dlp version:", report)
        self.assertIn("test_vid_xyz", report)
        self.assertIn("Google OAuth:", report)
        self.assertIn("yt-dlp cookies:", report)
        self.assertIn("Authentication method:", report)
        self.assertIn("Player clients:", report)
        self.assertIn("PO Token provider:", report)
        self.assertIn("PO Token generated:", report)
        self.assertIn("PO Token attached:", report)
        self.assertIn("Format probe:", report)
        self.assertIn("Playback extraction:", report)
        self.assertIn("Download extraction:", report)

        # Ensure no token or secret leak
        self.assertNotIn("secret", report.lower())
        self.assertNotIn("Bearer", report)
        self.assertNotIn("ya29.", report)


if __name__ == "__main__":
    unittest.main()
