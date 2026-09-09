"""
Unit tests for YouTubeAuthManager (Native Desktop OAuth 2.0 and OS Keyring).
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from vyntra.services.auth_manager import YouTubeAuthManager, auth_manager


class TestYouTubeAuthManager(unittest.TestCase):
    """Test suite for YouTubeAuthManager."""

    def test_pkce_generation(self):
        """Verify PKCE code_verifier and code_challenge format."""
        manager = YouTubeAuthManager()
        verifier, challenge = manager._generate_pkce()
        self.assertGreater(len(verifier), 40)
        self.assertGreater(len(challenge), 20)
        self.assertNotIn("=", challenge)

    def test_keyring_persistence(self):
        """Verify credentials save, load, and delete lifecycle with mocked keyring."""
        manager = YouTubeAuthManager()
        mock_storage = {}

        def mock_set(service, username, password):
            mock_storage[f"{service}:{username}"] = password

        def mock_get(service, username):
            return mock_storage.get(f"{service}:{username}")

        def mock_delete(service, username):
            mock_storage.pop(f"{service}:{username}", None)

        with patch("keyring.set_password", side_effect=mock_set), \
             patch("keyring.get_password", side_effect=mock_get), \
             patch("keyring.delete_password", side_effect=mock_delete):

            test_data = {
                "client_id": "test_id",
                "client_secret": "test_sec",
                "access_token": "ya29.test_token_123",
                "refresh_token": "1//test_refresh_456",
                "expires_at": time.time() + 3600,
                "profile": {"email": "test@example.com", "name": "Test User"},
            }

            manager._save_to_keyring(test_data)
            self.assertTrue(len(mock_storage) > 0)

            loaded = manager.load_credentials()
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["access_token"], "ya29.test_token_123")
            self.assertTrue(manager.is_authenticated())

            manager.logout()
            self.assertFalse(manager.is_authenticated())
            self.assertIsNone(manager.get_user_profile())

    def test_test_connection_disconnected(self):
        """Verify test_connection returns proper message when not signed in."""
        manager = YouTubeAuthManager()
        manager.logout()
        success, msg = manager.test_connection()
        self.assertFalse(success)
        self.assertIn("Not signed in", msg)

    def test_client_id_masking(self):
        """Verify client ID masking safely obscures sensitive parts."""
        from vyntra.developer_config import mask_client_id
        self.assertEqual(mask_client_id(""), "<none>")
        masked = mask_client_id("1048123984712-k9m8j7h6g5f4e3d2c1b0a9z8y7x6w5v4.apps.googleusercontent.com")
        self.assertTrue(masked.startswith("104812"))
        self.assertTrue(masked.endswith(".apps.googleusercontent.com"))
        self.assertIn("...", masked)
        self.assertNotIn("k9m8j7h6g5f4e3d2c1b0a9z8y7x6w5v4", masked)


    def test_developer_oauth_config_resolution(self):
        """Verify developer oauth client loading resolution order."""
        from vyntra.developer_config import load_developer_oauth_client, BUILTIN_CLIENT_ID
        import os

        # 1. Test bundled default (when no env var)
        non_vyntra_env = {k: v for k, v in os.environ.items() if not k.startswith("VYNTRA_")}
        with patch.dict(os.environ, non_vyntra_env, clear=True):
            cid, sec, pid, source = load_developer_oauth_client()
            self.assertTrue(len(cid) > 10)
            self.assertIn(".apps.googleusercontent.com", cid)

        # 2. Test environment variable override
        test_env_id = "999999999999-customenvoverride.apps.googleusercontent.com"
        with patch.dict(os.environ, {"VYNTRA_GOOGLE_CLIENT_ID": test_env_id, "VYNTRA_GOOGLE_CLIENT_SECRET": "custom_sec"}):
            cid, sec, pid, source = load_developer_oauth_client()
            self.assertEqual(cid, test_env_id)
            self.assertEqual(sec, "custom_sec")
            self.assertIn("environment variable", source)

    def test_has_valid_client_id(self):
        """Verify has_valid_client_id returns True for properly configured clients."""
        manager = YouTubeAuthManager()
        self.assertTrue(manager.has_valid_client_id())

    def test_candidate_paths_resolution(self):
        """Verify get_candidate_credential_paths returns list of Paths without errors."""
        from vyntra.developer_config import get_candidate_credential_paths
        paths = get_candidate_credential_paths()
        self.assertIsInstance(paths, list)
        self.assertGreater(len(paths), 0)


if __name__ == "__main__":
    unittest.main()

