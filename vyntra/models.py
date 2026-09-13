"""
Data models and enumerations for Vyntra.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid


class Platform(str, Enum):
    """Supported media platforms."""
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    SPOTIFY = "spotify"


@dataclass
class PlatformCapabilities:
    """Defines the technical features supported by a platform."""
    platform_id: str
    display_name: str
    icon: str
    supports_search: bool = False
    supports_url_input: bool = True
    supports_video_playback: bool = True
    supports_audio_preview: bool = True
    supports_mp4: bool = True
    supports_mp3: bool = True
    supports_video_quality: bool = False
    supports_audio_quality: bool = True


class MediaFormat(str, Enum):
    """Supported output formats."""
    MP3 = "MP3"
    MP4 = "MP4"


class AudioQuality(str, Enum):
    """Audio quality presets (bitrate in kbps)."""
    STANDARD = "192"
    HIGH = "256"
    BEST = "320"


class VideoQuality(str, Enum):
    """Video resolution presets."""
    SD_480P = "480p"
    HD_720P = "720p"
    FHD_1080P = "1080p"
    BEST = "best"


class DownloadStatus(str, Enum):
    """Lifecycle status of a download job."""
    IDLE = "IDLE"
    PENDING = "PENDING"
    CONNECTING = "CONNECTING"
    DOWNLOADING = "DOWNLOADING"
    CONVERTING = "CONVERTING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class PlaybackState(str, Enum):
    """Playback state of video preview."""
    UNSTARTED = "UNSTARTED"
    BUFFERING = "BUFFERING"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    ENDED = "ENDED"
    ERROR = "ERROR"


@dataclass
class MediaItem:
    """
    Unified representation of a media item across all platforms.
    100% backward-compatible with SearchResult.
    """
    video_id: str
    title: str
    channel: str
    duration_seconds: int = 0
    duration_formatted: str = "00:00"
    views: Optional[int] = None
    views_formatted: str = "N/A"
    thumbnail_url: str = ""
    url: str = ""
    description: Optional[str] = ""
    publish_date: Optional[str] = ""
    # Multi-platform fields
    platform: str = Platform.YOUTUBE.value
    album: Optional[str] = None
    preview_url: Optional[str] = None
    audio_source_url: Optional[str] = None

    @property
    def display_title(self) -> str:
        """Returns clean title without leading/trailing whitespace."""
        return self.title.strip() if self.title else "Untitled Media"


# Backward-compatible alias: SearchResult is MediaItem
SearchResult = MediaItem


@dataclass
class ProgressInfo:
    """Snapshot of active download progress."""
    status: DownloadStatus = DownloadStatus.PENDING
    percent: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed_str: str = "-- KB/s"
    eta_str: str = "--:--"
    status_message: str = "Initializing..."
    filename: str = ""


@dataclass
class DownloadTask:
    """Represents an active or queued download job."""
    result: MediaItem
    format: MediaFormat
    save_directory: str
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    platform: str = Platform.YOUTUBE.value
    audio_quality: AudioQuality = AudioQuality.BEST
    video_quality: VideoQuality = VideoQuality.BEST
    selected_quality: str = "best"
    status: DownloadStatus = DownloadStatus.PENDING
    progress: ProgressInfo = field(default_factory=ProgressInfo)
    output_filepath: Optional[str] = None
    error_message: Optional[str] = None
    is_cancelled: bool = False

    def __post_init__(self):
        # Auto-inherit platform from result if not explicitly overridden
        if self.result and hasattr(self.result, "platform") and self.result.platform:
            self.platform = self.result.platform
