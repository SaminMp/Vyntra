"""
Unit tests for platform detection and asset selection in Vyntra updater.
"""

import unittest
from unittest.mock import patch
from vyntra.updater.models import ReleaseAsset
from vyntra.updater.platform_detector import (
    get_current_arch,
    get_current_platform,
    select_platform_asset,
)


class TestUpdaterPlatform(unittest.TestCase):
    """Verifies OS/Arch resolution and platform-specific release asset filtering."""

    def test_current_platform_and_arch(self):
        plat = get_current_platform()
        self.assertIn(plat, ["windows", "darwin", "linux"])
        arch = get_current_arch()
        self.assertIn(arch, ["x64", "arm64"])

    @patch("vyntra.updater.platform_detector.get_current_platform", return_value="windows")
    @patch("vyntra.updater.platform_detector.get_current_arch", return_value="x64")
    def test_windows_asset_selection(self, mock_arch, mock_plat):
        assets = [
            ReleaseAsset(name="SHA256SUMS.txt", download_url="http://example.com/sums", size=100),
            ReleaseAsset(name="Vyntra-macOS-arm64.dmg", download_url="http://example.com/mac", size=50000000),
            ReleaseAsset(name="Vyntra-Windows-x64.exe", download_url="http://example.com/win", size=60000000),
        ]
        chosen = select_platform_asset(assets)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.name, "Vyntra-Windows-x64.exe")

    @patch("vyntra.updater.platform_detector.get_current_platform", return_value="darwin")
    @patch("vyntra.updater.platform_detector.get_current_arch", return_value="arm64")
    def test_macos_arm64_asset_selection(self, mock_arch, mock_plat):
        assets = [
            ReleaseAsset(name="SHA256SUMS.txt", download_url="http://example.com/sums", size=100),
            ReleaseAsset(name="Vyntra-macOS-x64.dmg", download_url="http://example.com/intel", size=50000000),
            ReleaseAsset(name="Vyntra-macOS-arm64.dmg", download_url="http://example.com/arm", size=50000000),
            ReleaseAsset(name="Vyntra-Windows-x64.exe", download_url="http://example.com/win", size=60000000),
        ]
        chosen = select_platform_asset(assets)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.name, "Vyntra-macOS-arm64.dmg")

    @patch("vyntra.updater.platform_detector.get_current_platform", return_value="darwin")
    @patch("vyntra.updater.platform_detector.get_current_arch", return_value="x64")
    def test_macos_intel_asset_selection(self, mock_arch, mock_plat):
        assets = [
            ReleaseAsset(name="Vyntra-macOS-arm64.dmg", download_url="http://example.com/arm", size=50000000),
            ReleaseAsset(name="Vyntra-macOS-x64.dmg", download_url="http://example.com/intel", size=50000000),
        ]
        chosen = select_platform_asset(assets)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.name, "Vyntra-macOS-x64.dmg")

    @patch("vyntra.updater.platform_detector.get_current_platform", return_value="windows")
    @patch("vyntra.updater.platform_detector.get_current_arch", return_value="x64")
    def test_no_compatible_asset_returns_none(self, mock_arch, mock_plat):
        assets = [
            ReleaseAsset(name="Vyntra-macOS-arm64.dmg", download_url="http://example.com/arm", size=50000000),
            ReleaseAsset(name="Vyntra-macOS-x64.dmg", download_url="http://example.com/intel", size=50000000),
        ]
        chosen = select_platform_asset(assets)
        self.assertIsNone(chosen)


if __name__ == "__main__":
    unittest.main()
