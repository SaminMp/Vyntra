"""
Unit tests for VyntraUpdateServiceProvider.
Verifies client communication with the server-side update service,
asset discovery, SemVer evaluation, offline resilience, and hash verification.
"""

import hashlib
import os
import unittest
from unittest.mock import MagicMock, patch

from vyntra.updater.download_manager import UpdateDownloadManager, UpdateIntegrityError
from vyntra.updater.models import ReleaseAsset
from vyntra.updater.providers.service_provider import VyntraUpdateServiceProvider


class TestVyntraUpdateServiceProvider(unittest.TestCase):
    """Verifies VyntraUpdateServiceProvider behavior against update service API."""

    def setUp(self):
        self.provider = VyntraUpdateServiceProvider(service_url="https://mock-update.vyntra.app")

    @patch("requests.get")
    def test_check_for_updates_available(self, mock_get):
        """When update service returns update_available=True, returns status='available'."""
        fake_response = {
            "update_available": True,
            "version": "1.2.4",
            "tag": "v1.2.4",
            "name": "Vyntra v1.2.4",
            "release_notes": "### New Features\n- Background updates\n- Bug fixes",
            "platform": "windows-x64",
            "asset_name": "Vyntra-Windows-x64.exe",
            "download_url": "https://mock-update.vyntra.app/api/v1/updates/download/windows-x64?version=1.2.4",
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "size": 85000000,
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_response
        mock_get.return_value = mock_resp

        result = self.provider.check_for_updates(current_version="1.1.3")

        self.assertEqual(result.status, "available")
        self.assertTrue(result.has_update)
        self.assertEqual(result.latest_release.version, "1.2.4")
        self.assertIsNotNone(result.target_asset)
        self.assertEqual(result.target_asset.name, "Vyntra-Windows-x64.exe")
        self.assertEqual(result.target_asset.sha256, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

    @patch("requests.get")
    def test_check_for_updates_up_to_date(self, mock_get):
        """When update service returns update_available=False, returns status='up_to_date'."""
        fake_response = {
            "update_available": False,
            "version": "1.1.3",
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_response
        mock_get.return_value = mock_resp

        result = self.provider.check_for_updates(current_version="1.1.3")
        self.assertEqual(result.status, "up_to_date")
        self.assertFalse(result.has_update)

    @patch("requests.get")
    def test_check_for_updates_offline_graceful_fallback(self, mock_get):
        """When server is offline or connection fails, fails gracefully without crashing."""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("Failed to connect to update server")

        result = self.provider.check_for_updates(current_version="1.1.3")
        self.assertEqual(result.status, "up_to_date")
        self.assertFalse(result.has_update)

    @patch("requests.get")
    def test_check_for_updates_env_override(self, mock_get):
        """VYNTRA_UPDATE_SERVICE_URL environment variable overrides default service URL."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"update_available": False, "version": "1.1.3"}
        mock_get.return_value = mock_resp

        with patch.dict(os.environ, {"VYNTRA_UPDATE_SERVICE_URL": "https://staging-update.example.com"}):
            provider = VyntraUpdateServiceProvider()
            self.assertEqual(provider.service_url, "https://staging-update.example.com")
            provider.check_for_updates(current_version="1.1.3")

            call_url = mock_get.call_args[0][0]
            self.assertTrue(call_url.startswith("https://staging-update.example.com"))

    def test_download_asset_integrity(self):
        """Verifies downloaded stream has SHA-256 validated."""
        content = b"Mock executable from update service proxy"
        expected_hash = hashlib.sha256(content).hexdigest()

        asset = ReleaseAsset(
            name="Vyntra-Windows-x64.exe",
            download_url="https://mock-update.vyntra.app/api/v1/updates/download/windows-x64",
            size=len(content),
            sha256=expected_hash,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-length": str(len(content))}
        mock_resp.iter_content.return_value = [content]
        mock_resp.__enter__.return_value = mock_resp

        with patch("requests.get", return_value=mock_resp):
            staged = self.provider.download_asset(asset)
            self.assertTrue(staged.exists())
            self.assertEqual(staged.read_bytes(), content)
            staged.unlink()
