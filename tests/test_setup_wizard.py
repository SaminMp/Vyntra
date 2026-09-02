"""
Unit tests for Initial Setup Wizard and Account Modal.
"""

from pathlib import Path
import tempfile
import unittest
import customtkinter as ctk

from vyntra.config import ConfigManager, config_manager
from vyntra.services.auth_service import auth_service
from vyntra.ui.views.account_modal import AccountModal
from vyntra.ui.views.setup_wizard import SetupWizard


class TestSetupWizard(unittest.TestCase):
    """Test suite for setup wizard and account management modals."""

    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_setup_wizard_steps(self):
        """Verify setup wizard transitions through all 4 steps without errors."""
        completed_flags = []
        wizard = SetupWizard(self.root, on_completed=lambda: completed_flags.append(True))

        self.assertEqual(wizard._current_step, 1)

        wizard._show_step(2)
        self.assertEqual(wizard._current_step, 2)

        wizard._show_step(3)
        self.assertEqual(wizard._current_step, 3)

        wizard._show_step(4)
        self.assertEqual(wizard._current_step, 4)

        wizard._complete_setup()
        self.assertEqual(len(completed_flags), 1)
        self.assertTrue(config_manager.config.setup_completed)

    def test_account_modal(self):
        """Verify AccountModal builds and displays connection status."""
        modal = AccountModal(self.root)
        self.assertIsNotNone(modal.status_title)
        self.assertIsNotNone(modal.signin_btn)
        self.assertIsNotNone(modal.signout_btn)
        modal.destroy()

    def test_auth_service_connect_disconnect(self):
        """Verify auth service connect and disconnect state transitions."""
        auth_service.disconnect()
        status_key, label, _ = auth_service.get_connection_status()
        self.assertEqual(status_key, "disconnected")
        self.assertIn("Guest", label)


if __name__ == "__main__":
    unittest.main()
