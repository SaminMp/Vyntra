"""
Configuration manager for Vyntra with persistent JSON storage.
"""

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from vyntra.models import AudioQuality, MediaFormat, VideoQuality
from vyntra.utils.logger import logger


def get_app_data_dir() -> Path:
    """
    Resolves standard OS-specific user application data directory.
    - Windows: %APPDATA%/Vyntra (e.g. C:\\Users\\<user>\\AppData\\Roaming\\Vyntra)
    - macOS: ~/Library/Application Support/Vyntra
    - Linux / Other: $XDG_CONFIG_HOME/vyntra or ~/.config/vyntra
    Maintains backward compatibility: if ~/.vyntra already exists, keeps using it.
    """
    legacy_dir = Path.home() / ".vyntra"
    if legacy_dir.is_dir():
        return legacy_dir

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Vyntra"
        return Path.home() / "AppData" / "Roaming" / "Vyntra"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Vyntra"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            return Path(xdg) / "vyntra"
        return Path.home() / ".config" / "vyntra"


@dataclass
class AppConfig:
    """User configuration schema."""
    download_directory: str = ""
    default_format: str = MediaFormat.MP3.value
    audio_quality: str = AudioQuality.BEST.value
    video_quality: str = VideoQuality.BEST.value
    max_search_results: int = 12
    custom_ffmpeg_path: str = ""
    theme_mode: str = "dark"
    color_theme: str = "blue"
    auth_connected: bool = False
    auth_status: str = "disconnected"   # "connected", "disconnected", "expired"
    setup_completed: bool = False
    donation_prompt_dismissed: bool = False

    # YouTube Media Access Authentication (cleanly separated from Google OAuth Identity)
    youtube_media_auth_mode: str = "none"   # "none", "browser", "cookie_file"
    youtube_media_browser: str = "firefox"  # "firefox", "chrome", "edge", "brave", "opera"
    youtube_media_browser_profile: str = ""
    youtube_media_custom_cookie_path: str = ""
    youtube_media_status: str = "unconfigured"  # "ready", "unconfigured", "failed"
    youtube_media_status_message: str = ""

    # Multi-platform settings
    instagram_custom_cookie_path: str = ""
    tiktok_custom_cookie_path: str = ""

    def __post_init__(self):
        if not self.download_directory:
            # Default to ~/Downloads/Vyntra or ~/Downloads
            downloads_dir = Path.home() / "Downloads" / "Vyntra"
            self.download_directory = str(downloads_dir)


class ConfigManager:
    """Manages reading, updating, and saving user preferences."""

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            self.config_dir = get_app_data_dir()
        else:
            self.config_dir = Path(config_dir)

        self.config_file = self.config_dir / "config.json"
        self._config: AppConfig = self._load()

    @property
    def config(self) -> AppConfig:
        return self._config

    def _load(self) -> AppConfig:
        """Loads configuration from JSON file, or creates defaults if missing."""
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data: Dict[str, Any] = json.load(f)
                config = AppConfig(**{k: v for k, v in data.items() if k in AppConfig.__annotations__})
                logger.info("Loaded user configuration from %s", self.config_file)
                return config
        except Exception as err:
            logger.warning("Failed to load config file (%s), using defaults. Error: %s", self.config_file, err)

        # Initialize with defaults and save
        default_config = AppConfig()
        self._ensure_paths(default_config)
        self._save_to_disk(default_config)
        return default_config

    def _ensure_paths(self, config: AppConfig) -> None:
        """Creates config and download directories if they do not exist."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            Path(config.download_directory).mkdir(parents=True, exist_ok=True)
        except Exception as err:
            logger.error("Error creating directories: %s", err)

    def _save_to_disk(self, config: AppConfig) -> None:
        """Writes configuration to JSON file on disk."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(asdict(config), f, indent=4, ensure_ascii=False)
        except Exception as err:
            logger.error("Failed to save config to disk: %s", err)

    def save(self) -> None:
        """Saves current state of self._config to disk."""
        self._ensure_paths(self._config)
        self._save_to_disk(self._config)

    def update(self, **kwargs) -> None:
        """Updates one or more configuration keys and persists changes."""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
        self.save()


# Singleton instance for easy import across modules
config_manager = ConfigManager()
