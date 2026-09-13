"""
Unit tests for dynamic quality resolution selection, MP3 bitrate handling,
and player integration.
"""

from unittest.mock import MagicMock, patch
import unittest

from vyntra.models import AudioQuality, DownloadTask, MediaFormat, SearchResult
from vyntra.services.download_service import download_service
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.services.search_service import search_service
from vyntra.ui.views.player_modal import VideoPlayerModal
import customtkinter as ctk


class TestQualitySelection(unittest.TestCase):
    """Verifies that MP3 and MP4 download tasks correctly generate appropriate quality formats."""

    def setUp(self):
        ffmpeg_service.get_status(force_refresh=True)
        self.dummy_result = SearchResult(
            video_id="dummy123",
            title="Test Song",
            channel="Artist",
            duration_seconds=180,
            duration_formatted="03:00",
            thumbnail_url="https://example.com/thumb.jpg",
            url="https://www.youtube.com/watch?v=dummy123",
        )

    def test_mp3_quality_bitrate_options(self):
        """Verify that MP3 tasks set preferredquality based on selected_quality."""
        bitrate_tests = [
            ("320 kbps", "320"),
            ("256 kbps", "256"),
            ("192 kbps", "192"),
            ("128 kbps", "128"),
            ("unknown", "320"),  # fallback
        ]

        for quality_str, expected_bitrate in bitrate_tests:
            task = DownloadTask(
                result=self.dummy_result,
                format=MediaFormat.MP3,
                save_directory="/tmp",
                selected_quality=quality_str,
            )
            opts = download_service.build_ydl_options(task, "/tmp/dummy")
            self.assertIn("postprocessors", opts)
            extract_audio_pp = next(
                (p for p in opts["postprocessors"] if p.get("key") == "FFmpegExtractAudio"),
                None,
            )
            self.assertIsNotNone(extract_audio_pp, "FFmpegExtractAudio postprocessor missing")
            self.assertEqual(extract_audio_pp.get("preferredquality"), expected_bitrate)
            self.assertEqual(extract_audio_pp.get("preferredcodec"), "mp3")

    def test_mp4_resolution_format_spec(self):
        """Verify that MP4 tasks target requested height with automatic fallback."""
        res_tests = [
            ("1080p", 1080),
            ("720p", 720),
            ("480p", 480),
            ("2160p (4K)", 2160),
        ]

        for res_str, expected_height in res_tests:
            task = DownloadTask(
                result=self.dummy_result,
                format=MediaFormat.MP4,
                save_directory="/tmp",
                selected_quality=res_str,
            )
            opts = download_service.build_ydl_options(task, "/tmp/dummy")
            self.assertEqual(opts.get("merge_output_format"), "mp4")
            format_spec = opts.get("format", "")
            self.assertIn(f"height<={expected_height}", format_spec)
            self.assertIn("bestvideo", format_spec)
            self.assertIn("bestaudio", format_spec)

    def test_mp4_best_quality_fallback(self):
        """Verify that 'Best Available' for MP4 selects best video + best audio."""
        task = DownloadTask(
            result=self.dummy_result,
            format=MediaFormat.MP4,
            save_directory="/tmp",
            selected_quality="Best Available",
        )
        opts = download_service.build_ydl_options(task, "/tmp/dummy")
        self.assertEqual(opts.get("merge_output_format"), "mp4")
        format_spec = opts.get("format", "")
        self.assertIn("bestvideo", format_spec)
        self.assertIn("bestaudio", format_spec)


class TestSearchServiceResolutionExtraction(unittest.TestCase):
    """Verifies that SearchService parses available stream heights from yt-dlp metadata."""

    @patch("yt_dlp.YoutubeDL")
    def test_get_available_resolutions_parsing(self, mock_ydl_class):
        mock_ydl = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "formats": [
                {"vcodec": "none", "acodec": "mp4a.40.2"},  # audio only
                {"vcodec": "avc1", "height": 360},
                {"vcodec": "avc1", "height": 720},
                {"vcodec": "vp9", "height": 1080},
                {"vcodec": "vp9", "height": 720},  # duplicate height
                {"vcodec": "avc1", "height": 240},
            ]
        }

        resolutions = search_service.get_available_resolutions("dummy_id")
        self.assertEqual(resolutions, ["Best (Auto)", "1080p (FHD)", "720p (HD)", "360p", "240p"])

    @patch("yt_dlp.YoutubeDL")
    def test_get_available_resolutions_empty_on_error(self, mock_ydl_class):
        """Verifies that no fake fallbacks (e.g. 1080p, 720p) are returned when format probing fails."""
        mock_ydl = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.side_effect = RuntimeError("Network error")

        resolutions = search_service.get_available_resolutions("dummy_fail_id")
        self.assertEqual(resolutions, [])


class TestPlayerModalArchitecture(unittest.TestCase):
    """Verifies in-process video player modal architecture."""

    def test_player_modal_is_toplevel(self):
        """Ensure VideoPlayerModal inherits from CTkToplevel, not CTk (which would be a second root)."""
        self.assertTrue(issubclass(VideoPlayerModal, ctk.CTkToplevel))
        self.assertFalse(issubclass(VideoPlayerModal, ctk.CTk))


if __name__ == "__main__":
    unittest.main()
