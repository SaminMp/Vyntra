"""
Unit tests for USDT Donation modal dialog and app integration:
- DonationModal UI elements, wallet address accuracy, and clipboard copying
- Preference persistence ("Don't show this again")
- SettingsModal donation section integration
- VyntraApp header support button and download prompt triggering
"""

import unittest
from unittest.mock import patch
import customtkinter as ctk

from vyntra.config import config_manager
from vyntra.ui.app import VyntraApp
from vyntra.ui.views.donation_modal import DonationModal, USDT_WALLET_ADDRESS
from vyntra.ui.views.settings_modal import SettingsModal


class TestDonationModal(unittest.TestCase):
    """Verifies DonationModal behavior, wallet address, and clipboard interaction."""

    def test_donation_modal_initialization_and_wallet_address(self):
        """Verifies DonationModal renders expected USDT address and networks."""
        root = ctk.CTk()
        root.withdraw()
        try:
            modal = DonationModal(root)
            modal.withdraw()
            root.update_idletasks()

            self.assertEqual(modal.address_label.cget("text"), "0x9B3493BF0459BAE41B39AbBF0BCdBb9C76699eE7")
            self.assertEqual(USDT_WALLET_ADDRESS, "0x9B3493BF0459BAE41B39AbBF0BCdBb9C76699eE7")
            self.assertTrue(hasattr(modal, "copy_btn"))
            self.assertTrue(hasattr(modal, "dont_show_checkbox"))
            self.assertTrue(hasattr(modal, "close_btn"))

            modal.destroy()
        finally:
            root.destroy()

    def test_copy_wallet_address_interaction(self):
        """Verifies clicking copy updates button text to indicate copied status."""
        root = ctk.CTk()
        root.withdraw()
        try:
            modal = DonationModal(root)
            modal.withdraw()
            root.update_idletasks()

            modal._copy_wallet_address()
            self.assertIn("Copied", modal.copy_btn.cget("text"))

            modal.destroy()
        finally:
            root.destroy()

    def test_dont_show_again_persists_to_config(self):
        """Verifies toggling 'Don't show again' checkbox persists to config."""
        root = ctk.CTk()
        root.withdraw()
        initial_val = config_manager.config.donation_prompt_dismissed
        try:
            modal = DonationModal(root)
            modal.withdraw()
            root.update_idletasks()

            modal._dont_show_var.set(True)
            modal._on_toggle_dont_show()
            self.assertTrue(config_manager.config.donation_prompt_dismissed)

            modal._dont_show_var.set(False)
            modal._on_toggle_dont_show()
            self.assertFalse(config_manager.config.donation_prompt_dismissed)

            modal.destroy()
        finally:
            config_manager.update(donation_prompt_dismissed=initial_val)
            root.destroy()

    def test_settings_modal_has_donation_section(self):
        """Verifies SettingsModal includes a Support section with donate button and prompt toggle."""
        root = ctk.CTk()
        root.withdraw()
        try:
            settings = SettingsModal(root)
            settings.withdraw()
            root.update_idletasks()

            self.assertTrue(hasattr(settings, "donate_btn"))
            self.assertTrue(hasattr(settings, "donation_prompt_chk"))
            self.assertEqual(settings.donate_btn.cget("text"), "Support with USDT")

            settings.destroy()
        finally:
            root.destroy()

    def test_app_header_support_button_and_prompt_cooldown(self):
        """Verifies VyntraApp header contains support button and session cooldown works."""
        with patch.object(config_manager.config, "setup_completed", True):
            app = VyntraApp()
            app.withdraw()
            try:
                app.update_idletasks()
                self.assertTrue(hasattr(app, "support_btn"))
                self.assertEqual(app.support_btn.cget("text"), "💖 Support")

                # Test manual opening
                app._open_donation_modal(force=True)
                self.assertIsNotNone(app._donation_modal)
                self.assertTrue(app._donation_shown_this_session)

                # Dismissed check
                with patch.object(config_manager.config, "donation_prompt_dismissed", True):
                    app._donation_modal.destroy()
                    app._donation_modal = None
                    app._donation_shown_this_session = False
                    app._maybe_prompt_donation(trigger="download")
                    # Should not open because dismissed
                    self.assertIsNone(app._donation_modal)

                # Session cooldown check
                with patch.object(config_manager.config, "donation_prompt_dismissed", False):
                    app._donation_shown_this_session = True
                    app._maybe_prompt_donation(trigger="download")
                    # Should not open because already shown this session
                    self.assertIsNone(app._donation_modal)
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
