"""
Unit tests for SynchronizedMediaPlayer state machine, clock authority, buffering, and seek epoch.
"""

import queue
import time
import unittest
from unittest.mock import MagicMock, patch

from vyntra.services.media_player import PlayerState, SynchronizedMediaPlayer


class TestPlayerClockAndState(unittest.TestCase):
    """Test suite ensuring master clock never runs away and state machine behaves correctly."""

    @patch("av.open")
    @patch("sounddevice.RawOutputStream")
    def test_initial_state_and_buffering_transition(self, mock_sd_cls, mock_av_open):
        """Verifies player enters BUFFERING on empty queue and freezes clock."""
        mock_container_v = MagicMock()
        mock_v_stream = MagicMock()
        mock_v_stream.time_base = 1.0 / 30.0
        mock_v_stream.average_rate = 30.0
        mock_v_stream.width = 640
        mock_v_stream.height = 360
        mock_v_stream.start_time = 0
        mock_container_v.streams.video = [mock_v_stream]
        mock_container_v.demux.return_value = iter([])

        mock_container_a = MagicMock()
        mock_a_stream = MagicMock()
        mock_a_stream.time_base = 1.0 / 44100.0
        mock_a_stream.rate = 44100
        mock_a_stream.start_time = 0
        mock_container_a.streams.audio = [mock_a_stream]
        mock_container_a.demux.return_value = iter([])

        def side_effect(url, options=None):
            if "video" in str(url):
                return mock_container_v
            return mock_container_a

        mock_av_open.side_effect = side_effect

        mock_sd = MagicMock()
        mock_sd_cls.return_value = mock_sd

        payload = {"video_url": "http://example.com/video.mp4", "audio_url": "http://example.com/audio.mp4"}

        with patch("threading.Thread"):
            player = SynchronizedMediaPlayer(payload, diagnostic_mode=False)

        # State should be PLAYING initially
        self.assertEqual(player.get_state(), PlayerState.PLAYING)

        # When get_frame is called and video queue is empty and not EOF -> BUFFERING
        frame_res, delay = player.get_frame()
        self.assertIsNone(frame_res)
        self.assertEqual(player.get_state(), PlayerState.BUFFERING)

        # When in BUFFERING, get_pts returns frozen _last_video_pts
        player._last_video_pts = 12.5
        self.assertEqual(player.get_pts(), 12.5)

        # Clock does not advance even after time passes
        time.sleep(0.05)
        self.assertEqual(player.get_pts(), 12.5)

        player.close_player()

    @patch("av.open")
    def test_error_state_on_stream_failure(self, mock_av_open):
        """Verifies player enters ERROR state if container opening fails and clock does not tick."""
        mock_av_open.side_effect = RuntimeError("HTTP 403 Forbidden")

        payload = {"video_url": "https://googlevideo.com/videoplayback?fail=1"}
        player = SynchronizedMediaPlayer(payload, diagnostic_mode=False)

        self.assertEqual(player.get_state(), PlayerState.ERROR)
        self.assertIsNotNone(player._last_error)
        self.assertIn("403 Forbidden", player._last_error)

        # Frame call returns error
        frame_res, delay = player.get_frame()
        self.assertIsNone(frame_res)
        self.assertEqual(delay, "error")

        # PTS is frozen at 0.0, does not run away
        self.assertEqual(player.get_pts(), 0.0)
        time.sleep(0.05)
        self.assertEqual(player.get_pts(), 0.0)

        player.close_player()

    @patch("av.open")
    @patch("sounddevice.RawOutputStream")
    def test_seek_increments_epoch_and_flushes(self, mock_sd_cls, mock_av_open):
        """Verifies seek increments epoch, flushes buffers, and sets BUFFERING state."""
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_stream.time_base = 1.0 / 30.0
        mock_stream.average_rate = 30.0
        mock_stream.codec_context = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.streams.audio = []
        mock_container.demux.return_value = iter([])
        mock_av_open.return_value = mock_container

        with patch("threading.Thread"):
            player = SynchronizedMediaPlayer({"video_url": "http://example.com/video.mp4"}, diagnostic_mode=False)

        initial_epoch = player._seek_epoch
        player.seek(60.0)

        self.assertEqual(player._seek_epoch, initial_epoch + 1)
        self.assertEqual(player.get_state(), PlayerState.BUFFERING)
        self.assertEqual(player.get_pts(), 60.0)
        mock_stream.codec_context.flush_buffers.assert_called()

        player.close_player()


if __name__ == "__main__":
    unittest.main()
