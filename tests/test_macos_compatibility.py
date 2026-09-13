"""
Unit tests for macOS and cross-platform compatibility in Vyntra.
Validates Apple macOS paths, icons, FFmpeg candidate discovery, and Safari browser options.
"""

import os
from pathlib import Path
import platform
import unittest
from unittest.mock import patch

from vyntra.config import get_app_data_dir
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.services.youtube_service import youtube_service


class TestMacOSCompatibility(unittest.TestCase):
    """Verifies macOS / Apple device compatibility across services."""

    def test_icon_assets_exist(self):
        """Verifies that all three cross-platform icon assets exist and are valid."""
        root = Path(__file__).resolve().parent.parent
        assets = root / "assets"
        
        ico = assets / "icon.ico"
        png = assets / "icon.png"
        icns = assets / "icon.icns"
        
        self.assertTrue(ico.is_file(), "Windows icon.ico must exist")
        self.assertTrue(png.is_file(), "Universal icon.png must exist")
        self.assertTrue(icns.is_file(), "Apple macOS icon.icns must exist")
        
        self.assertGreater(ico.stat().st_size, 0)
        self.assertGreater(png.stat().st_size, 0)
        self.assertGreater(icns.stat().st_size, 0)

    def test_macos_app_data_dir_resolution(self):
        """Verifies standard macOS Application Support path resolution."""
        with patch("sys.platform", "darwin"), patch("pathlib.Path.home", return_value=Path("/Users/testuser")):
            with patch("pathlib.Path.is_dir", return_value=False):
                resolved = get_app_data_dir()
                expected = Path("/Users/testuser/Library/Application Support/Vyntra")
                self.assertEqual(resolved, expected)

    def test_macos_ffmpeg_candidates(self):
        """Verifies that Apple Silicon and Intel Homebrew paths are checked on Darwin."""
        def mock_is_file(p):
            return "/opt/homebrew/bin/ffmpeg" in str(p) or "/usr/local/bin/ffmpeg" in str(p)

        with patch("platform.system", return_value="Darwin"), \
             patch("os.path.isfile", side_effect=mock_is_file), \
             patch("os.access", return_value=True):
            candidates = ffmpeg_service._get_candidate_paths()
            self.assertIn("/opt/homebrew/bin/ffmpeg", candidates, "Apple Silicon Homebrew path must be checked")
            self.assertIn("/usr/local/bin/ffmpeg", candidates, "Intel Homebrew path must be checked")

    def test_safari_browser_cookie_option_in_youtube_service(self):
        """Verifies that Safari browser option can be configured and parsed."""
        from vyntra.config import config_manager
        orig_mode = config_manager.config.youtube_media_auth_mode
        orig_browser = config_manager.config.youtube_media_browser
        try:
            config_manager.update(
                youtube_media_auth_mode="browser",
                youtube_media_browser="safari"
            )
            ydl_opts = youtube_service.get_base_ydl_options(purpose="search")
            self.assertEqual(ydl_opts.get("cookiesfrombrowser"), ("safari", None, None, None))
        finally:
            config_manager.update(
                youtube_media_auth_mode=orig_mode,
                youtube_media_browser=orig_browser
            )

    def test_mac_app_bundle_structure(self):
        """Verifies dist/Vyntra.app bundle structure, Info.plist, and launcher."""
        root = Path(__file__).resolve().parent.parent
        app_bundle = root / "dist" / "Vyntra.app"
        
        self.assertTrue(app_bundle.is_dir(), "dist/Vyntra.app directory must exist")
        self.assertTrue((app_bundle / "Contents" / "Info.plist").is_file(), "Info.plist must exist")
        self.assertTrue((app_bundle / "Contents" / "PkgInfo").is_file(), "PkgInfo must exist")
        self.assertTrue((app_bundle / "Contents" / "MacOS" / "Vyntra").is_file(), "MacOS/Vyntra launcher must exist")
        self.assertTrue((app_bundle / "Contents" / "Resources" / "icon.icns").is_file(), "icon.icns must exist in Resources")
        self.assertTrue((app_bundle / "Contents" / "Resources" / "run.py").is_file(), "run.py must exist in Resources")
        self.assertTrue((app_bundle / "Contents" / "Resources" / "vyntra").is_dir(), "vyntra package must exist in Resources")
        
        # Verify portable zip
        zip_file = root / "dist" / "Vyntra-macOS-Portable.zip"
        self.assertTrue(zip_file.is_file(), "dist/Vyntra-macOS-Portable.zip must exist")
        self.assertGreater(zip_file.stat().st_size, 100000)


if __name__ == "__main__":
    unittest.main()
