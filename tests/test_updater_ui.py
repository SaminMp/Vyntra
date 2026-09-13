"""
Unit tests for updater UI integration:
- UpdateModal dialog and progress reporting
- SettingsModal 'Check for Updates' section
- VyntraApp header update badge and footer terminal notification integration
"""

import unittest
from unittest.mock import MagicMock, patch
import customtkinter as ctk

from vyntra.ui.app import VyntraApp
from vyntra.ui.views.settings_modal import SettingsModal
from vyntra.ui.views.update_modal import UpdateModal
from vyntra.updater.models import DownloadProgress, ReleaseAsset, ReleaseInfo, UpdateCheckResult


class TestUpdaterUI(unittest.TestCase):
    """Verifies update modal, settings modal, and app badge behavior."""

    def test_update_modal_initialization_and_progress(self):
        """Verifies UpdateModal renders release details and responds to progress updates."""
        root = ctk.CTk()
        root.withdraw()
        try:
            asset = ReleaseAsset(
                name="Vyntra-Windows-x64.exe",
                download_url="http://mock.test/Vyntra.exe",
                size=50 * 1024 * 1024,
            )
            rel_info = ReleaseInfo(
                version="1.2.4",
                tag="v1.2.4",
                name="Vyntra v1.2.4",
                release_notes="* Added auto updates\n* Performance fixes",
                published_at="2026-09-14",
                assets=[asset],
            )
            check_res = UpdateCheckResult(
                status="available",
                current_version="1.1.3",
                latest_release=rel_info,
                target_asset=asset,
            )

            modal = UpdateModal(root, check_result=check_res)
            root.update_idletasks()

            # Verify notes content
            notes_content = modal.notes_box.get("1.0", "end")
            self.assertIn("Added auto updates", notes_content)

            # Test progress update callback
            prog = DownloadProgress(
                downloaded_bytes=25 * 1024 * 1024,
                total_bytes=50 * 1024 * 1024,
                percent=50.0,
                speed_bps=5 * 1024 * 1024,
                status_text="Downloading...",
            )
            modal._on_download_progress(prog)
            root.update()

            self.assertEqual(modal.progress_bar.get(), 0.5)
            self.assertIn("50%", modal.status_label.cget("text"))

            modal.destroy()
        finally:
            root.destroy()

    def test_settings_modal_has_update_section(self):
        """Verifies SettingsModal includes the Updates section and check button."""
        root = ctk.CTk()
        root.withdraw()
        try:
            settings = SettingsModal(root)
            root.update()

            self.assertTrue(hasattr(settings, "check_updates_btn"))
            self.assertTrue(hasattr(settings, "updater_ver_lbl"))
            self.assertIn("Installed Version", settings.updater_ver_lbl.cget("text"))

            settings.destroy()
        finally:
            root.destroy()

    def test_app_shows_update_badge_when_available(self):
        """Verifies VyntraApp maps update_badge_btn when an update is available."""
        app = VyntraApp()
        try:
            app.update()
            # Initially hidden
            self.assertEqual(app.update_badge_btn.winfo_manager(), "")

            asset = ReleaseAsset(
                name="Vyntra-Windows-x64.exe",
                download_url="http://mock.test/Vyntra.exe",
                size=50 * 1024 * 1024,
            )
            rel_info = ReleaseInfo(
                version="1.2.5",
                tag="v1.2.5",
                name="Vyntra v1.2.5",
                release_notes="Notes",
                published_at="2026-09-14",
                assets=[asset],
            )
            res = UpdateCheckResult(
                status="available",
                current_version="1.1.3",
                latest_release=rel_info,
                target_asset=asset,
            )

            app._handle_update_result(res)
            app.update()

            # Now mapped and showing version
            self.assertEqual(app.update_badge_btn.winfo_manager(), "pack")
            self.assertIn("v1.2.5", app.update_badge_btn.cget("text"))

            # Verify terminal received notice
            terminal_text = app.footer_terminal.textbox.get("1.0", "end")
            self.assertIn("New version v1.2.5 available", terminal_text)
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
