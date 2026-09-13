"""
Regression and lifecycle tests for Vyntra UI components, executors, and event loops.
Ensures zero orphaned Tk callbacks, clean executor shutdowns, and no thread leaks.
"""

import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import customtkinter as ctk

from vyntra.services.download_service import download_service
from vyntra.services.image_service import image_service
from vyntra.services.search_service import search_service
from vyntra.platforms.registry import platform_registry
from vyntra.ui.app import VyntraApp
from vyntra.ui.views.setup_wizard import SetupWizard
from vyntra.ui.views.update_modal import UpdateModal
from vyntra.updater.models import ReleaseAsset, ReleaseInfo, UpdateCheckResult
from vyntra.utils.logger import logger


class TestLifecycleAndShutdown(unittest.TestCase):
    """Verifies that all widgets and services uphold strict disposal contracts."""

    def test_app_dispose_unhooks_log_bridge_and_cancels_callbacks(self):
        """Verify VyntraApp.dispose() unhooks log bridge, listeners, and cancels pending after IDs."""
        app = VyntraApp()
        app.withdraw()
        try:
            # Verify bridge was added to logger
            bridge = app._log_bridge
            self.assertIn(bridge, logger.handlers)
            self.assertTrue(len(app._tracked_after_ids) > 0)

            # Dispose app
            app.dispose()
            self.assertTrue(app._is_disposed)

            # Bridge must be completely removed from root logger
            self.assertNotIn(bridge, logger.handlers)
            self.assertEqual(len(app._tracked_after_ids), 0)

            # Subsequent logging must NOT raise any exceptions or trigger callbacks
            logger.info("Test log after application disposal")
            logger.warning("Another warning message")

        finally:
            app.destroy()

    def test_direct_destroy_runs_disposal(self):
        """Verify that directly calling app.destroy() runs disposal without errors."""
        app = VyntraApp()
        app.withdraw()
        bridge = app._log_bridge

        app.destroy()
        self.assertTrue(app._is_disposed)
        self.assertNotIn(bridge, logger.handlers)

    def test_setup_wizard_timers_purged_on_destroy(self):
        """Verify SetupWizard cancels any scheduled after timers on destroy."""
        root = ctk.CTk()
        root.withdraw()
        try:
            wizard = SetupWizard(root)
            wizard.withdraw()
            root.update_idletasks()

            wizard.destroy()
            root.update_idletasks()
            # If timers remained on root or children, active timer count would be non-zero
            active_timers = root.tk.splitlist(root.tk.eval("after info"))
            self.assertEqual(len(active_timers), 0)
        finally:
            root.destroy()

    def test_update_modal_progress_callback_safe_after_destroy(self):
        """Verify progress updates dispatched to destroyed UpdateModal do not throw TclError."""
        root = ctk.CTk()
        root.withdraw()
        try:
            check_res = UpdateCheckResult(
                status="available",
                current_version="1.0.0",
                latest_release=ReleaseInfo(version="1.1.0", tag="v1.1.0", name="v1.1.0", release_notes="", published_at=""),
                target_asset=ReleaseAsset(name="pkg.zip", download_url="http://localhost", size=100),
            )
            modal = UpdateModal(root, check_result=check_res)
            modal.withdraw()
            root.update_idletasks()

            # Destroy modal
            modal.destroy()
            root.update_idletasks()

            # Simulating late download error or progress hook
            modal._on_download_error("Network timeout")
            root.update_idletasks()
        finally:
            root.destroy()

    def test_service_executors_shutdown_and_leave_no_non_daemon_threads(self):
        """Verify that all services cleanly shut down their worker threads."""
        # Ensure executors are active
        image_service._ensure_executor()
        download_service._ensure_executor()
        search_service._ensure_executor()

        # Trigger shutdown
        image_service.shutdown(wait=True)
        download_service.shutdown(wait=True)
        search_service.shutdown(wait=True)
        platform_registry.shutdown_all(wait=True)

        # Check for rogue worker threads
        threads = threading.enumerate()
        worker_names = [
            t.name for t in threads
            if any(p in t.name for p in ("ThumbnailWorker", "DownloadWorker", "SearchWorker", "Worker"))
            and not t.daemon
        ]
        self.assertEqual(worker_names, [], f"Non-daemon worker threads still alive: {worker_names}")


if __name__ == "__main__":
    unittest.main()
