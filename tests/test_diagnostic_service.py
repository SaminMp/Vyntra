"""
Unit tests for safe diagnostic reporting service.
"""

import unittest
from vyntra.services.diagnostic_service import (
    diagnostic_service,
    sanitize_proxy_url,
    get_proxy_status,
)


class TestDiagnosticService(unittest.TestCase):
    """Tests for non-sensitive diagnostic report generation."""

    def test_sanitize_proxy_url(self):
        self.assertEqual(sanitize_proxy_url(None), "NONE")
        self.assertEqual(sanitize_proxy_url(""), "NONE")

        # Plain proxy without credentials
        self.assertEqual(sanitize_proxy_url("http://127.0.0.1:8080"), "http://127.0.0.1:8080")

        # Proxy with user and password MUST be masked
        masked = sanitize_proxy_url("http://admin:secret123@proxy.example.com:3128")
        self.assertNotIn("admin", masked)
        self.assertNotIn("secret123", masked)
        self.assertIn("***:***", masked)
        self.assertIn("proxy.example.com:3128", masked)

    def test_full_diagnostics_no_secrets(self):
        report = diagnostic_service.generate_full_diagnostics()
        self.assertIn("Vyntra Diagnostics", report)
        self.assertIn("Version:", report)
        self.assertIn("Platform:", report)
        self.assertIn("Google Account:", report)
        self.assertIn("YouTube Media:", report)
        self.assertIn("yt-dlp Version:", report)

        # Confirm zero credentials/tokens
        self.assertNotIn("Bearer", report)
        self.assertNotIn("refresh_token", report)
        self.assertNotIn("client_secret", report)
        self.assertNotIn("SAPISID", report)

    def test_network_diagnostics_no_secrets(self):
        report = diagnostic_service.generate_network_diagnostics()
        self.assertIn("Vyntra Network Diagnostics", report)
        self.assertIn("Internet connectivity:", report)
        self.assertIn("HTTPS connectivity:", report)
        self.assertIn("TLS:", report)
        self.assertIn("Search endpoint:", report)


if __name__ == "__main__":
    unittest.main()
