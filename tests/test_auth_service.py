"""
Unit tests for YouTube Authentication Service.
"""

import unittest
from unittest.mock import MagicMock, patch

from vyntra.services.auth_service import auth_service


class TestAuthService(unittest.TestCase):
    """Test suite for AuthService facade."""

    def test_connection_status_disconnected(self):
        """Verify initial / disconnected state."""
        auth_service.disconnect()
        status_key, label, details = auth_service.get_connection_status()
        self.assertEqual(status_key, "disconnected")
        self.assertIn("Guest", label)

    def test_error_translation(self):
        """Verify raw exceptions are translated into clear guidance."""
        bot_err = Exception("ERROR: [youtube] Obvg5jVCvxc: Sign in to confirm you’re not a bot.")
        msg = auth_service.translate_error(bot_err)
        self.assertIn("sign-in verification", msg.lower())
        self.assertIn("google account", msg.lower())

        priv_err = Exception("ERROR: [youtube] 12345: Private video")
        msg_priv = auth_service.translate_error(priv_err)
        self.assertIn("private", msg_priv.lower())


if __name__ == "__main__":
    unittest.main()
