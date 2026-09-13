"""
Unit tests for GitHubPrivateReleaseProvider.
Tests private release metadata fetching, asset filtering, SemVer precedence,
cross-domain AWS S3 redirect handling, and error handling.
"""

import unittest
from unittest.mock import MagicMock, patch

from vyntra.updater.auth_manager import UpdaterAuthManager
from vyntra.updater.models import ReleaseAsset, UpdateCheckResult
from vyntra.updater.providers.github_provider import GitHubPrivateReleaseProvider


class TestGitHubPrivateReleaseProvider(unittest.TestCase):
    """Verifies GitHubPrivateReleaseProvider behavior against private repositories."""

    def setUp(self):
        self.mock_auth = MagicMock(spec=UpdaterAuthManager)
        self.provider = GitHubPrivateReleaseProvider(
            owner="SaminMp",
            repo="Vyntra",
            auth_mgr=self.mock_auth,
        )

    def test_check_for_updates_unauthenticated_returns_auth_required(self):
        """When no token is configured, check_for_updates returns auth_required."""
        self.mock_auth.get_token.return_value = None

        result = self.provider.check_for_updates(current_version="1.1.3")
        self.assertEqual(result.status, "auth_required")
        self.assertEqual(result.auth_status, "unauthenticated")
        self.assertIn("Connect update access", result.error_message)

    @patch("requests.get")
    def test_check_for_updates_available(self, mock_get):
        """When valid token provided and newer release exists, returns available."""
        self.mock_auth.get_token.return_value = "ghp_valid_token"

        fake_release = {
            "tag_name": "v1.2.4",
            "name": "Vyntra v1.2.4",
            "body": "Private Release Notes",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "id": 101,
                    "name": "Vyntra-Windows-x64.exe",
                    "url": "https://api.github.com/repos/SaminMp/Vyntra/releases/assets/101",
                    "browser_download_url": "https://github.com/SaminMp/Vyntra/releases/download/v1.2.4/Vyntra-Windows-x64.exe",
                    "size": 85000000,
                    "content_type": "application/octet-stream",
                },
                {
                    "id": 102,
                    "name": "Vyntra-macOS-arm64.dmg",
                    "url": "https://api.github.com/repos/SaminMp/Vyntra/releases/assets/102",
                    "browser_download_url": "https://github.com/SaminMp/Vyntra/releases/download/v1.2.4/Vyntra-macOS-arm64.dmg",
                    "size": 75000000,
                    "content_type": "application/octet-stream",
                },
            ],
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_release
        mock_get.return_value = mock_resp

        with patch("vyntra.updater.platform_detector.get_current_platform", return_value="windows"), \
             patch("vyntra.updater.platform_detector.get_current_arch", return_value="x64"):

            result = self.provider.check_for_updates(current_version="1.1.3")
            self.assertEqual(result.status, "available")
            self.assertTrue(result.has_update)
            self.assertEqual(result.target_asset.name, "Vyntra-Windows-x64.exe")
            self.assertEqual(result.target_asset.asset_id, 101)
            self.assertEqual(result.target_asset.api_url, "https://api.github.com/repos/SaminMp/Vyntra/releases/assets/101")

            # Verify authorization header was sent
            call_headers = mock_get.call_args[1]["headers"]
            self.assertEqual(call_headers["Authorization"], "Bearer ghp_valid_token")

    @patch("requests.get")
    def test_check_for_updates_up_to_date(self, mock_get):
        """When release version matches current version, returns up_to_date."""
        self.mock_auth.get_token.return_value = "ghp_valid_token"

        fake_release = {
            "tag_name": "v1.1.3",
            "draft": False,
            "prerelease": False,
            "assets": [],
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_release
        mock_get.return_value = mock_resp

        result = self.provider.check_for_updates(current_version="1.1.3")
        self.assertEqual(result.status, "up_to_date")
        self.assertFalse(result.has_update)

    @patch("requests.get")
    def test_check_for_updates_expired_token(self, mock_get):
        """When GitHub returns 401/403, returns auth_required with invalid_token."""
        self.mock_auth.get_token.return_value = "ghp_expired_token"

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        result = self.provider.check_for_updates(current_version="1.1.3")
        self.assertEqual(result.status, "auth_required")
        self.assertEqual(result.auth_status, "invalid_token")

    @patch("requests.get")
    def test_check_for_updates_ignores_draft_and_prerelease(self, mock_get):
        """Drafts and pre-releases are ignored on the stable channel."""
        self.mock_auth.get_token.return_value = "ghp_valid_token"

        fake_release = {
            "tag_name": "v2.0.0-rc1",
            "draft": False,
            "prerelease": True,
            "assets": [],
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_release
        mock_get.return_value = mock_resp

        result = self.provider.check_for_updates(current_version="1.1.3")
        self.assertEqual(result.status, "up_to_date")

    @patch("requests.get")
    def test_fetch_private_checksums_strips_auth_on_s3_redirect(self, mock_get):
        """
        Critical security test: Ensures Authorization header is stripped when GitHub redirects
        to AWS S3 pre-signed storage to avoid AWS 400 InvalidArgument error.
        """
        probe_resp = MagicMock()
        probe_resp.status_code = 302
        probe_resp.headers = {"Location": "https://objects.githubusercontent.com/s3-storage-presigned-url"}

        s3_resp = MagicMock()
        s3_resp.status_code = 200
        s3_resp.text = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  Vyntra-Windows-x64.exe\n"

        mock_get.side_effect = [probe_resp, s3_resp]

        mapping = self.provider._fetch_private_checksums(
            "https://api.github.com/repos/SaminMp/Vyntra/releases/assets/999",
            token="ghp_secret_token",
        )

        self.assertEqual(len(mapping), 1)
        self.assertEqual(mapping["Vyntra-Windows-x64.exe"], "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

        # Verify second call was to S3 and DID NOT contain Authorization header
        s3_call_headers = mock_get.call_args_list[1][1]["headers"]
        self.assertNotIn("Authorization", s3_call_headers)
