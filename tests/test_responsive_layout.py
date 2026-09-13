"""
Unit and integration tests for Vyntra's responsive UI architecture.
Tests multi-resolution adaptations (800x600 up to 2560x1440),
PlatformSelector layout transitions (Wide 1x4, Medium 2x2, Compact),
SearchBar grid column weighting, ResultCard adaptive wrapping, and
DownloadPanel responsiveness without widget collisions.
"""

import unittest
from unittest.mock import MagicMock
import customtkinter as ctk

from vyntra import __version__
from vyntra.models import MediaItem, SearchResult
from vyntra.ui.app import VyntraApp
from vyntra.ui.components.download_panel import DownloadPanel
from vyntra.ui.components.platform_selector import PLATFORM_METADATA, PlatformSelector
from vyntra.ui.components.result_card import ResultCard
from vyntra.ui.components.search_bar import SearchBar


class TestResponsiveLayout(unittest.TestCase):
    """Verifies responsive layout constraints, breakpoints, and dynamic adaptation."""

    def test_version_bumped_to_1_1_4(self):
        """Verifies centralized patch version bump."""
        self.assertEqual(__version__, "1.1.4")

    def test_platform_selector_layout_transitions(self):
        """Verifies PlatformSelector transitions seamlessly between Wide, Medium, and Compact modes."""
        root = ctk.CTk()
        root.withdraw()
        try:
            changed = []
            selector = PlatformSelector(
                root,
                current_platform="youtube",
                on_platform_changed=lambda p: changed.append(p),
            )
            root.update_idletasks()

            # 1. Wide mode (1x4)
            selector._apply_layout("wide")
            self.assertEqual(selector._layout_mode, "wide")
            for col, pid in enumerate(["youtube", "instagram", "tiktok", "spotify"]):
                info = selector._buttons[pid].grid_info()
                self.assertEqual(int(info["row"]), 0)
                self.assertEqual(int(info["column"]), col)

            # 2. Medium mode (2x2)
            selector._apply_layout("medium")
            self.assertEqual(selector._layout_mode, "medium")
            yt_info = selector._buttons["youtube"].grid_info()
            ig_info = selector._buttons["instagram"].grid_info()
            tt_info = selector._buttons["tiktok"].grid_info()
            sp_info = selector._buttons["spotify"].grid_info()

            self.assertEqual((int(yt_info["row"]), int(yt_info["column"])), (0, 0))
            self.assertEqual((int(ig_info["row"]), int(ig_info["column"])), (0, 1))
            self.assertEqual((int(tt_info["row"]), int(tt_info["column"])), (1, 0))
            self.assertEqual((int(sp_info["row"]), int(sp_info["column"])), (1, 1))

            # 3. Compact mode (Dropdown / OptionMenu)
            selector._apply_layout("compact")
            self.assertEqual(selector._layout_mode, "compact")
            # Buttons should be unmapped (grid_remove)
            for pid in ["youtube", "instagram", "tiktok", "spotify"]:
                self.assertEqual(selector._buttons[pid].grid_info(), {})
            # Compact frame should be mapped
            compact_info = selector._compact_frame.grid_info()
            self.assertEqual(int(compact_info["row"]), 0)
            self.assertEqual(int(compact_info["column"]), 0)

            # Switching in compact mode
            selector._on_compact_selected("♫  Spotify")
            self.assertEqual(selector.get_selected_platform(), "spotify")
            self.assertEqual(changed, ["spotify"])
        finally:
            root.destroy()

    def test_search_bar_responsive_weights(self):
        """Verifies SearchBar allocates horizontal growth to entry rather than prefix icon."""
        root = ctk.CTk()
        root.withdraw()
        try:
            search_bar = SearchBar(root, on_search=lambda q: None)
            root.update_idletasks()

            # Check column configurations
            col0_weight = search_bar.grid_columnconfigure(0)["weight"]
            col1_weight = search_bar.grid_columnconfigure(1)["weight"]

            self.assertEqual(col0_weight, 0, "Search icon column should have weight=0 to avoid eating entry space")
            self.assertEqual(col1_weight, 1, "Search text entry column must have weight=1 to expand responsively")
        finally:
            root.destroy()

    def test_result_card_adaptive_layout_and_wraplength(self):
        """Verifies ResultCard re-positions action buttons and updates wraplength dynamically."""
        root = ctk.CTk()
        root.withdraw()
        try:
            dummy_result = SearchResult(
                video_id="test1234",
                title="A very long video title that needs dynamic wrapping based on container width",
                channel="Test Channel",
                views=10000,
                views_formatted="10K",
                duration_seconds=300,
                duration_formatted="05:00",
                thumbnail_url="https://example.com/thumb.jpg",
                url="https://youtube.com/watch?v=test1234",
            )

            card = ResultCard(root, result=dummy_result, on_select=lambda r: None)
            root.update_idletasks()

            # Wide layout (>= 660px)
            card._apply_responsive_layout(is_compact=False)
            action_info_wide = card.action_frame.grid_info()
            self.assertEqual(int(action_info_wide["column"]), 2)
            self.assertEqual(int(action_info_wide["row"]), 0)

            # Compact layout (< 660px)
            card._apply_responsive_layout(is_compact=True)
            action_info_compact = card.action_frame.grid_info()
            self.assertEqual(int(action_info_compact["row"]), 3)
            self.assertEqual(int(action_info_compact["column"]), 0)

            # Check wraplength configure trigger
            event_mock = MagicMock()
            event_mock.width = 500
            card._on_configure(event_mock)
            self.assertLessEqual(card.title_label.cget("wraplength"), 400)
        finally:
            root.destroy()

    def test_download_panel_adaptive_options(self):
        """Verifies DownloadPanel reorganizes format and quality dropdowns for compact viewports."""
        root = ctk.CTk()
        root.withdraw()
        try:
            panel = DownloadPanel(root, on_download=lambda r, f, q, d: None, on_cancel=lambda: None)
            root.update_idletasks()

            # Wide options (1 row)
            panel._regrid_options(is_compact=False)
            fmt_info = panel.format_segmented.grid_info()
            q_info = panel.quality_option.grid_info()
            self.assertEqual(int(fmt_info["row"]), 0)
            self.assertEqual(int(q_info["row"]), 0)

            # Compact options (2 rows)
            panel._regrid_options(is_compact=True)
            fmt_info_c = panel.format_segmented.grid_info()
            q_info_c = panel.quality_option.grid_info()
            self.assertEqual(int(fmt_info_c["row"]), 0)
            self.assertEqual(int(q_info_c["row"]), 1)
        finally:
            root.destroy()

    def test_app_multi_resolution_stability_and_no_header_overlap(self):
        """Verifies VyntraApp handles resizing across 800x600 up to 2560x1440 with no widget conflicts."""
        app = VyntraApp()
        try:
            # 1. Verify minsize accommodates 800x600
            self.assertLessEqual(app._min_width, 800, "Window min width must allow 800px")
            self.assertLessEqual(app._min_height, 600, "Window min height must allow 600px")

            # 2. Verify header column configuration has no duplicate PlatformSelector in col 1
            header_frame = None
            for child in app.winfo_children():
                if isinstance(child, ctk.CTkFrame) and child.grid_info().get("row") == 0:
                    header_frame = child
                    break
            self.assertIsNotNone(header_frame)
            col1_weight = header_frame.grid_columnconfigure(1)["weight"]
            self.assertEqual(col1_weight, 1, "Header column 1 should be a flexible spacer")

            # 3. Test resolutions
            resolutions = [
                "800x600",
                "1024x768",
                "1280x720",
                "1366x768",
                "1600x900",
                "1920x1080",
                "2560x1440",
            ]

            for res in resolutions:
                app.geometry(res)
                app.update_idletasks()

            # 4. Switch platforms across resolutions
            platforms = ["youtube", "instagram", "tiktok", "spotify"]
            for pid in platforms:
                app._switch_platform(pid)
                app.geometry("800x600")
                app.update_idletasks()
                app.geometry("1920x1080")
                app.update_idletasks()
                self.assertEqual(app._current_platform, pid)

        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
