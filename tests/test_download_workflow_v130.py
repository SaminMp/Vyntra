"""
Tests for Vyntra 1.3.0 download workflow upgrade:
- Accurate MP4 quality targeting without raw [ext=mp4] filtering bug
- Post-download media property inspection and height verification
- Playlist URL detection, flat extraction, and private/deleted video filtering
- Per-video format and quality configuration on individual cards
- Batch selection ('Select All' / 'Deselect All') and multi-item download dispatching
"""

import unittest
from unittest.mock import MagicMock, patch
import customtkinter as ctk

from vyntra import __version__
from vyntra.models import AudioQuality, DownloadStatus, DownloadTask, MediaFormat, SearchResult
from vyntra.services.download_service import download_service
from vyntra.services.ffmpeg_service import ffmpeg_service
from vyntra.services.search_service import search_service
from vyntra.services.youtube_service import youtube_service
from vyntra.ui.components.download_panel import DownloadPanel
from vyntra.ui.components.result_card import ResultCard
from vyntra.ui.components.results_list import ResultsList


class TestDownloadQualityBugFix(unittest.TestCase):
    """Verifies that MP4 quality formatting does not downgrade higher resolutions to 360p."""

    def test_mp4_format_spec_prioritizes_exact_height_and_allows_webm(self):
        """
        Verify that for 720p and 1080p, the format selector string:
        1. Seeks exact height first (height=720 or height=1080)
        2. Does NOT restrict bestvideo to [ext=mp4], which previously skipped YouTube's WebM/VP9 720p/1080p streams
        3. Sets merge_output_format to 'mp4'
        """
        result = SearchResult(
            video_id="test_vid_123",
            title="Test Video",
            channel="Channel",
            duration_seconds=120,
            duration_formatted="02:00",
            thumbnail_url="http://example.com/thumb.jpg",
            url="https://youtube.com/watch?v=test_vid_123",
        )

        for quality_label, expected_h in [("720p", 720), ("1080p", 1080), ("480p", 480)]:
            task = DownloadTask(
                result=result,
                format=MediaFormat.MP4,
                selected_quality=quality_label,
                save_directory="/tmp",
            )
            opts = download_service.build_ydl_options(task, "/tmp/out")
            format_str = opts.get("format", "")

            # Exact height matching must appear first in preference order
            self.assertIn(f"bestvideo[height={expected_h}]", format_str)
            self.assertIn(f"bestvideo[height<={expected_h}]", format_str)

            # Ensure bestvideo is NOT restricted to [ext=mp4]
            self.assertNotIn("bestvideo[height=", format_str.replace(f"bestvideo[height={expected_h}]", "").replace(f"bestvideo[height<={expected_h}]", ""))
            self.assertNotIn("[ext=mp4]+bestaudio", format_str)

            # Clean MP4 container remuxing
            self.assertEqual(opts.get("merge_output_format"), "mp4")

    @patch("pathlib.Path.is_file", return_value=True)
    @patch("vyntra.services.ffmpeg_service.ffmpeg_service.inspect_media_file")
    def test_post_download_verification_succeeds_on_matching_resolution(self, mock_inspect, mock_is_file):
        """Ensures that when the output file matches or approximates target height, verification passes."""
        mock_inspect.return_value = {
            "width": 1280,
            "height": 720,
            "resolution": "1280x720",
            "video_codec": "h264",
            "audio_codec": "aac",
            "has_audio": True,
            "has_video": True,
            "container": "mp4",
        }

        task = DownloadTask(
            result=SearchResult(
                video_id="abc",
                title="Vid",
                channel="Ch",
                duration_seconds=60,
                duration_formatted="01:00",
                thumbnail_url="",
                url="https://youtube.com/watch?v=abc",
            ),
            format=MediaFormat.MP4,
            selected_quality="720p",
            save_directory="/tmp",
        )

        available_formats = ["720p (HD)", "360p"]
        download_service._verify_downloaded_media(task, "/tmp/test.mp4", available_formats=available_formats)
        self.assertTrue(task.is_verified)
        self.assertEqual(task.actual_height, 720)
        self.assertEqual(task.actual_width, 1280)
        self.assertEqual(task.video_codec, "h264")

    @patch("pathlib.Path.is_file", return_value=True)
    @patch("vyntra.services.ffmpeg_service.ffmpeg_service.inspect_media_file")
    def test_post_download_verification_raises_when_downgraded_below_available(self, mock_inspect, mock_is_file):
        """Ensures that if 720p was available but the file was only 360p, verification raises RuntimeError."""
        mock_inspect.return_value = {
            "width": 640,
            "height": 360,
            "resolution": "640x360",
            "video_codec": "h264",
            "audio_codec": "aac",
            "has_audio": True,
            "has_video": True,
            "container": "mp4",
        }

        task = DownloadTask(
            result=SearchResult(
                video_id="abc",
                title="Vid",
                channel="Ch",
                duration_seconds=60,
                duration_formatted="01:00",
                thumbnail_url="",
                url="https://youtube.com/watch?v=abc",
            ),
            format=MediaFormat.MP4,
            selected_quality="720p",
            save_directory="/tmp",
        )

        available_formats = ["720p (HD)", "360p"]
        with self.assertRaises(RuntimeError) as ctx:
            download_service._verify_downloaded_media(task, "/tmp/test.mp4", available_formats=available_formats)
        self.assertIn("Resolution mismatch", str(ctx.exception))


class TestPlaylistSupport(unittest.TestCase):
    """Verifies YouTube playlist detection and extraction."""

    def test_playlist_url_detection(self):
        """Verifies that various playlist URL structures are correctly recognized."""
        valid_playlists = [
            "https://www.youtube.com/playlist?list=PLbpi6ZahtOH6Blw3RGYpWkSByi_T73gbE",
            "https://youtube.com/playlist?list=PLbpi6ZahtOH6Blw3RGYpWkSByi_T73gbE",
            "www.youtube.com/playlist?list=PL1234567890",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLbpi6ZahtOH6Blw3RGYpWkSByi_T73gbE",
            "https://youtu.be/dQw4w9WgXcQ?list=PLbpi6ZahtOH6Blw3RGYpWkSByi_T73gbE",
        ]
        for url in valid_playlists:
            self.assertTrue(search_service.is_youtube_playlist_url(url), f"Failed for {url}")
            self.assertTrue(search_service.is_youtube_url(url), f"Failed is_youtube_url for {url}")

        non_playlists = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "just a search term",
            "https://open.spotify.com/track/123",
        ]
        for query in non_playlists:
            self.assertFalse(search_service.is_youtube_playlist_url(query), f"Should not match {query}")

    @patch("yt_dlp.YoutubeDL")
    def test_playlist_extraction_filters_private_and_deleted(self, mock_ydl_class):
        """Verifies that flat playlist extraction skips private/deleted videos and extracts clean results."""
        mock_ydl = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "_type": "playlist",
            "title": "My Awesome Playlist",
            "entries": [
                {
                    "id": "vid1",
                    "title": "First Song",
                    "uploader": "Artist 1",
                    "duration": 200,
                    "view_count": 50000,
                    "url": "https://www.youtube.com/watch?v=vid1",
                },
                {
                    "id": "vid_deleted",
                    "title": "[Deleted video]",
                    "uploader": None,
                    "duration": 0,
                    "url": "https://www.youtube.com/watch?v=vid_deleted",
                },
                {
                    "id": "vid_priv",
                    "title": "Private video",
                    "uploader": None,
                    "duration": 0,
                    "url": "https://www.youtube.com/watch?v=vid_priv",
                },
                {
                    "id": "vid2",
                    "title": "Second Song",
                    "uploader": "Artist 2",
                    "duration": 180,
                    "view_count": 12000,
                    "url": "https://www.youtube.com/watch?v=vid2",
                },
            ],
        }

        results = search_service.search("https://www.youtube.com/playlist?list=PLtest")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].video_id, "vid1")
        self.assertEqual(results[0].title, "First Song")
        self.assertFalse(results[0].selected_for_download)
        self.assertEqual(results[0].download_format, MediaFormat.MP4)
        self.assertEqual(results[0].download_quality, "720p")

        self.assertEqual(results[1].video_id, "vid2")
        self.assertEqual(results[1].title, "Second Song")


class TestPerCardControlsAndBatchSelection(unittest.TestCase):
    """Verifies per-card format configuration and batch selection toolbar."""

    def test_result_card_per_item_format_and_checkbox(self):
        """Verifies ResultCard updates result model when format, quality, or checkbox is toggled."""
        root = ctk.CTk()
        root.withdraw()
        try:
            item = SearchResult(
                video_id="card_vid",
                title="Card Video",
                channel="Card Channel",
                duration_seconds=240,
                duration_formatted="04:00",
                thumbnail_url="http://example.com/thumb.jpg",
                url="https://youtube.com/watch?v=card_vid",
            )
            config_changed_calls = []
            card = ResultCard(
                root,
                result=item,
                on_select=lambda r: None,
                on_download_config_changed=lambda r: config_changed_calls.append(r),
            )
            root.update_idletasks()

            # Default state
            self.assertFalse(item.selected_for_download)
            self.assertEqual(item.download_format, MediaFormat.MP4)
            self.assertEqual(item.download_quality, "720p")

            # Check download checkbox
            card.set_download_checked(True)
            self.assertTrue(item.selected_for_download)

            # Change format to MP3
            card._on_format_changed("MP3")
            self.assertEqual(item.download_format, MediaFormat.MP3)
            self.assertEqual(item.download_quality, "320 kbps")

            # Change quality
            card._on_quality_changed("192 kbps")
            self.assertEqual(item.download_quality, "192 kbps")

            # Switch back to MP4
            card._on_format_changed("MP4")
            self.assertEqual(item.download_format, MediaFormat.MP4)
            self.assertEqual(item.download_quality, "720p")

            card._on_quality_changed("1080p")
            self.assertEqual(item.download_quality, "1080p")

            self.assertGreaterEqual(len(config_changed_calls), 4)
        finally:
            root.destroy()

    def test_results_list_select_all_and_batch_retrieval(self):
        """Verifies ResultsList 'Select All' and 'Deselect All' bulk toggling."""
        root = ctk.CTk()
        root.withdraw()
        try:
            items = [
                SearchResult(
                    video_id=f"vid_{i}",
                    title=f"Video {i}",
                    channel="Channel",
                    duration_seconds=100,
                    duration_formatted="01:40",
                    thumbnail_url="",
                    url=f"https://youtube.com/watch?v=vid_{i}",
                )
                for i in range(3)
            ]

            selection_events = []
            rlist = ResultsList(
                root,
                on_result_selected=lambda r: None,
                on_download_selection_changed=lambda sel: selection_events.append(sel),
            )
            root.update_idletasks()

            rlist.display_results(items)
            root.update_idletasks()

            # Initial: 0 selected
            self.assertEqual(len(rlist.get_selected_download_items()), 0)

            # Select All
            rlist.select_all()
            selected = rlist.get_selected_download_items()
            self.assertEqual(len(selected), 3)

            # Deselect All
            rlist.deselect_all()
            self.assertEqual(len(rlist.get_selected_download_items()), 0)

            # Manually check individual card
            rlist._cards[1].set_download_checked(True)
            rlist._handle_download_config_changed()
            selected = rlist.get_selected_download_items()
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0].video_id, "vid_1")
        finally:
            root.destroy()

    def test_download_panel_button_text_updates_dynamically(self):
        """Verifies DownloadPanel button reflects batch count or single card settings."""
        root = ctk.CTk()
        root.withdraw()
        try:
            panel = DownloadPanel(
                root,
                on_download=lambda *args, **kwargs: None,
                on_cancel=lambda: None,
            )
            root.update_idletasks()

            item1 = SearchResult(
                video_id="v1",
                title="Song A",
                channel="Ch",
                duration_seconds=100,
                duration_formatted="01:40",
                thumbnail_url="",
                url="https://youtube.com/watch?v=v1",
            )
            item1.download_format = MediaFormat.MP3
            item1.download_quality = "320 kbps"

            item2 = SearchResult(
                video_id="v2",
                title="Song B",
                channel="Ch",
                duration_seconds=120,
                duration_formatted="02:00",
                thumbnail_url="",
                url="https://youtube.com/watch?v=v2",
            )
            item2.download_format = MediaFormat.MP4
            item2.download_quality = "1080p"

            # 1. Single card selected
            panel.set_selected_result(item1)
            self.assertIn("Download Video", panel.download_btn.cget("text"))

            # 2. Batch selected: 2 items
            panel.set_batch_selected_items([item1, item2])
            self.assertEqual(panel.download_btn.cget("text"), "⬇ Download 2 Selected Videos")

            # 3. Batch cleared -> reverts to single card
            panel.set_batch_selected_items([])
            self.assertIn("Download Video", panel.download_btn.cget("text"))
        finally:
            root.destroy()


class TestBatchAppDispatch(unittest.TestCase):
    """Verifies that VyntraApp correctly queues batch tasks using per-item configuration."""

    @patch("vyntra.services.download_service.download_service.start_download")
    def test_app_queues_and_runs_batch_downloads(self, mock_start_download):
        from vyntra.ui.app import VyntraApp
        root = VyntraApp()
        root.withdraw()
        try:
            item1 = SearchResult(
                video_id="b1",
                title="Batch Video 1",
                channel="Ch1",
                duration_seconds=100,
                duration_formatted="01:40",
                thumbnail_url="",
                url="https://youtube.com/watch?v=b1",
            )
            item1.download_format = MediaFormat.MP3
            item1.download_quality = "320 kbps"

            item2 = SearchResult(
                video_id="b2",
                title="Batch Video 2",
                channel="Ch2",
                duration_seconds=200,
                duration_formatted="03:20",
                thumbnail_url="",
                url="https://youtube.com/watch?v=b2",
            )
            item2.download_format = MediaFormat.MP4
            item2.download_quality = "1080p"

            # Dispatch batch download
            root._handle_start_download(
                result=item1,
                media_format=MediaFormat.MP4,
                quality="720p",
                save_dir="/tmp",
                batch_items=[item1, item2],
            )

            # Check that first task was dispatched immediately
            self.assertEqual(mock_start_download.call_count, 1)
            first_task = mock_start_download.call_args[1]["task"]
            self.assertEqual(first_task.result.video_id, "b1")
            self.assertEqual(first_task.format, MediaFormat.MP3)
            self.assertEqual(first_task.selected_quality, "320 kbps")

            # Check remaining in queue
            self.assertEqual(len(root._download_queue), 1)
            queued_task = root._download_queue[0]
            self.assertEqual(queued_task.result.video_id, "b2")
            self.assertEqual(queued_task.format, MediaFormat.MP4)
            self.assertEqual(queued_task.selected_quality, "1080p")

            # Complete first task to trigger second
            on_complete = mock_start_download.call_args[1]["on_complete"]
            on_complete("/tmp/b1.mp3")
            root.update()

            self.assertEqual(mock_start_download.call_count, 2)
            second_task = mock_start_download.call_args[1]["task"]
            self.assertEqual(second_task.result.video_id, "b2")
            self.assertEqual(len(root._download_queue), 0)

            # Complete second task
            on_complete2 = mock_start_download.call_args[1]["on_complete"]
            on_complete2("/tmp/b2.mp4")
            root.update()

            self.assertIsNone(root._active_task_id)
        finally:
            root.destroy()


class TestFooterDecoupledFormatAndQuality(unittest.TestCase):
    """
    Verifies that:
    1. Format and Media Quality controls are completely removed from the footer.
    2. Media cards retain their individual Format and Quality controls as the source of truth.
    3. The footer download action respects each card's independent format and quality settings.
    """

    def test_footer_has_no_format_or_quality_controls(self):
        root = ctk.CTk()
        root.withdraw()
        try:
            panel = DownloadPanel(
                root,
                on_download=lambda *args, **kwargs: None,
                on_cancel=lambda: None,
            )
            root.update_idletasks()

            # Confirm no format or quality widgets exist in the footer
            self.assertFalse(hasattr(panel, "format_segmented"))
            self.assertFalse(hasattr(panel, "quality_option"))
            self.assertFalse(hasattr(panel, "fmt_label"))
            self.assertFalse(hasattr(panel, "quality_label"))
            self.assertFalse(hasattr(panel, "options_frame"))

            # Confirm essential footer controls exist
            self.assertTrue(hasattr(panel, "header_frame"))
            self.assertTrue(hasattr(panel, "folder_frame"))
            self.assertTrue(hasattr(panel, "action_frame"))
            self.assertTrue(hasattr(panel, "download_btn"))
            self.assertTrue(hasattr(panel, "cancel_btn"))
        finally:
            root.destroy()

    def test_media_card_retains_format_and_quality_controls(self):
        root = ctk.CTk()
        root.withdraw()
        try:
            item = SearchResult(
                video_id="test_card_1",
                title="Sample Video",
                channel="Sample Channel",
                duration_seconds=180,
                duration_formatted="03:00",
                thumbnail_url="",
                url="https://youtube.com/watch?v=test_card_1",
            )
            card = ResultCard(root, result=item, on_select=lambda r: None)
            root.update_idletasks()

            # Both controls must remain on the media card
            self.assertTrue(hasattr(card, "format_menu"))
            self.assertTrue(hasattr(card, "quality_menu"))
            self.assertTrue(hasattr(card, "download_checkbox"))

            # Changing format on card updates item model
            card._on_format_changed("MP3")
            self.assertEqual(item.download_format, MediaFormat.MP3)
            self.assertEqual(item.download_quality, "320 kbps")

            card._on_quality_changed("256 kbps")
            self.assertEqual(item.download_quality, "256 kbps")

            card._on_format_changed("MP4")
            self.assertEqual(item.download_format, MediaFormat.MP4)
            self.assertEqual(item.download_quality, "720p")

            card._on_quality_changed("1080p")
            self.assertEqual(item.download_quality, "1080p")
        finally:
            root.destroy()

    def test_single_card_download_uses_card_format_and_quality(self):
        root = ctk.CTk()
        root.withdraw()
        try:
            dispatched = []

            def mock_download(res, fmt, q, d, **kwargs):
                dispatched.append((res, fmt, q, d, kwargs))

            panel = DownloadPanel(
                root,
                on_download=mock_download,
                on_cancel=lambda: None,
            )
            root.update_idletasks()

            item = SearchResult(
                video_id="single_vid",
                title="Single MP3 Video",
                channel="Music",
                duration_seconds=120,
                duration_formatted="02:00",
                thumbnail_url="",
                url="https://youtube.com/watch?v=single_vid",
            )
            item.download_format = MediaFormat.MP3
            item.download_quality = "320 kbps"

            panel.set_selected_result(item)
            self.assertIn("MP3", panel.download_btn.cget("text"))
            self.assertIn("320", panel.download_btn.cget("text"))

            panel._handle_download()
            self.assertEqual(len(dispatched), 1)
            res, fmt, q, d, kwargs = dispatched[0]
            self.assertEqual(res.video_id, "single_vid")
            self.assertEqual(fmt, MediaFormat.MP3)
            self.assertEqual(q, "320 kbps")
        finally:
            root.destroy()

    def test_batch_cards_download_respects_each_card_settings_independently(self):
        root = ctk.CTk()
        root.withdraw()
        try:
            dispatched = []

            def mock_download(res, fmt, q, d, **kwargs):
                dispatched.append((res, fmt, q, d, kwargs))

            panel = DownloadPanel(
                root,
                on_download=mock_download,
                on_cancel=lambda: None,
            )
            root.update_idletasks()

            card1_item = SearchResult(
                video_id="card1",
                title="Song A",
                channel="Artist A",
                duration_seconds=150,
                duration_formatted="02:30",
                thumbnail_url="",
                url="https://youtube.com/watch?v=card1",
            )
            card1_item.download_format = MediaFormat.MP3
            card1_item.download_quality = "320 kbps"

            card2_item = SearchResult(
                video_id="card2",
                title="Video B",
                channel="Creator B",
                duration_seconds=300,
                duration_formatted="05:00",
                thumbnail_url="",
                url="https://youtube.com/watch?v=card2",
            )
            card2_item.download_format = MediaFormat.MP4
            card2_item.download_quality = "1080p"

            # Set batch selection with 2 cards having independent settings
            panel.set_batch_selected_items([card1_item, card2_item])
            self.assertEqual(panel.download_btn.cget("text"), "⬇ Download 2 Selected Videos")

            # Click footer download button
            panel._handle_download()
            self.assertEqual(len(dispatched), 1)
            res, fmt, q, d, kwargs = dispatched[0]
            batch_items = kwargs.get("batch_items", [])
            self.assertEqual(len(batch_items), 2)

            # Each item in the batch preserves its own independent settings
            self.assertEqual(batch_items[0].video_id, "card1")
            self.assertEqual(batch_items[0].download_format, MediaFormat.MP3)
            self.assertEqual(batch_items[0].download_quality, "320 kbps")

            self.assertEqual(batch_items[1].video_id, "card2")
            self.assertEqual(batch_items[1].download_format, MediaFormat.MP4)
            self.assertEqual(batch_items[1].download_quality, "1080p")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()

