"""
Unit tests for Spotify audio-only platform integration in Vyntra.
"""

from unittest.mock import MagicMock, patch
import unittest

from vyntra.models import AudioQuality, DownloadTask, MediaFormat, MediaItem, Platform
from vyntra.platforms.registry import platform_registry
from vyntra.platforms.spotify.service import spotify_platform


class TestSpotifyPlatform(unittest.TestCase):
    """Test suite for Spotify platform service, audio-only constraints, and capabilities."""

    def test_platform_registration(self):
        svc = platform_registry.get("spotify")
        self.assertIsNotNone(svc)
        self.assertEqual(svc.platform_id, "spotify")
        self.assertEqual(svc.capabilities.display_name, "Spotify")

    def test_capabilities_audio_only_constraints(self):
        caps = spotify_platform.capabilities
        self.assertTrue(caps.supports_search)
        self.assertTrue(caps.supports_url_input)
        self.assertFalse(caps.supports_video_playback, "Spotify must NOT support video playback")
        self.assertTrue(caps.supports_audio_preview)
        self.assertFalse(caps.supports_mp4, "Spotify must NEVER support MP4")
        self.assertTrue(caps.supports_mp3, "Spotify must support MP3")
        self.assertFalse(caps.supports_video_quality, "Spotify must NOT have video quality options")
        self.assertTrue(caps.supports_audio_quality)

    def test_url_detection(self):
        valid_urls = [
            "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
            "http://spotify.com/track/4cOdK2wGLETKBW3PvgPWqT?si=12345",
            "spotify:track:4cOdK2wGLETKBW3PvgPWqT",
            "https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3",
        ]
        invalid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.instagram.com/reel/C7XyZ123456/",
            "https://www.tiktok.com/@user/video/123456789",
            "https://example.com",
            "",
        ]
        for url in valid_urls:
            self.assertTrue(spotify_platform.can_handle_url(url), f"Should handle valid Spotify URL: {url}")
        for url in invalid_urls:
            self.assertFalse(spotify_platform.can_handle_url(url), f"Should reject non-Spotify URL: {url}")

    def test_extract_track_id(self):
        tid1 = spotify_platform._extract_track_id("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT?si=123")
        self.assertEqual(tid1, "4cOdK2wGLETKBW3PvgPWqT")
        tid2 = spotify_platform._extract_track_id("spotify:track:1234567890abcdef")
        self.assertEqual(tid2, "1234567890abcdef")

    def test_build_download_options_enforces_mp3(self):
        item = MediaItem(
            video_id="4cOdK2wGLETKBW3PvgPWqT",
            title="Never Gonna Give You Up",
            channel="Rick Astley",
            url="https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
            platform="spotify",
        )
        # Even if MP4 was mistakenly requested on DownloadTask, SpotifyPlatform must force MP3
        task = DownloadTask(
            result=item,
            format=MediaFormat.MP4,
            save_directory="D:/Downloads",
            audio_quality=AudioQuality.BEST,
        )
        opts = spotify_platform.build_download_options(task, "D:/Downloads/Rick_Astley_Never_Gonna_Give_You_Up")
        self.assertEqual(task.format, MediaFormat.MP3, "Spotify must enforce MP3 format")
        has_audio_extract = any(p.get("key") == "FFmpegExtractAudio" for p in opts["postprocessors"])
        self.assertTrue(has_audio_extract)
        # Verify preferred codec is mp3
        for p in opts["postprocessors"]:
            if p.get("key") == "FFmpegExtractAudio":
                self.assertEqual(p.get("preferredcodec"), "mp3")

    @patch("urllib.request.urlopen")
    def test_extract_from_url_mock(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = (
            b'<html><script id="__NEXT_DATA__" type="application/json">'
            b'{"props":{"pageProps":{"state":{"data":{"entity":{'
            b'"title":"Stay","artists":[{"name":"The Kid LAROI"},{"name":"Justin Bieber"}],'
            b'"duration":141800,"audioPreview":{"url":"https://p.scdn.co/preview.mp3"},'
            b'"coverArt":{"sources":[{"url":"https://image-cdn.spotify.com/art.jpg"}]}'
            b'}}}}}}</script></html>'
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        item = spotify_platform.extract_from_url("https://open.spotify.com/track/5PjdY0CKGZdEuoNab3yMmX")
        self.assertIsNotNone(item)
        self.assertEqual(item.video_id, "5PjdY0CKGZdEuoNab3yMmX")
        self.assertEqual(item.title, "Stay")
        self.assertEqual(item.channel, "The Kid LAROI, Justin Bieber")
        self.assertEqual(item.duration_seconds, 141)
        self.assertEqual(item.duration_formatted, "02:21")
        self.assertEqual(item.preview_url, "https://p.scdn.co/preview.mp3")

    @patch.object(spotify_platform, "_get_api_access_token", return_value="mock_token")
    @patch("urllib.request.urlopen")
    def test_search_fallback_to_music_catalog_on_403(self, mock_urlopen, mock_token):
        # 1st call to Spotify Web API raises HTTP 403 Forbidden
        import urllib.error
        err_403 = urllib.error.HTTPError(
            url="https://api.spotify.com/v1/search",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )

        catalog_resp = MagicMock()
        catalog_resp.read.return_value = (
            b'{"resultCount":1,"results":[{"trackId":12345,"trackName":"in the pool",'
            b'"artistName":"kensuke ushio","collectionName":"Chainsaw Man OST",'
            b'"trackTimeMillis":180000,"artworkUrl100":"https://img/100x100bb.jpg",'
            b'"previewUrl":"https://audio/preview.m4a","trackViewUrl":"https://music/track"}]}'
        )
        catalog_cm = MagicMock()
        catalog_cm.__enter__.return_value = catalog_resp

        mock_urlopen.side_effect = [err_403, catalog_cm]

        results = spotify_platform.search("in the pool", max_results=5)
        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item.title, "in the pool")
        self.assertEqual(item.channel, "kensuke ushio")
        self.assertEqual(item.album, "Chainsaw Man OST")
        self.assertEqual(item.duration_seconds, 180)
        self.assertEqual(item.platform, "spotify")
        self.assertEqual(item.preview_url, "https://audio/preview.m4a")
        self.assertTrue("600x600bb.jpg" in item.thumbnail_url)

    def test_prepare_playback_stream(self):
        item = MediaItem(
            video_id="test_123",
            title="Test Song",
            channel="Test Artist",
            platform="spotify",
            preview_url="https://audio/preview.mp3",
        )
        stream = spotify_platform.prepare_playback_stream(item)
        self.assertEqual(stream.get("source_type"), "official_preview")
        self.assertEqual(stream.get("url"), "https://audio/preview.mp3")
        self.assertEqual(stream.get("duration_seconds"), 30)


if __name__ == "__main__":
    unittest.main()

