"""
Unit and integration tests for SpotifyPage lifecycle safety,
ImageService async fetching, and prominent PlatformSelector redesign.
"""

import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
import customtkinter as ctk

from vyntra.models import AudioQuality, MediaFormat, MediaItem, Platform
from vyntra.services.image_service import image_service
from vyntra.ui.app import VyntraApp
from vyntra.ui.components.platform_selector import PLATFORM_METADATA, PlatformSelector
from vyntra.ui.pages import InstagramPage, SpotifyPage, TikTokPage, YouTubePage


class TestSpotifyAndPlatformSelector(unittest.TestCase):
    """Tests Spotify lifecycle, artwork loading, and navigation bar visibility."""

    def test_image_service_get_image_async(self):
        """Verifies ImageService.get_image_async handles cache, success, and error gracefully."""
        # 1. Test empty URL error handling
        error_called = []
        image_service.get_image_async(
            "",
            on_success=lambda img: None,
            on_error=lambda err: error_called.append(err),
        )
        self.assertTrue(len(error_called) > 0)
        self.assertIsInstance(error_called[0], ValueError)

        # 2. Test cached image retrieval
        test_pil = Image.new("RGBA", (50, 50), color=(255, 0, 0, 255))
        image_service._cache["https://test.example/cached.png"] = test_pil
        success_img = []
        image_service.get_image_async(
            "https://test.example/cached.png",
            on_success=lambda img: success_img.append(img),
        )
        self.assertTrue(len(success_img) > 0)
        self.assertEqual(success_img[0].size, (50, 50))

    def test_platform_selector_metadata_and_buttons(self):
        """Verifies that all 4 platforms are represented in PlatformSelector with prominent buttons."""
        root = ctk.CTk()
        try:
            changed_platforms = []
            selector = PlatformSelector(
                root,
                current_platform="youtube",
                on_platform_changed=lambda p: changed_platforms.append(p),
            )
            self.assertEqual(selector.get_selected_platform(), "youtube")

            # Verify buttons exist for all 4 platforms
            for pid in ["youtube", "instagram", "tiktok", "spotify"]:
                self.assertIn(pid, selector._buttons)
                btn = selector._buttons[pid]
                self.assertTrue(btn.winfo_exists())

            # Test switching platform updates internal selection and triggers callback
            selector._select_platform("spotify")
            self.assertEqual(selector.get_selected_platform(), "spotify")
            self.assertEqual(changed_platforms, ["spotify"])

            # Verify active button styling has bold/accent formatting
            spotify_btn = selector._buttons["spotify"]
            self.assertIn("Spotify", spotify_btn.cget("text"))
            self.assertEqual(spotify_btn.cget("border_width"), 2)
            self.assertEqual(spotify_btn.cget("border_color"), PLATFORM_METADATA["spotify"].accent_color)
        finally:
            root.destroy()

    def test_spotify_page_placeholder_preservation_across_multiple_searches(self):
        """Verifies that clearing or displaying search results never destroys placeholder_label."""
        app = VyntraApp()
        try:
            app._switch_platform("spotify")
            spotify_page = app._pages["spotify"]
            self.assertTrue(spotify_page.placeholder_label.winfo_exists())

            mock_items = [
                MediaItem(
                    video_id="track1",
                    title="Get Lucky",
                    channel="Daft Punk",
                    album="Random Access Memories",
                    duration_seconds=248,
                    duration_formatted="4:08",
                    thumbnail_url="https://test.example/art.jpg",
                    url="https://open.spotify.com/track/track1",
                    platform="spotify",
                ),
                MediaItem(
                    video_id="track2",
                    title="Starboy",
                    channel="The Weeknd",
                    album="Starboy",
                    duration_seconds=230,
                    duration_formatted="3:50",
                    thumbnail_url="",
                    url="https://open.spotify.com/track/track2",
                    platform="spotify",
                ),
            ]

            # 1. First search display
            gen1 = spotify_page.next_generation()
            spotify_page._display_results(mock_items, gen1)
            self.assertEqual(len(spotify_page._cards), 2)
            # placeholder_label MUST still exist and not be destroyed
            self.assertTrue(spotify_page.placeholder_label.winfo_exists())

            # 2. Second search query simulation
            spotify_page.search_entry.delete(0, "end")
            spotify_page.search_entry.insert(0, "New Search Query")
            # Clear cards directly
            spotify_page._clear_cards()
            self.assertEqual(len(spotify_page._cards), 0)
            self.assertTrue(spotify_page.placeholder_label.winfo_exists())

            # 3. Third search returning empty results
            gen2 = spotify_page.next_generation()
            spotify_page._display_results([], gen2)
            self.assertTrue(spotify_page.placeholder_label.winfo_exists())
            self.assertIn("No tracks found", spotify_page.placeholder_label.cget("text"))
        finally:
            app.destroy()

    def test_rapid_platform_switching_stability(self):
        """Verifies that switching platforms rapidly does not cause TclErrors or state leaks."""
        app = VyntraApp()
        try:
            cycle = ["youtube", "spotify", "tiktok", "instagram", "spotify", "youtube", "tiktok"]
            for target in cycle:
                app._switch_platform(target)
                self.assertEqual(app._current_platform, target)
                self.assertTrue(app._pages[target].is_page_active)

            # Confirm final state is intact
            self.assertEqual(app.platform_selector.get_selected_platform(), "tiktok")
            self.assertTrue(bool(app._pages["tiktok"].grid_info()))
        finally:
            app.destroy()

    def test_spotify_card_and_panel_action_buttons(self):
        """Verifies Spotify page panel action buttons and per-card Preview/Download/Select buttons."""
        app = VyntraApp()
        try:
            app._switch_platform("spotify")
            sp = app._pages["spotify"]
            app.update_idletasks()

            # Verify panel buttons exist and are placed on row 3, distinct from progress_frame (row 4)
            actions_info = sp.preview_btn.master.grid_info()
            progress_info = sp.progress_frame.grid_info()
            self.assertEqual(actions_info["row"], 3)
            # progress_frame should be configured on row 4 when gridded
            self.assertEqual(sp.progress_frame.grid_info().get("row", 4), 4)
            self.assertTrue(sp.preview_btn.winfo_exists())
            self.assertTrue(sp.download_mp3_btn.winfo_exists())
            self.assertIn("Download MP3", sp.download_mp3_btn.cget("text"))

            # Render a test track
            item = MediaItem(
                video_id="spot_1",
                title="Levitating",
                channel="Dua Lipa",
                album="Future Nostalgia",
                duration_seconds=203,
                duration_formatted="3:23",
                thumbnail_url="",
                url="https://open.spotify.com/track/spot_1",
                platform="spotify",
            )
            sp._display_results([item], sp.next_generation())
            app.update_idletasks()

            self.assertEqual(len(sp._cards), 1)
            card = sp._cards[0]

            # Find action buttons container in card
            action_frames = [w for w in card.winfo_children() if isinstance(w, ctk.CTkFrame)]
            self.assertTrue(len(action_frames) > 0)
            btn_texts = [b.cget("text") for b in action_frames[0].winfo_children() if isinstance(b, ctk.CTkButton)]

            # Check that Preview, Download, and Select buttons all exist on the card
            self.assertTrue(any("Preview" in t for t in btn_texts))
            self.assertTrue(any("Download" in t for t in btn_texts))
            self.assertTrue(any("Select" in t for t in btn_texts))

            # Check that Download checkbox and audio quality menu exist on the card
            checkboxes = [w for w in action_frames[0].winfo_children() if isinstance(w, ctk.CTkCheckBox)]
            option_menus = [w for w in action_frames[0].winfo_children() if isinstance(w, ctk.CTkOptionMenu)]
            self.assertEqual(len(checkboxes), 1)
            self.assertEqual(len(option_menus), 1)
            self.assertEqual(checkboxes[0].cget("text"), "Download")
            self.assertEqual(option_menus[0].get(), "320 kbps")
        finally:
            app.destroy()

    def test_spotify_multi_select_and_select_all(self):
        """Verifies multi-select checkboxes, Select All, Deselect All, and toolbar counter."""
        app = VyntraApp()
        try:
            app._switch_platform("spotify")
            sp = app._pages["spotify"]
            app.update_idletasks()

            items = [
                MediaItem(video_id="t1", title="Song 1", channel="Artist 1", platform="spotify", download_quality="320 kbps"),
                MediaItem(video_id="t2", title="Song 2", channel="Artist 2", platform="spotify", download_quality="320 kbps"),
                MediaItem(video_id="t3", title="Song 3", channel="Artist 3", platform="spotify", download_quality="320 kbps"),
            ]
            sp._display_results(items, sp.next_generation(), col_key="test_album")
            app.update_idletasks()

            # Initially none selected for download
            self.assertEqual(len(sp.get_selected_download_items()), 0)
            self.assertIn("0 selected for download", sp._selection_summary_lbl.cget("text"))
            self.assertEqual(sp.download_mp3_btn.cget("text"), "⬇ Download MP3")

            # Select All
            sp.select_all()
            app.update_idletasks()
            self.assertEqual(len(sp.get_selected_download_items()), 3)
            self.assertIn("3 selected for download", sp._selection_summary_lbl.cget("text"))
            self.assertEqual(sp.download_mp3_btn.cget("text"), "⬇ Download 3 Selected Tracks")

            # Deselect All
            sp.deselect_all()
            app.update_idletasks()
            self.assertEqual(len(sp.get_selected_download_items()), 0)
            self.assertIn("0 selected for download", sp._selection_summary_lbl.cget("text"))
            self.assertEqual(sp.download_mp3_btn.cget("text"), "⬇ Download MP3")

            # Repeatedly clicking Select All should not duplicate items
            sp.select_all()
            sp.select_all()
            self.assertEqual(len(sp.get_selected_download_items()), 3)
        finally:
            app.destroy()

    def test_spotify_per_track_quality_selection_and_batch_download(self):
        """Verifies each Spotify track carries its own audio quality setting into the download queue."""
        app = VyntraApp()
        try:
            app._switch_platform("spotify")
            sp = app._pages["spotify"]
            app.update_idletasks()

            items = [
                MediaItem(video_id="t1", title="Song 1", channel="Artist 1", platform="spotify"),
                MediaItem(video_id="t2", title="Song 2", channel="Artist 2", platform="spotify"),
                MediaItem(video_id="t3", title="Song 3", channel="Artist 3", platform="spotify"),
            ]
            sp._display_results(items, sp.next_generation(), col_key="test_playlist")
            app.update_idletasks()

            # Set independent qualities on cards
            sp._on_card_quality_changed("128 kbps", items[0])
            sp._on_card_quality_changed("192 kbps", items[1])
            sp._on_card_quality_changed("256 kbps", items[2])

            self.assertEqual(items[0].download_quality, "128 kbps")
            self.assertEqual(items[1].download_quality, "192 kbps")
            self.assertEqual(items[2].download_quality, "256 kbps")

            # Select Song 1 and Song 3 only (Song 2 not selected)
            items[0].selected_for_download = True
            items[2].selected_for_download = True
            sp._handle_download_selection_changed()

            # Mock download execution so tasks stay in queue
            with patch.object(app, "_process_next_download_task"):
                sp._handle_start_download()

                # Verify only the 2 selected tracks are queued
                self.assertEqual(len(app._download_queue), 2)

                task1 = app._download_queue[0]
                task2 = app._download_queue[1]

                # Verify task 1 has Song 1's quality (128 kbps -> LOW)
                self.assertEqual(task1.result.video_id, "t1")
                self.assertEqual(task1.selected_quality, "128 kbps")
                self.assertEqual(task1.format, MediaFormat.MP3)

                # Verify task 2 has Song 3's quality (256 kbps -> HIGH)
                self.assertEqual(task2.result.video_id, "t3")
                self.assertEqual(task2.selected_quality, "256 kbps")
                self.assertEqual(task2.format, MediaFormat.MP3)
        finally:
            app.destroy()

    def test_spotify_no_tracks_selected_prevents_silent_queue(self):
        """Verifies clicking download with 0 tracks selected does NOT silently queue the playlist."""
        app = VyntraApp()
        try:
            app._switch_platform("spotify")
            sp = app._pages["spotify"]
            app.update_idletasks()

            items = [
                MediaItem(video_id="t1", title="Song 1", channel="Artist 1", platform="spotify"),
                MediaItem(video_id="t2", title="Song 2", channel="Artist 2", platform="spotify"),
            ]
            sp._display_results(items, sp.next_generation(), col_key="empty_selection")
            sp.deselect_all()
            app.update_idletasks()

            with patch.object(app.status_banner, "show_warning") as mock_warn:
                sp._handle_start_download()
                mock_warn.assert_called_once()
                self.assertEqual(len(app._download_queue), 0)
        finally:
            app.destroy()

    def test_spotify_collection_scoping_and_state_preservation(self):
        """Verifies selection is scoped to active collection and preserved when returning."""
        app = VyntraApp()
        try:
            app._switch_platform("spotify")
            sp = app._pages["spotify"]
            app.update_idletasks()

            items_a = [
                MediaItem(video_id="a1", title="Track A1", channel="Artist A", platform="spotify"),
                MediaItem(video_id="a2", title="Track A2", channel="Artist A", platform="spotify"),
            ]
            sp._display_results(items_a, sp.next_generation(), col_key="playlist_alpha")
            items_a[0].selected_for_download = True
            sp._on_card_quality_changed("192 kbps", items_a[0])
            sp._handle_download_selection_changed()

            self.assertEqual(len(sp.get_selected_download_items()), 1)

            # Navigate to playlist beta
            items_b = [
                MediaItem(video_id="b1", title="Track B1", channel="Artist B", platform="spotify"),
                MediaItem(video_id="b2", title="Track B2", channel="Artist B", platform="spotify"),
            ]
            sp._display_results(items_b, sp.next_generation(), col_key="playlist_beta")
            # In playlist beta, no tracks should be selected initially
            self.assertEqual(len(sp.get_selected_download_items()), 0)

            # Select B2 in playlist beta
            items_b[1].selected_for_download = True
            sp._handle_download_selection_changed()
            self.assertEqual(len(sp.get_selected_download_items()), 1)
            self.assertEqual(sp.get_selected_download_items()[0].video_id, "b2")

            # Return to playlist alpha
            items_a_reloaded = [
                MediaItem(video_id="a1", title="Track A1", channel="Artist A", platform="spotify"),
                MediaItem(video_id="a2", title="Track A2", channel="Artist A", platform="spotify"),
            ]
            sp._display_results(items_a_reloaded, sp.next_generation(), col_key="playlist_alpha")

            # Verify playlist alpha's selections and quality were restored
            selected_a = sp.get_selected_download_items()
            self.assertEqual(len(selected_a), 1)
            self.assertEqual(selected_a[0].video_id, "a1")
            self.assertEqual(selected_a[0].download_quality, "192 kbps")
            # B2 must not be in playlist alpha
            self.assertFalse(any(it.video_id == "b2" for it in sp._current_items))
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
