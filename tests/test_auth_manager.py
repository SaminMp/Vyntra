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


if __name__ == "__main__":
    unittest.main()
