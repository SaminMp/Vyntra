"""
Unit tests for Spotify 30-second preview timeline clamping and metadata preservation.
"""

import unittest
from unittest.mock import MagicMock, patch

from vyntra.models import MediaItem
from vyntra.platforms.spotify.service import spotify_platform


class TestSpotifyTimeline30s(unittest.TestCase):
    """Test suite ensuring Spotify preview timeline is strictly 30s while preserving metadata."""

    def setUp(self):
        self.item = MediaItem(
            video_id="test_track_123",
            title="Blinding Lights",
            channel="The Weeknd",
            platform="spotify",
            url="https://open.spotify.com/track/test_track_123",
            duration_seconds=200,  # 3 minutes 20 seconds metadata
            preview_url="https://p.scdn.co/mp3-preview/test_hash_123",
            thumbnail_url="https://i.scdn.co/image/test_art",
            album="After Hours",
        )

    def test_spotify_stream_metadata_contains_preview_duration(self):
        """Verifies SpotifyPlatform.prepare_playback_stream specifies 30-second preview."""
        stream_data = spotify_platform.prepare_playback_stream(self.item)
        self.assertEqual(stream_data.get("duration_seconds"), 30)
        self.assertEqual(stream_data.get("preview_duration"), 30)
        self.assertTrue(stream_data.get("is_preview"))
        # Crucially, item.duration_seconds metadata was not altered!
        self.assertEqual(self.item.duration_seconds, 200)

    @patch("vyntra.ui.views.audio_player_modal.AudioPlayer")
    @patch("vyntra.ui.views.audio_player_modal.image_service")
    def test_audio_player_modal_clamps_to_30s(self, mock_img_svc, mock_audio_player_cls):
        """Verifies AudioPlayerModal limits timeline and seeking to 30s while preserving full track metadata."""
        from vyntra.ui.views.audio_player_modal import AudioPlayerModal

        with patch.object(AudioPlayerModal, "__init__", return_value=None):
            modal = AudioPlayerModal()
            modal.item = self.item
            modal._is_closed = False
            modal._is_seeking = False
            modal._playable_duration = 30.0
            modal._duration = 200

            modal.title_label = MagicMock()
            modal.artist_label = MagicMock()
            modal.art_label = MagicMock()
            modal.time_total_label = MagicMock()
            modal.time_current_label = MagicMock()
            modal.seek_slider = MagicMock()
            modal.status_label = MagicMock()
            modal.play_btn = MagicMock()
            modal.vol_slider = MagicMock()
            modal.vol_slider.get.return_value = 1.0
            modal.after = MagicMock()

            # Call load_audio
            with patch("threading.Thread"):
                modal.load_audio(self.item)

            self.assertEqual(modal._playable_duration, 30.0)
            self.assertEqual(modal._duration, 200)
            modal.seek_slider.configure.assert_called_with(to=30.0)
            modal.time_total_label.configure.assert_called_with(text="00:30")

            # Check metadata text includes full track duration
            artist_call_args = modal.artist_label.configure.call_args[1]
            self.assertIn("03:20", artist_call_args["text"])
            self.assertIn("30s Preview", artist_call_args["text"])

            # Test seeking beyond 30s is clamped to 30s
            mock_player = MagicMock()
            mock_player.get_pts.return_value = 25.0
            modal._player = mock_player

            # Drag slider to 45s
            modal._on_seek_drag(45.0)
            modal.time_current_label.configure.assert_called_with(text="00:30")

            # Commit slider at 50s
            modal.seek_slider.get.return_value = 50.0
            modal._on_seek_commit()
            mock_player.seek.assert_called_with(30.0)

            # Relative seek forward +10s from 25s should clamp to 30s
            modal._seek_relative(10.0)
            mock_player.seek.assert_called_with(30.0)
            modal.seek_slider.set.assert_called_with(30.0)

            # Relative seek backward -10s from 25s should go to 15s
            modal._seek_relative(-10.0)
            mock_player.seek.assert_called_with(15.0)
            modal.seek_slider.set.assert_called_with(15.0)


if __name__ == "__main__":
    unittest.main()
