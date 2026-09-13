"""
Centralized configuration and constants for Vyntra's update subsystem.
Provides a single source of truth for repository information, release channels,
network timeouts, and staging directory locations.
"""

from pathlib import Path
from vyntra.config import get_app_data_dir


# GitHub Repository Coordinates
GITHUB_OWNER: str = "SaminMp"
GITHUB_REPO: str = "Vyntra"
GITHUB_API_BASE: str = "https://api.github.com"

# Official GitHub Releases endpoint
LATEST_RELEASE_API_URL: str = f"{GITHUB_API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
ALL_RELEASES_API_URL: str = f"{GITHUB_API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"

# Release channels
CHANNEL_STABLE: str = "stable"
CHANNEL_BETA: str = "beta"
DEFAULT_CHANNEL: str = CHANNEL_STABLE

# Supported operating system keys
PLATFORM_WINDOWS: str = "windows"
PLATFORM_MACOS: str = "darwin"

# Supported CPU architectures
ARCH_X64: str = "x64"
ARCH_ARM64: str = "arm64"

# Network timeouts (seconds)
NETWORK_CONNECT_TIMEOUT: float = 8.0
NETWORK_READ_TIMEOUT: float = 15.0

# HTTP User Agent
USER_AGENT_TEMPLATE: str = "Vyntra-Desktop/{version} (GitHub-Release-Updater)"

# Checksum file conventions in releases
CHECKSUM_FILE_NAMES = (
    "SHA256SUMS.txt",
    "checksums.txt",
    "sha256sums.txt",
)


def get_updates_dir() -> Path:
    """Returns directory for updater temporary artifacts and scripts."""
    updates_dir = get_app_data_dir() / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    return updates_dir


def get_staging_dir() -> Path:
    """Returns temporary staging directory for downloaded release assets."""
    staging_dir = get_updates_dir() / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    return staging_dir
