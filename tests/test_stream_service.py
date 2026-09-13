"""
Unit tests for the Live Streaming Server and Player Service.
"""

import unittest
import urllib.request

from vyntra.services.stream_service import generate_player_page, stream_server, stream_service


class TestStreamService(unittest.TestCase):
    """Test suite for live streaming server and stream extraction."""

    def test_generate_player_page(self):
        """Verify HTML page generation for the full media player."""
        html = generate_player_page(
            video_id="dQw4w9WgXcQ",
            title="Rick Astley - Never Gonna Give You Up",
            channel="Rick Astley",
            duration_secs=212,
            stream_port=8080,
        )
        self.assertIn("Rick Astley - Never Gonna Give You Up", html)
        self.assertIn("http://127.0.0.1:8080/stream.mp4", html)
        self.assertIn("Vyntra HD Player", html)
        self.assertIn("video id=\"video-elem\"", html)

    def test_server_lifecycle_and_http_response(self):
        """Verify local stream server starts, responds on localhost, and stops cleanly."""
        port = stream_server.start()
        try:
            self.assertGreater(port, 1024)

            # Query /player endpoint
            url = f"http://127.0.0.1:{port}/player"
            req = urllib.request.urlopen(url, timeout=3)
            self.assertEqual(req.status, 200)
            content = req.read().decode("utf-8")
            self.assertIn("Vyntra HD Player", content)
        finally:
            stream_server.stop()
        self.assertEqual(stream_server.port, 0)

    def test_stream_url_extraction(self):
        """Verify yt-dlp extracts valid video and audio stream URLs."""
        v_url, a_url, headers, duration, title, channel = stream_service.extract_stream_urls("dQw4w9WgXcQ")
        self.assertTrue(v_url.startswith("http"))
        self.assertTrue(a_url.startswith("http"))
        self.assertGreater(duration, 0)
        self.assertTrue(len(title) > 0)


if __name__ == "__main__":
    unittest.main()
