"""
Unit tests for FooterTerminal component and its integration into VyntraApp.
Verifies that notifications and operational logs appear in the footer terminal,
and that platform navigation buttons on row 1 are never obscured or overlapped.
"""

import unittest
from unittest.mock import MagicMock
import customtkinter as ctk

from vyntra.ui.app import VyntraApp
from vyntra.ui.components.footer_terminal import FooterTerminal
from vyntra.ui.components.status_banner import StatusBanner


class TestFooterTerminal(unittest.TestCase):
    """Verifies FooterTerminal behavior and backward compatibility."""

    def test_status_banner_alias(self):
        """Verifies StatusBanner is an alias to FooterTerminal."""
        self.assertIs(StatusBanner, FooterTerminal)

    def test_terminal_basic_operations(self):
        """Verifies logging, badge states, and buffer clearing."""
        root = ctk.CTk()
        root.withdraw()
        try:
            terminal = FooterTerminal(root)
            root.update_idletasks()

            # Initial state
            self.assertIn("READY", terminal.status_badge.cget("text"))

            # Test show_info
            terminal.show_info("Test information message")
            root.update_idletasks()
            self.assertEqual(terminal.summary_label.cget("text"), "Test information message")
            self.assertIn("READY", terminal.status_badge.cget("text"))

            # Test show_warning
            terminal.show_warning("Warning: high memory usage")
            root.update_idletasks()
            self.assertEqual(terminal.summary_label.cget("text"), "Warning: high memory usage")
            self.assertIn("ALERT", terminal.status_badge.cget("text"))

            # Test show_error with action callback
            action_mock = MagicMock()
            terminal.show_error("Download error occurred", action_text="Retry", on_action=action_mock)
            root.update_idletasks()
            self.assertEqual(terminal.summary_label.cget("text"), "Download error occurred")
            self.assertIn("ERROR", terminal.status_badge.cget("text"))
            self.assertEqual(terminal.action_btn.cget("text"), "Retry")

            # Trigger action button
            terminal._on_action_clicked()
            action_mock.assert_called_once()

            # Test clear
            terminal.clear()
            root.update_idletasks()
            self.assertIn("READY", terminal.status_badge.cget("text"))
            self.assertEqual(terminal.summary_label.cget("text"), "Terminal buffer cleared.")

            # Test collapse / expand
            self.assertFalse(terminal._is_collapsed)
            terminal.toggle_collapse()
            self.assertTrue(terminal._is_collapsed)
            self.assertEqual(terminal.toggle_btn.cget("text"), "▲ Expand")

            terminal.toggle_collapse()
            self.assertFalse(terminal._is_collapsed)
            self.assertEqual(terminal.toggle_btn.cget("text"), "▼ Minimize")
        finally:
            root.destroy()

    def test_app_footer_terminal_does_not_obscure_navigation(self):
        """Verifies that in VyntraApp, notifications do NOT obscure or grid over platform navigation."""
        app = VyntraApp()
        try:
            # Check row configuration
            # row 0: Header
            # row 1: Platform Navigation
            # row 2: Page Container (weight=1)
            # row 3: Footer Terminal
            nav_frame = None
            for child in app.winfo_children():
                info = child.grid_info()
                if info.get("row") == 1:
                    nav_frame = child
                    break

            self.assertIsNotNone(nav_frame, "Navigation frame must be on row 1")
            self.assertIsNotNone(app.footer_terminal, "FooterTerminal must exist")

            terminal_row = int(app.footer_terminal.grid_info().get("row", -1))
            self.assertEqual(terminal_row, 3, "Footer terminal must reside permanently on row 3")

            pages_row = int(app.pages_container.grid_info().get("row", -1))
            self.assertEqual(pages_row, 2, "Pages container must reside on row 2")

            # Verify navigation frame is mapped with grid
            app.update_idletasks()
            self.assertEqual(nav_frame.winfo_manager(), "grid")
            self.assertEqual(int(nav_frame.grid_info()["row"]), 1)

            # Fire notifications of various types
            app.status_banner.show_error("Testing unexpected extraction failure")
            app.update_idletasks()

            # Verify nav_frame row is still 1 and still gridded
            self.assertEqual(nav_frame.winfo_manager(), "grid")
            self.assertEqual(int(nav_frame.grid_info()["row"]), 1)

            # Fire success notification
            app.status_banner.show_success("Finished downloading test track!")
            app.update_idletasks()

            self.assertEqual(nav_frame.winfo_manager(), "grid")
            self.assertEqual(int(nav_frame.grid_info()["row"]), 1)

            # Verify terminal received the messages in its text box
            terminal_text = app.footer_terminal.textbox.get("1.0", "end")
            self.assertIn("Testing unexpected extraction failure", terminal_text)
            self.assertIn("Finished downloading test track!", terminal_text)

        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
