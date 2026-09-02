"""
Configuration manager for Vyntra with persistent JSON storage.
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from vyntra.models import AudioQuality, MediaFormat, VideoQuality
from vyntra.utils.logger import logger


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

    def __post_init__(self):
        if not self.download_directory:
            # Default to ~/Downloads/Vyntra or ~/Downloads
            downloads_dir = Path.home() / "Downloads" / "Vyntra"
            self.download_directory = str(downloads_dir)


class ConfigManager:
    """Manages reading, updating, and saving user preferences."""

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            self.config_dir = Path.home() / ".vyntra"
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
