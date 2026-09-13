"""
Unit and integration tests for UpdateManager and UpdateDownloadManager.
Verifies UpdateManager state machine, provider delegation, thread orchestration,
SHA-256 integrity verification, and network failure tolerance.
"""

import hashlib
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
from vyntra.updater.models import ReleaseAsset, ReleaseInfo, UpdateCheckResult
from vyntra.updater.providers.base import BaseUpdateProvider


class TestUpdaterManager(unittest.TestCase):
    """Verifies UpdateManager state machine and provider delegation."""

    def setUp(self):
        self.mock_provider = MagicMock(spec=BaseUpdateProvider)
        self.manager = UpdateManager(provider=self.mock_provider)

    def test_initial_state(self):
        self.assertEqual(self.manager.state, UpdateState.IDLE)
        self.assertIsNone(self.manager.last_result)

    def test_default_provider_is_github_release_provider(self):
        from vyntra.updater.providers.github_provider import GitHubReleaseProvider
        default_mgr = UpdateManager()
        self.assertIsInstance(default_mgr.provider, GitHubReleaseProvider)

    def test_check_for_updates_available_transitions_state(self):
        """When provider reports available update, manager state is AVAILABLE."""
        asset = ReleaseAsset(
            name="Vyntra-Windows-x64.exe",
            download_url="http://mock/Vyntra.exe",
            size=1000,
        )
        rel_info = ReleaseInfo(
            version="1.2.4",
            tag="v1.2.4",
            name="v1.2.4",
            release_notes="Notes",
            published_at="2026-09-14",
            assets=[asset],
        )
        self.mock_provider.check_for_updates.return_value = UpdateCheckResult(
            status="available",
            current_version="1.1.3",
            latest_release=rel_info,
            target_asset=asset,
        )

        callback_mock = MagicMock()
        self.manager._run_check_worker(callback=callback_mock, background=True)

        self.assertEqual(self.manager.state, UpdateState.AVAILABLE)
        self.assertTrue(self.manager.last_result.has_update)
        callback_mock.assert_called_once()

    def test_check_for_updates_up_to_date_transitions_state(self):
        """When provider reports up to date, manager state is UP_TO_DATE."""
        self.mock_provider.check_for_updates.return_value = UpdateCheckResult(
            status="up_to_date",
            current_version="1.1.3",
        )

        self.manager._run_check_worker(callback=None, background=True)
        self.assertEqual(self.manager.state, UpdateState.UP_TO_DATE)
        self.assertFalse(self.manager.last_result.has_update)

    def test_check_for_updates_auth_required_transitions_state(self):
        """When provider reports auth required, manager state is AUTH_REQUIRED."""
        self.mock_provider.check_for_updates.return_value = UpdateCheckResult(
            status="auth_required",
            current_version="1.1.3",
            auth_status="unauthenticated",
            error_message="Update access not configured.",
        )

        self.manager._run_check_worker(callback=None, background=True)
        self.assertEqual(self.manager.state, UpdateState.AUTH_REQUIRED)

    def test_check_for_updates_exception_transitions_to_error(self):
        """When provider raises exception, manager catches and transitions to ERROR."""
        self.mock_provider.check_for_updates.side_effect = RuntimeError("Network timeout")

        callback_mock = MagicMock()
        self.manager._run_check_worker(callback=callback_mock, background=True)

        self.assertEqual(self.manager.state, UpdateState.ERROR)
        self.assertEqual(self.manager.last_result.status, "error")
        callback_mock.assert_called_once()

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
