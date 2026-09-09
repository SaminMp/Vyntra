"""
Unit and integration tests for the video player stream pipeline and download folder resolution.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from vyntra.config import config_manager
from vyntra.models import DownloadTask, MediaFormat, SearchResult
from vyntra.services.download_service import download_service
from vyntra.services.media_player import FFmpegMediaPlayer
from vyntra.services.youtube_service import youtube_service
from vyntra.ui.views.player_modal import VideoPlayerModal


class TestPlayerStreamPipeline(unittest.TestCase):
    """Tests for the video playback preparation and stream extraction pipeline."""

    def setUp(self):
        self.result = SearchResult(
            video_id="test_vid_123",
            title="Sample Video",
            channel="Sample Channel",
            duration_seconds=120,
            duration_formatted="02:00",
            thumbnail_url="https://example.com/thumb.jpg",
            url="https://www.youtube.com/watch?v=test_vid_123",
        )

    def test_prepare_playback_finds_existing_local_file(self):
        """Verifies that an existing local downloaded video is reused immediately without network extraction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_file = Path(tmpdir) / "Sample Video.mp4"
            fake_file.write_text("fake video content" * 10000)

            ready_args = []
            error_args = []

            with patch.object(config_manager.config, "download_directory", tmpdir):
                youtube_service.prepare_playback_stream(
                    self.result,
                    on_ready=lambda url, dur: ready_args.append((url, dur)),
                    on_error=lambda err: error_args.append(err),
                )
                self.assertEqual(len(ready_args), 1)
                self.assertEqual(ready_args[0][0], str(fake_file))
                self.assertEqual(len(error_args), 0)

    @patch("yt_dlp.YoutubeDL")
    def test_prepare_playback_extracts_stream_url_without_download(self, mock_ydl_cls):
        """Verifies that prepare_playback_stream calls extract_info with download=False and invokes on_ready."""
        import threading
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "id": "test_vid_123",
            "title": "Sample Video",
            "url": "https://googlevideo.com/videoplayback?id=1",
            "duration": 120,
            "http_headers": {"User-Agent": "TestAgent/1.0"},
        }

        ready_event = threading.Event()
        ready_args = []
        error_args = []

        youtube_service.prepare_playback_stream(
            self.result,
            on_ready=lambda url, dur: (ready_args.append((url, dur)), ready_event.set()),
            on_error=lambda err: (error_args.append(err), ready_event.set()),
        )

        self.assertTrue(ready_event.wait(timeout=5.0))
        self.assertEqual(len(ready_args), 1)
        self.assertIn("https://googlevideo.com/videoplayback", ready_args[0][0])
        self.assertEqual(ready_args[0][1], 120)
        self.assertEqual(len(error_args), 0)
        mock_ydl.extract_info.assert_called_once_with(self.result.url, download=False)

    @patch("yt_dlp.YoutubeDL")
    def test_prepare_playback_error_translation(self, mock_ydl_cls):
        """Verifies that stream preparation errors are caught, sanitized, and passed to on_error."""
        import threading
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.side_effect = RuntimeError("Sign in to confirm you’re not a bot")

        error_event = threading.Event()
        error_args = []

        youtube_service.prepare_playback_stream(
            self.result,
            on_ready=lambda url, dur: None,
            on_error=lambda err: (error_args.append(err), error_event.set()),
        )

        self.assertTrue(error_event.wait(timeout=5.0))
        self.assertEqual(len(error_args), 1)
        self.assertIn("sign-in verification", str(error_args[0]).lower())


class TestDownloadFolderResolution(unittest.TestCase):
    """Tests for download folder tracking and custom path persistence."""

    @patch("yt_dlp.YoutubeDL")
    def test_execute_download_logs_and_returns_actual_output(self, mock_ydl_cls):
        """Verifies that _execute_download configures postprocessor hooks and returns the resolved output path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task = DownloadTask(
                result=SearchResult(
                    video_id="track_vid",
                    title="Test Song",
                    channel="Artist",
                    duration_seconds=60,
                    duration_formatted="01:00",
                    thumbnail_url="",
                    url="https://youtube.com/watch?v=track_vid",
                ),
                format=MediaFormat.MP3,
                save_directory=tmpdir,
            )

            # Simulate produced file on disk
            produced_file = Path(tmpdir) / "Test Song.mp3"
            produced_file.write_text("fake mp3 data")

            mock_ydl = MagicMock()
            mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

            def fake_download(urls):
                # Simulate ytdlp postprocessor hook invocation
                call_opts = mock_ydl_cls.call_args[0][0]
                self.assertIn("postprocessor_hooks", call_opts)
                for hook in call_opts["postprocessor_hooks"]:
                    hook({"status": "finished", "info_dict": {"filepath": str(produced_file)}})

            mock_ydl.download.side_effect = fake_download

            out = download_service._execute_download(task, lambda p: None)
            self.assertEqual(out, str(produced_file.resolve()))

    def test_custom_save_directory_updates_config(self):
        """Verifies that selecting a custom directory persists immediately to user configuration."""
        with tempfile.TemporaryDirectory() as custom_dir:
            initial_dir = config_manager.config.download_directory
            try:
                config_manager.update(download_directory=custom_dir)
                self.assertEqual(config_manager.config.download_directory, custom_dir)
            finally:
                config_manager.update(download_directory=initial_dir)


class TestPlayerControls(unittest.TestCase):
    """Tests for FFmpegMediaPlayer seeking, generation tokens, and playback controls stability."""

    @patch("subprocess.Popen")
    def test_seek_does_not_deadlock_and_increments_generation(self, mock_popen_cls):
        """Verifies that seek() executes cleanly without deadlocking and increments generation."""
        mock_proc = MagicMock()
        mock_proc.stdout.read.return_value = b""
        mock_proc.poll.return_value = None
        mock_popen_cls.return_value = mock_proc

        player = FFmpegMediaPlayer("fake_media.mp4")
        self.assertEqual(player._generation, 1)

        # Seek should not deadlock
        player.seek(15.0)
        self.assertEqual(player._generation, 2)
        self.assertEqual(player.get_pts(), 15.0)

        # Relative seek
        player.seek(10.0, relative=True)
        self.assertEqual(player._generation, 3)
        self.assertEqual(player.get_pts(), 25.0)

        player.close_player()
        self.assertTrue(player._is_closed)

    @patch("subprocess.Popen")
    def test_obsolete_reader_thread_does_not_inject_eof(self, mock_popen_cls):
        """Verifies that reader loops from earlier generations do not inject EOF into frame queue."""
        mock_proc = MagicMock()
        mock_proc.stdout.read.return_value = b""
        mock_proc.poll.return_value = None
        mock_popen_cls.return_value = mock_proc

        player = FFmpegMediaPlayer("fake_media.mp4")
        gen1 = player._generation

        # Now simulate seek which increments generation to 2
        player.seek(10.0)
        self.assertEqual(player._generation, 2)

        # Drain the queue so it is completely empty
        while not player._frame_queue.empty():
            player._frame_queue.get_nowait()

        # If obsolete gen1 thread exits, it should NOT put 'eof' because gen1 != self._generation
        player._frame_reader_loop(gen1, mock_proc)

        # Frame queue should remain empty (no eof inserted by obsolete generation)
        self.assertTrue(player._frame_queue.empty())

        player.close_player()

    def test_modal_seek_relative_and_release(self):
        """Verifies VideoPlayerModal seek helper functions."""
        modal = MagicMock()
        modal._player = MagicMock()
        modal._player.get_pts.return_value = 20.0
        modal._duration = 100.0
        modal._is_paused = True
        modal._is_render_loop_running = False
        modal._ensure_render_loop_running = MagicMock()

        # Test relative seek +10s
        VideoPlayerModal._seek_relative(modal, 10.0)
        modal._player.seek.assert_called_with(30.0, relative=False)
        modal.seek_slider.set.assert_called_with(30.0)
        self.assertFalse(modal._is_paused)
        modal._ensure_render_loop_running.assert_called()

        # Test relative seek -10s
        modal._player.get_pts.return_value = 30.0
        VideoPlayerModal._seek_relative(modal, -10.0)
        modal._player.seek.assert_called_with(20.0, relative=False)
        modal.seek_slider.set.assert_called_with(20.0)


if __name__ == "__main__":
    unittest.main()
