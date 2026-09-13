"""
Unit tests for platform detection and asset selection in Vyntra updater.
"""

import unittest
from unittest.mock import patch
from vyntra.updater.models import ReleaseAsset
from vyntra.updater.platform_detector import (
    get_current_arch,
    get_current_platform,
    select_platform_asset,
)


class TestUpdaterPlatform(unittest.TestCase):
    """Verifies OS/Arch resolution and platform-specific release asset filtering."""

    def test_current_platform_and_arch(self):
        plat = get_current_platform()
        self.assertIn(plat, ["windows", "darwin", "linux"])
        arch = get_current_arch()
        self.assertIn(arch, ["x64", "arm64"])

    @patch("vyntra.updater.platform_detector.get_current_platform", return_value="windows")
    @patch("vyntra.updater.platform_detector.get_current_arch", return_value="x64")
    def test_windows_asset_selection(self, mock_arch, mock_plat):
        assets = [
            ReleaseAsset(name="SHA256SUMS.txt", download_url="http://example.com/sums", size=100),
            ReleaseAsset(name="Vyntra-macOS-arm64.dmg", download_url="http://example.com/mac", size=50000000),
            ReleaseAsset(name="Vyntra-Windows-x64.exe", download_url="http://example.com/win", size=60000000),
        ]
        chosen = select_platform_asset(assets)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.name, "Vyntra-Windows-x64.exe")

    @patch("vyntra.updater.platform_detector.get_current_platform", return_value="darwin")
    @patch("vyntra.updater.platform_detector.get_current_arch", return_value="arm64")
    def test_macos_arm64_asset_selection(self, mock_arch, mock_plat):
        assets = [
            ReleaseAsset(name="SHA256SUMS.txt", download_url="http://example.com/sums", size=100),
            ReleaseAsset(name="Vyntra-macOS-x64.dmg", download_url="http://example.com/intel", size=50000000),
            ReleaseAsset(name="Vyntra-macOS-arm64.dmg", download_url="http://example.com/arm", size=50000000),
            ReleaseAsset(name="Vyntra-Windows-x64.exe", download_url="http://example.com/win", size=60000000),
        ]
        chosen = select_platform_asset(assets)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.name, "Vyntra-macOS-arm64.dmg")

    @patch("vyntra.updater.platform_detector.get_current_platform", return_value="darwin")
    @patch("vyntra.updater.platform_detector.get_current_arch", return_value="x64")
    def test_macos_intel_asset_selection(self, mock_arch, mock_plat):
        assets = [
            ReleaseAsset(name="Vyntra-macOS-arm64.dmg", download_url="http://example.com/arm", size=50000000),
            ReleaseAsset(name="Vyntra-macOS-x64.dmg", download_url="http://example.com/intel", size=50000000),
        ]
        chosen = select_platform_asset(assets)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.name, "Vyntra-macOS-x64.dmg")

    @patch("vyntra.updater.platform_detector.get_current_platform", return_value="windows")
    @patch("vyntra.updater.platform_detector.get_current_arch", return_value="x64")
    def test_windows_asset_selection_prefers_exe_over_zip(self, mock_arch, mock_plat):
        """Verifies that .exe is prioritized over .zip even if .zip is listed first."""
        assets = [
            ReleaseAsset(name="SHA256SUMS.txt", download_url="http://example.com/sums", size=100),
            ReleaseAsset(name="Vyntra-Windows-x64.zip", download_url="http://example.com/win.zip", size=60000000),
            ReleaseAsset(name="Vyntra-Windows-x64.exe", download_url="http://example.com/win.exe", size=60000000),
        ]
        chosen = select_platform_asset(assets)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.name, "Vyntra-Windows-x64.exe")

    @patch("vyntra.updater.platform_detector.get_current_platform", return_value="windows")
    @patch("vyntra.updater.platform_detector.get_current_arch", return_value="x64")
    def test_no_compatible_asset_returns_none(self, mock_arch, mock_plat):
        assets = [
            ReleaseAsset(name="Vyntra-macOS-arm64.dmg", download_url="http://example.com/arm", size=50000000),
            ReleaseAsset(name="Vyntra-macOS-x64.dmg", download_url="http://example.com/intel", size=50000000),
        ]
        chosen = select_platform_asset(assets)
        self.assertIsNone(chosen)


class TestWindowsInstaller(unittest.TestCase):
    """Verifies WindowsInstaller script generation, detached process launch, and clean process exit."""

    def test_missing_staged_file_raises_not_found(self):
        from vyntra.updater.installers.windows_installer import WindowsInstaller
        from pathlib import Path
        installer = WindowsInstaller()
        with self.assertRaises(FileNotFoundError):
            installer.install_and_restart(
                staged_file=Path("non_existent_payload.exe"),
                target_path=Path("target.exe"),
            )

    @patch("os._exit")
    @patch("subprocess.Popen")
    def test_installer_generates_script_and_exits(self, mock_popen, mock_os_exit):
        from vyntra.updater.installers.windows_installer import WindowsInstaller
        import tempfile
        from pathlib import Path

        installer = WindowsInstaller()
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp) / "Vyntra-Windows-x64.exe"
            staged.write_text("dummy new exe")
            target = Path(tmp) / "Vyntra.exe"
            target.write_text("dummy old exe")

            installer.install_and_restart(staged_file=staged, target_path=target)

            mock_popen.assert_called_once()
            args, kwargs = mock_popen.call_args
            self.assertEqual(args[0][0], "cmd.exe")
            self.assertEqual(args[0][1], "/c")
            self.assertTrue(kwargs.get("close_fds"))

            # Verify batch script was created and contains key directives
            script_path = Path(args[0][2])
            self.assertTrue(script_path.exists())
            content = script_path.read_text(encoding="utf-8")
            self.assertIn("tasklist", content)
            self.assertIn("taskkill", content)
            self.assertIn("replace_loop", content)
            self.assertIn("replace_success", content)

            # Verify os._exit(0) was invoked to immediately release OS file locks
            mock_os_exit.assert_called_once_with(0)


class TestMacOSInstaller(unittest.TestCase):
    """Verifies MacOSInstaller script generation, detached process launch, and clean process exit."""

    def test_missing_staged_dmg_raises_not_found(self):
        from vyntra.updater.installers.macos_installer import MacOSInstaller
        from pathlib import Path
        installer = MacOSInstaller()
        with self.assertRaises(FileNotFoundError):
            installer.install_and_restart(
                staged_file=Path("non_existent_payload.dmg"),
                target_path=Path("Vyntra.app"),
            )

    @patch("os._exit")
    @patch("subprocess.Popen")
    def test_macos_installer_generates_script_and_exits(self, mock_popen, mock_os_exit):
        from vyntra.updater.installers.macos_installer import MacOSInstaller
        import tempfile
        from pathlib import Path

        installer = MacOSInstaller()
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp) / "Vyntra-macOS.dmg"
            staged.write_text("dummy dmg payload")
            target = Path(tmp) / "Vyntra.app"
            target.mkdir(parents=True, exist_ok=True)

            installer.install_and_restart(staged_file=staged, target_path=target)

            mock_popen.assert_called_once()
            args, kwargs = mock_popen.call_args
            self.assertEqual(args[0][0], "/bin/bash")
            self.assertTrue(kwargs.get("close_fds"))

            script_path = Path(args[0][1])
            self.assertTrue(script_path.exists())
            content = script_path.read_text(encoding="utf-8")
            self.assertIn("hdiutil attach", content)
            self.assertIn("hdiutil detach", content)
            self.assertIn("kill -0", content)

            mock_os_exit.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
