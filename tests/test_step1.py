"""
Unit tests for Step 1 components: Models, Utils, and Configuration.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from vyntra.config import ConfigManager
from vyntra.models import AudioQuality, DownloadStatus, MediaFormat, SearchResult
from vyntra.utils.filename import get_unique_filepath, sanitize_filename
from vyntra.utils.formatters import (
    format_bytes,
    format_duration,
    format_eta,
    format_speed,
    format_view_count,
)


class TestStep1(unittest.TestCase):
    """Test suite for Step 1."""

    def test_models(self):
        """Verify SearchResult data model properties."""
        res = SearchResult(
            video_id="dQw4w9WgXcQ",
            title="  Rick Astley - Never Gonna Give You Up (Official Music Video)  ",
            channel="Rick Astley",
            duration_seconds=212,
            duration_formatted="03:32",
            views=1500000000,
            views_formatted="1.5B views",
            thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        self.assertEqual(res.display_title, "Rick Astley - Never Gonna Give You Up (Official Music Video)")
        self.assertEqual(res.video_id, "dQw4w9WgXcQ")

    def test_formatters(self):
        """Verify formatting helpers."""
        self.assertEqual(format_duration(0), "00:00")
        self.assertEqual(format_duration(75), "01:15")
        self.assertEqual(format_duration(3665), "01:01:05")

        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(15 * 1024 * 1024), "15.00 MB")

        self.assertEqual(format_speed(2.5 * 1024 * 1024), "2.50 MB/s")

        self.assertEqual(format_view_count(950), "950 views")
        self.assertEqual(format_view_count(450_000), "450.0K views")
        self.assertEqual(format_view_count(2_400_000), "2.4M views")
        self.assertEqual(format_view_count(1_200_000_000), "1.2B views")

        self.assertEqual(format_eta(90), "01:30")

    def test_filename_sanitization_persian_and_unicode(self):
        """Verify filename sanitizer handles Persian, special characters, and length limits."""
        # Persian title with illegal characters
        persian_title = 'آهنگ آرامش‌بخش / پیانو: ملودی دلنشین * 2026? <HD>'
        sanitized = sanitize_filename(persian_title)
        self.assertNotIn("/", sanitized)
        self.assertNotIn(":", sanitized)
        self.assertNotIn("*", sanitized)
        self.assertNotIn("?", sanitized)
        self.assertNotIn("<", sanitized)
        self.assertNotIn(">", sanitized)
        self.assertTrue("آهنگ آرامش‌بخش" in sanitized)
        self.assertTrue("پیانو" in sanitized)

        # Long title
        long_title = "A" * 300
        truncated = sanitize_filename(long_title, max_length=50)
        self.assertEqual(len(truncated), 50)

    def test_unique_filepath(self):
        """Verify unique filename generation when duplicates exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            f1 = Path(temp_dir) / "test_track.mp3"
            f1.touch()

            unique_path = get_unique_filepath(temp_dir, "test_track", "mp3")
            self.assertEqual(unique_path.name, "test_track (1).mp3")

            unique_path.touch()
            unique_path_2 = get_unique_filepath(temp_dir, "test_track", "mp3")
            self.assertEqual(unique_path_2.name, "test_track (2).mp3")

    def test_config_manager(self):
        """Verify configuration load and persistence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg_mgr = ConfigManager(config_dir=Path(temp_dir))
            self.assertEqual(cfg_mgr.config.default_format, MediaFormat.MP3.value)

            cfg_mgr.update(default_format=MediaFormat.MP4.value, audio_quality=AudioQuality.HIGH.value)
            self.assertEqual(cfg_mgr.config.default_format, MediaFormat.MP4.value)
            self.assertEqual(cfg_mgr.config.audio_quality, AudioQuality.HIGH.value)

            # Re-read from disk
            cfg_mgr_2 = ConfigManager(config_dir=Path(temp_dir))
            self.assertEqual(cfg_mgr_2.config.default_format, MediaFormat.MP4.value)


if __name__ == "__main__":
    unittest.main()
