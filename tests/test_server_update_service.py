"""
Integration and unit tests for server/update_service.py.
Verifies HTTP endpoints, platform validation, SemVer precedence,
and binary streaming against live loopback ThreadingHTTPServer.
"""

from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import MagicMock, patch
import urllib.request
import urllib.error

from server.update_service import UpdateServiceHTTPHandler, fetch_release_data


class TestServerUpdateService(unittest.TestCase):
    """Verifies update service API contracts and validation."""

    @classmethod
    def setUpClass(cls):
        # Start test server on dynamic loopback port
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), UpdateServiceHTTPHandler)
        cls.port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_health_check(self):
        url = f"{self.base_url}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["service"], "vyntra-update-service")

    def test_unsupported_platform_rejected(self):
        """Rejects unsupported platform requests with HTTP 400."""
        url = f"{self.base_url}/api/v1/updates/latest?platform=linux-x86_64"
        req = urllib.request.Request(url)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)
        err_body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertIn("Unsupported platform", err_body["error"])

    @patch("server.update_service.fetch_release_data")
    def test_latest_update_windows_available(self, mock_fetch):
        """Returns sanitized metadata for Windows with update_available=True."""
        mock_fetch.return_value = {
            "tag_name": "v1.2.4",
            "name": "Vyntra v1.2.4",
            "body": "Release notes...",
            "published_at": "2026-09-14T00:00:00Z",
            "assets": [
                {
                    "name": "Vyntra-Windows-x64.exe",
                    "url": "https://api.github.com/repos/SaminMp/Vyntra/releases/assets/101",
                    "size": 85000000,
                },
                {
                    "name": "Vyntra-macOS.dmg",
                    "url": "https://api.github.com/repos/SaminMp/Vyntra/releases/assets/102",
                    "size": 75000000,
                },
            ],
            "_checksums_map": {
                "Vyntra-Windows-x64.exe": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            },
        }

        url = f"{self.base_url}/api/v1/updates/latest?platform=windows-x64&current_version=1.1.3"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))

            self.assertTrue(data["update_available"])
            self.assertEqual(data["version"], "1.2.4")
            self.assertEqual(data["platform"], "windows-x64")
            self.assertEqual(data["asset_name"], "Vyntra-Windows-x64.exe")
            self.assertIn("/api/v1/updates/download/windows-x64", data["download_url"])
            self.assertEqual(data["sha256"], "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

            # Verify no tokens or private URLs in client response
            self.assertNotIn("token", str(data).lower())
            self.assertNotIn("api.github.com", str(data))

    @patch("server.update_service.fetch_release_data")
    def test_latest_update_up_to_date(self, mock_fetch):
        """When client version matches remote version, returns update_available=False."""
        mock_fetch.return_value = {
            "tag_name": "v1.1.3",
            "assets": [
                {
                    "name": "Vyntra-Windows-x64.exe",
                    "url": "https://api.github.com/repos/SaminMp/Vyntra/releases/assets/101",
                    "size": 85000000,
                }
            ],
            "_checksums_map": {},
        }

        url = f"{self.base_url}/api/v1/updates/latest?platform=windows-x64&current_version=1.1.3"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertFalse(data["update_available"])
