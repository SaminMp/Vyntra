"""
Comprehensive Unit and Integration Test Suite for Vyntra's Redesigned YouTubeService.

Tests:
- Base yt-dlp option construction and hardening (cookie-free default, fetch_pot)
- Prioritized player client fallback chain (mweb, web_embedded, visionos, android, tv_downgraded)
- JavaScript runtime detection (Node.js >= 22.0.0) and EJS remote challenge solving
- Cookie management (NO silent browser harvesting; explicit user-consented file only)
- Native PO Token Provider (VyntraPTP) inspection and automatic integration
- Multi-strategy extraction fallback (Strategy 1 -> Strategy 2 -> Strategy 3)
- Real format probing without fake fallbacks
- Error classification (zero cookie prompts; clean content-restriction reporting)
- Diagnostics mode output schema and strict privacy guarantee
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
        self.assertIn("fetch_pot", opts["extractor_args"]["youtube"])
        self.assertEqual(opts["extractor_args"]["youtube"]["fetch_pot"], ["auto"])

        clients = opts["extractor_args"]["youtube"]["player_client"]
        self.assertEqual(clients, ["mweb", "web_embedded", "visionos"])

        # When explicit cookies are present, authed clients are used
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

    def test_no_silent_browser_cookie_harvesting(self):
        """CRITICAL: Verifies Vyntra NEVER silently harvests or reads browser databases."""
        opts = self.service.get_base_ydl_options()
        self.assertNotIn("cookiesfrombrowser", opts)

    def test_cookie_file_inclusion_when_explicitly_present(self):
        """Verifies cookie file is included only when user explicitly provides a custom cookie file."""
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


class TestYouTubeServicePOToken(unittest.TestCase):
    """Verifies PO Token inspection and provider auditing."""

    def setUp(self):
        self.service = YouTubeService()

    def test_po_token_provider_active(self):
        """Verifies native Vyntra PO Token Provider is active and reporting."""
        provider, is_gen, is_att = self.service.get_po_token_info()
        self.assertTrue(is_gen)
        self.assertTrue(is_att)
        self.assertIn("PO Token Provider", provider)


class TestYouTubeServiceMultiStrategyFallback(unittest.TestCase):
    """Verifies multi-tier client fallback behavior across strategies."""

    def setUp(self):
        self.service = YouTubeService()

    @patch("yt_dlp.YoutubeDL")
    def test_fallback_to_strategy_2_on_strategy_1_failure(self, mock_ydl_class):
        """Verifies that if Strategy 1 encounters a challenge, Strategy 2 is tried and succeeds."""
        mock_instance = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_instance

        # First call (Strategy 1) fails with bot check; Second call (Strategy 2) succeeds
        mock_instance.extract_info.side_effect = [
            RuntimeError("ERROR: [youtube] id123: Sign in to confirm you’re not a bot."),
            {"title": "Test Video", "formats": [{"height": 720, "vcodec": "avc1"}]},
        ]

        info = self.service.extract_info_with_fallback("https://www.youtube.com/watch?v=id123")
        self.assertIsNotNone(info)
        self.assertEqual(info.get("title"), "Test Video")
        self.assertEqual(mock_instance.extract_info.call_count, 2)


class TestYouTubeServiceFormatProbing(unittest.TestCase):
    """Verifies format probing parses genuine stream heights and NEVER returns fake fallbacks."""

    def setUp(self):
        self.service = YouTubeService()

    @patch.object(YouTubeService, "extract_info_with_fallback")
    def test_format_probe_success(self, mock_extract):
        """Verifies resolution sorting and deduplication on success."""
        mock_extract.return_value = {
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

    @patch.object(YouTubeService, "extract_info_with_fallback")
    def test_format_probe_failure_returns_empty_never_fake_fallbacks(self, mock_extract):
        """CRITICAL: Verifies that probe failure returns ([], error_message) and NEVER fake resolutions."""
        mock_extract.side_effect = RuntimeError("ERROR: [youtube] rJgNgZRCi6s: Sign in to confirm you’re not a bot.")

        resolutions, err = self.service.get_available_resolutions("rJgNgZRCi6s")
        self.assertEqual(resolutions, [])
        self.assertIsNotNone(err)
        self.assertIn("challenge", err.lower())
        # Ensure NO cookie prompt is present
        self.assertNotIn("cookie", err.lower())
        self.assertNotIn("settings", err.lower())


class TestYouTubeServiceErrorClassification(unittest.TestCase):
    """Verifies that YouTube errors are translated into clear, accurate human categories without cookie prompts."""

    def setUp(self):
        self.service = YouTubeService()

    def test_classify_bot_verification_no_cookie_prompts(self):
        """CRITICAL: Bot challenges must NEVER ask the user to configure cookies in Settings."""
        err = Exception("Sign in to confirm you’re not a bot. Use --cookies-from-browser")
        classified = self.service.classify_error(err)
        self.assertNotIn("cookie", classified.lower())
        self.assertNotIn("settings", classified.lower())
        self.assertNotIn("firefox", classified.lower())
        self.assertIn("challenge", classified.lower())

    def test_classify_private_video(self):
        err = Exception("ERROR: [youtube] abc: Private video")
        classified = self.service.classify_error(err)
        self.assertIn("private", classified.lower())
        self.assertNotIn("cookie", classified.lower())

    def test_classify_members_only(self):
        err = Exception("ERROR: [youtube] abc: Join this channel to get access to members-only content")
        classified = self.service.classify_error(err)
        self.assertIn("membership", classified.lower())
        self.assertNotIn("cookie", classified.lower())

    def test_classify_age_restricted(self):
        err = Exception("ERROR: [youtube] abc: Sign in to confirm your age")
        classified = self.service.classify_error(err)
        self.assertIn("age-restricted", classified.lower())
        self.assertNotIn("cookie", classified.lower())

    def test_classify_rate_limit(self):
        err = Exception("HTTP Error 429: Too Many Requests")
        classified = self.service.classify_error(err)
        self.assertIn("rate-limiting", classified.lower())


class TestYouTubeServiceDiagnostics(unittest.TestCase):
    """Verifies diagnostics report format and absence of secrets."""

    def setUp(self):
        self.service = YouTubeService()

    @patch.object(YouTubeService, "extract_info_with_fallback")
    def test_diagnose_video_schema(self, mock_extract):
        """Verifies report header, section headers, and absence of secrets."""
        mock_extract.return_value = {
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
