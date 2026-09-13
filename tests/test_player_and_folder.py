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
    """Tests for SynchronizedMediaPlayer seeking, master clock, and playback controls stability."""

    @patch("av.open")
    def test_seek_and_master_clock_controls(self, mock_av_open):
        """Verifies that seek() updates the authoritative master clock cleanly."""
        mock_container = MagicMock()
        mock_container.streams.video = [MagicMock(width=640, height=360, time_base=1/30, average_rate=30.0)]
        mock_container.streams.video[0].codec_context.name = "h264"
        mock_container.streams.video[0].start_time = 0
        mock_container.streams.audio = []
        mock_av_open.return_value = mock_container

        player = FFmpegMediaPlayer("fake_media.mp4")
        self.assertAlmostEqual(player.get_pts(), 0.0, delta=0.5)

        # Seek should update authoritative master clock
        player.seek(15.0)
        self.assertAlmostEqual(player.get_pts(), 15.0, delta=0.5)

        # Relative seek
        player.seek(10.0, relative=True)
        self.assertAlmostEqual(player.get_pts(), 25.0, delta=0.5)

        # Pause and resume
        player.set_pause(True)
        self.assertTrue(player._is_paused)
        player.set_pause(False)
        self.assertFalse(player._is_paused)

        player.close_player()
        self.assertTrue(player._is_closed)

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


class TestStreamPlaybackAndVersioning(unittest.TestCase):
    """Tests for direct stream playback without downloads and centralized versioning."""

    def test_stream_payload_structure(self):
        """Verifies StreamPayload is a string subclass with separate video/audio URLs and headers."""
        from vyntra.services.youtube_service import StreamPayload
        payload = StreamPayload(
            video_url="https://youtube.com/video_stream_720p",
            audio_url="https://youtube.com/audio_stream_m4a",
            http_headers={"User-Agent": "CustomAgent/1.0", "Cookie": "test=1"},
        )
        self.assertIsInstance(payload, str)
        self.assertEqual(payload, "https://youtube.com/video_stream_720p")
        self.assertEqual(payload.video_url, "https://youtube.com/video_stream_720p")
        self.assertEqual(payload.audio_url, "https://youtube.com/audio_stream_m4a")
        self.assertEqual(payload.http_headers["User-Agent"], "CustomAgent/1.0")

    @patch("av.open")
    def test_synchronized_media_player_single_pipeline(self, mock_av_open):
        """Verifies SynchronizedMediaPlayer initializes a single unified pipeline rather than two processes."""
        from vyntra.services.youtube_service import StreamPayload
        mock_container = MagicMock()
        mock_container.streams.video = [MagicMock(width=1280, height=720, time_base=1/30, average_rate=30.0)]
        mock_container.streams.video[0].codec_context.name = "h264"
        mock_container.streams.video[0].start_time = 0
        mock_container.streams.audio = [MagicMock(rate=44100, time_base=1/44100)]
        mock_container.streams.audio[0].codec_context.name = "aac"
        mock_container.streams.audio[0].start_time = 0
        mock_av_open.return_value = mock_container

        payload = StreamPayload(
            video_url="https://googlevideo.com/video_stream",
            audio_url="https://googlevideo.com/audio_stream",
            http_headers={"User-Agent": "TestUA/2.0"},
        )

        player = FFmpegMediaPlayer(payload)

        # Verify unified single-engine pipeline opened both stream endpoints
        self.assertTrue(mock_av_open.called)
        self.assertEqual(player.video_url, "https://googlevideo.com/video_stream")
        self.assertEqual(player.audio_url, "https://googlevideo.com/audio_stream")

        player.close_player()
        self.assertTrue(player._is_closed)

    def test_version_centralization(self):
        """Verifies Vyntra centralized version string format and single source of truth."""
        import vyntra
        self.assertTrue(hasattr(vyntra, "__version__"))
        version = vyntra.__version__
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        parts = version.split(".")
        self.assertEqual(len(parts), 3, "Version must follow MAJOR.MINOR.PATCH format")
        for part in parts:
            self.assertTrue(part.isdigit(), f"Version part {part} must be numeric")


if __name__ == "__main__":
    unittest.main()
