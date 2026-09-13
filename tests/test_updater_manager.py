"""
Unit and integration tests for UpdateManager and UpdateDownloadManager.
Verifies GitHub API parsing, background thread execution, SHA-256 integrity verification,
network failure tolerance, and corrupted payload rejection.
"""

import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from vyntra.updater.download_manager import (
    UpdateDownloadError,
    UpdateDownloadManager,
    UpdateIntegrityError,
)
from vyntra.updater.manager import UpdateManager, UpdateState
from vyntra.updater.models import ReleaseAsset, UpdateCheckResult


class TestUpdaterManager(unittest.TestCase):
    """Verifies UpdateManager state machine, GitHub API handling, and security verification."""

    def setUp(self):
        self.manager = UpdateManager()

    def test_evaluate_release_update_available(self):
        """Verifies detection of newer published stable release."""
        fake_release = {
            "tag_name": "v1.2.4",
            "name": "Vyntra v1.2.4 - Multi-Platform & Updater",
            "body": "### What's new\n- Automatic updates\n- Bug fixes",
            "published_at": "2026-09-14T12:00:00Z",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": "Vyntra-Windows-x64.exe",
                    "browser_download_url": "https://github.com/SaminMp/Vyntra/releases/download/v1.2.4/Vyntra-Windows-x64.exe",
                    "size": 85000000,
                    "content_type": "application/octet-stream",
                },
                {
                    "name": "Vyntra-macOS-arm64.dmg",
                    "browser_download_url": "https://github.com/SaminMp/Vyntra/releases/download/v1.2.4/Vyntra-macOS-arm64.dmg",
                    "size": 75000000,
                    "content_type": "application/octet-stream",
                },
            ],
        }

        with patch("vyntra.updater.platform_detector.get_current_platform", return_value="windows"), \
             patch("vyntra.updater.platform_detector.get_current_arch", return_value="x64"):

            result = self.manager._evaluate_release(fake_release, current_version="1.1.3")
            self.assertEqual(result.status, "available")
            self.assertTrue(result.has_update)
            self.assertIsNotNone(result.latest_release)
            self.assertEqual(result.latest_release.version, "1.2.4")
            self.assertIn("Automatic updates", result.latest_release.release_notes)
            self.assertIsNotNone(result.target_asset)
            self.assertEqual(result.target_asset.name, "Vyntra-Windows-x64.exe")

    def test_evaluate_release_up_to_date(self):
        """Verifies current version matching release version results in up_to_date."""
        fake_release = {
            "tag_name": "v1.1.3",
            "draft": False,
            "prerelease": False,
            "assets": [],
        }
        result = self.manager._evaluate_release(fake_release, current_version="1.1.3")
        self.assertEqual(result.status, "up_to_date")
        self.assertFalse(result.has_update)

    def test_evaluate_release_ignores_draft_and_prerelease(self):
        """Verifies draft and prerelease tags are ignored on stable channel."""
        fake_draft = {
            "tag_name": "v1.5.0",
            "draft": True,
            "prerelease": False,
            "assets": [],
        }
        result = self.manager._evaluate_release(fake_draft, current_version="1.1.3")
        self.assertEqual(result.status, "up_to_date")

        fake_prerelease = {
            "tag_name": "v2.0.0-beta.1",
            "draft": False,
            "prerelease": True,
            "assets": [],
        }
        result = self.manager._evaluate_release(fake_prerelease, current_version="1.1.3")
        self.assertEqual(result.status, "up_to_date")

    @patch("requests.get")
    def test_check_for_updates_network_failure_does_not_crash(self, mock_get):
        """Verifies network connection error is caught gracefully and logged."""
        mock_get.side_effect = Exception("DNS lookup failed")
        callback_mock = MagicMock()

        self.manager._run_check_worker(callback=callback_mock, background=True)

        callback_mock.assert_called_once()
        result = callback_mock.call_args[0][0]
        self.assertEqual(result.status, "error")
        self.assertIn("DNS lookup failed", result.error_message)

    def test_download_and_sha256_verification_success(self):
        """Verifies streaming download computes correct SHA-256 and passes verification."""
        content = b"Mock Vyntra executable binary payload data 123456789"
        expected_hash = hashlib.sha256(content).hexdigest()

        asset = ReleaseAsset(
            name="Vyntra-Test.exe",
            download_url="http://mock.test/Vyntra-Test.exe",
            size=len(content),
            sha256=expected_hash,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": str(len(content))}
        mock_response.iter_content.return_value = [content[:20], content[20:]]
        mock_response.__enter__.return_value = mock_response

        downloader = UpdateDownloadManager()
        with patch("requests.get", return_value=mock_response):
            dest_file = downloader.download_asset(asset, expected_sha256=expected_hash)
            self.assertTrue(dest_file.exists())
            self.assertEqual(dest_file.read_bytes(), content)
            # Cleanup
            dest_file.unlink()

    def test_download_sha256_mismatch_rejects_and_deletes_file(self):
        """Verifies that a hash mismatch raises UpdateIntegrityError and purges the file."""
        content = b"Corrupted or tampered payload"
        bad_hash = "0000000000000000000000000000000000000000000000000000000000000000"

        asset = ReleaseAsset(
            name="Vyntra-Corrupt.exe",
            download_url="http://mock.test/corrupt.exe",
            size=len(content),
            sha256=bad_hash,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": str(len(content))}
        mock_response.iter_content.return_value = [content]
        mock_response.__enter__.return_value = mock_response

        downloader = UpdateDownloadManager()
        with patch("requests.get", return_value=mock_response):
            with self.assertRaises(UpdateIntegrityError):
                downloader.download_asset(asset, expected_sha256=bad_hash)

            # Ensure file does not remain in staging
            staging_path = downloader._current_dest
            if staging_path:
                self.assertFalse(staging_path.exists(), "Corrupted payload must be deleted")


if __name__ == "__main__":
    unittest.main()
