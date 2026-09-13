"""
Unit tests for UpdaterAuthManager.
Tests secure credential retrieval, OS Keyring storage, token validation with GitHub,
and least-privilege permission verification.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from vyntra.updater.auth_manager import UpdaterAuthManager


class TestUpdaterAuthManager(unittest.TestCase):
    """Verifies UpdaterAuthManager secure storage and verification flows."""

    def setUp(self):
        self.auth_mgr = UpdaterAuthManager()

    def test_get_token_from_env(self):
        """VYNTRA_UPDATE_TOKEN environment variable takes precedence if set."""
        with patch.dict(os.environ, {"VYNTRA_UPDATE_TOKEN": "ghp_mock_env_token"}):
            token = self.auth_mgr.get_token()
            self.assertEqual(token, "ghp_mock_env_token")
            self.assertTrue(self.auth_mgr.is_configured())

    @patch("keyring.get_password")
    def test_get_token_from_keyring(self, mock_keyring_get):
        """Falls back to OS Keyring when env var is unset."""
        mock_keyring_get.return_value = "github_pat_stored_in_keychain"
        with patch.dict(os.environ, {}, clear=True):
            token = self.auth_mgr.get_token()
            self.assertEqual(token, "github_pat_stored_in_keychain")
            self.assertTrue(self.auth_mgr.is_configured())
            mock_keyring_get.assert_called_with("Vyntra_GitHub_Update_Auth", "update_access_token")

    @patch("keyring.get_password")
    def test_not_configured_when_no_token_present(self, mock_keyring_get):
        mock_keyring_get.return_value = None
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(self.auth_mgr.get_token())
            self.assertFalse(self.auth_mgr.is_configured())

    @patch("keyring.set_password")
    def test_set_token_persists_to_keyring(self, mock_keyring_set):
        ok = self.auth_mgr.set_token("github_pat_12345")
        self.assertTrue(ok)
        mock_keyring_set.assert_called_once_with(
            "Vyntra_GitHub_Update_Auth",
            "update_access_token",
            "github_pat_12345",
        )

    @patch("keyring.delete_password")
    def test_delete_token_removes_from_keyring(self, mock_keyring_del):
        ok = self.auth_mgr.delete_token()
        self.assertTrue(ok)
        mock_keyring_del.assert_called_once_with(
            "Vyntra_GitHub_Update_Auth",
            "update_access_token",
        )

    @patch("requests.get")
    def test_verify_token_with_github_success(self, mock_get):
        """Verifies read access to private repo via 200 OK."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "name": "Vyntra",
            "private": True,
            "permissions": {"pull": True, "push": False, "admin": False},
        }
        mock_get.return_value = mock_resp

        success, msg, perms = self.auth_mgr.verify_token_with_github("ghp_test_token")
        self.assertTrue(success)
        self.assertIn("verified", msg.lower())

        # Ensure correct Authorization header was passed
        mock_get.assert_called_once()
        headers = mock_get.call_args[1]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer ghp_test_token")

    @patch("requests.get")
    def test_verify_token_with_github_rejected_unauthorized(self, mock_get):
        """Verifies 401 returns failure message."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"message": "Bad credentials"}
        mock_get.return_value = mock_resp

        success, msg, _ = self.auth_mgr.verify_token_with_github("ghp_invalid_token")
        self.assertFalse(success)
        self.assertIn("failed", msg.lower())

    @patch("requests.get")
    def test_verify_token_with_github_forbidden(self, mock_get):
        """Verifies 403 returns insufficient permission message."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {"message": "Resource not accessible by personal access token"}
        mock_get.return_value = mock_resp

        success, msg, _ = self.auth_mgr.verify_token_with_github("ghp_no_scope_token")
        self.assertFalse(success)
        self.assertIn("forbidden", msg.lower())

    @patch("requests.get")
    def test_verify_token_with_github_repo_not_found(self, mock_get):
        """Verifies 404 indicates token lacks access to private repository."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        success, msg, _ = self.auth_mgr.verify_token_with_github("ghp_outsider_token")
        self.assertFalse(success)
        self.assertIn("not found", msg.lower())
