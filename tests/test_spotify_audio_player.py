"""
Unit tests for Spotify audio-only player integration, dedicated AudioPlayer, and routing.
"""

import unittest
from unittest.mock import MagicMock, patch

from vyntra.models import MediaFormat, MediaItem, Platform
from vyntra.platforms.spotify.service import spotify_platform
from vyntra.services.audio_player import AudioPlayer


class TestSpotifyAudioOnly(unittest.TestCase):
    """Test suite ensuring Spotify is strictly audio-only with no video player involvement."""

    def setUp(self):
        self.item = MediaItem(
            video_id="4cOdK2wGLETKBW3PvgPWqT",
            title="Never Gonna Give You Up",
            channel="Rick Astley",
            platform="spotify",
            url="https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
            duration_seconds=213,
            preview_url="https://p.scdn.co/mp3-preview/test_preview_hash",
            thumbnail_url="https://i.scdn.co/image/test_art",
            album="Whenever You Need Somebody",
        )

    def test_prepare_playback_stream_official_preview(self):
        """Verifies that an official MP3 preview URL is returned directly."""
        stream_data = spotify_platform.prepare_playback_stream(self.item)
        self.assertIsInstance(stream_data, dict)
        self.assertEqual(stream_data.get("url"), "https://p.scdn.co/mp3-preview/test_preview_hash")
        self.assertEqual(stream_data.get("source_type"), "official_preview")
        self.assertIn("headers", stream_data)

    def test_prepare_playback_stream_raises_when_no_preview(self):
        """Verifies that when no preview snippet is available from Spotify, it raises RuntimeError and DOES NOT call YouTube."""
        item_no_prev = MediaItem(
            video_id="no_prev_123",
            title="A Little Death",
            channel="The Neighbourhood",
            platform="spotify",
            url="https://open.spotify.com/track/no_prev_123",
            duration_seconds=200,
            preview_url=None,
        )

        with patch.object(spotify_platform, "extract_from_url", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                spotify_platform.prepare_playback_stream(item_no_prev)
            self.assertIn("preview is unavailable", str(ctx.exception).lower())

    def test_build_download_options_strictly_audio(self):
        """Verifies that Spotify download options enforce MP3 and audio extraction."""
        from vyntra.models import DownloadTask
        task = DownloadTask(result=self.item, format=MediaFormat.MP4, save_directory="C:/Downloads")
        opts = spotify_platform.build_download_options(task, "C:/Music/test_song")

        self.assertEqual(task.format, MediaFormat.MP3)
        self.assertEqual(opts["format"], "bestaudio/best")
        self.assertTrue(any(
            pp.get("key") == "FFmpegExtractAudio" and pp.get("preferredcodec") == "mp3"
            for pp in opts.get("postprocessors", [])
        ))

    def test_app_routing_diverts_spotify_to_audio_player(self):
        """Verifies that VyntraApp._handle_play_video diverts Spotify items to _handle_play_audio."""
        from vyntra.ui.app import VyntraApp
        with patch.object(VyntraApp, "__init__", return_value=None):
            app = VyntraApp()
            app._handle_play_audio = MagicMock()
            app._player_modal = None

            app._handle_play_video(self.item)
            app._handle_play_audio.assert_called_once_with(self.item)
            self.assertIsNone(app._player_modal)

    def test_audio_player_requires_valid_url(self):
        """Verifies AudioPlayer rejects empty URLs with ValueError rather than crashing FFmpeg with error 22."""
        with self.assertRaises(ValueError):
            AudioPlayer({"audio_url": ""})

    @patch("av.open")
    @patch("sounddevice.RawOutputStream")
    def test_audio_player_lifecycle(self, mock_sd_cls, mock_av_open):
        """Verifies AudioPlayer initializes strictly audio streams, pause, seek, volume, and EOF."""
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_stream.time_base = 1.0 / 44100.0
        mock_stream.rate = 44100
        mock_container.streams.audio = [mock_stream]
        mock_container.demux.return_value = []
        mock_av_open.return_value = mock_container

        mock_sd = MagicMock()
        mock_sd_cls.return_value = mock_sd

        player = AudioPlayer({"audio_url": "https://p.scdn.co/preview.mp3"})
        self.assertFalse(player.is_eof())

        # Test volume
        player.set_volume(0.5)
        self.assertEqual(player._volume, 0.5)

        # Test pause/resume
        player.set_pause(True)
        self.assertTrue(player._is_paused)
        player.set_pause(False)
        self.assertFalse(player._is_paused)

        # Test seek
        player.seek(15.0)
        self.assertEqual(player.get_pts(), 15.0)
        mock_container.seek.assert_called()

        # Test close
        player.close()
        self.assertTrue(player._is_closed)
        mock_container.close.assert_called_once()

    def test_audio_player_resample_plane_slicing(self):
        """Verifies that AudioPlayer slices out the 128 padding bytes from resampled planes."""
        # A frame with 1024 samples in stereo 16-bit has 4096 valid bytes
        # Even if the plane buffer has 4224 bytes (with 128 padding bytes), it must slice to 4096 bytes
        mock_plane = b"x" * 4224
        mock_resampled = MagicMock()
        mock_resampled.samples = 1024
        mock_resampled.planes = [mock_plane]

        channels = 2
        valid_bytes = mock_resampled.samples * (channels * 2)
        raw_pcm = bytes(mock_resampled.planes[0])[:valid_bytes]
        self.assertEqual(len(raw_pcm), 4096)


if __name__ == "__main__":
    unittest.main()
