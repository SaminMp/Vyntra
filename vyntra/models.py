"""
Data models and enumerations for Vyntra.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid


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


@dataclass
class SearchResult:
    """Represents a single YouTube video search result."""
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

    @property
    def display_title(self) -> str:
        """Returns clean title without leading/trailing whitespace."""
        return self.title.strip() if self.title else "Untitled Video"


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
    result: SearchResult
    format: MediaFormat
    save_directory: str
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    audio_quality: AudioQuality = AudioQuality.BEST
    video_quality: VideoQuality = VideoQuality.BEST
    status: DownloadStatus = DownloadStatus.PENDING
    progress: ProgressInfo = field(default_factory=ProgressInfo)
    output_filepath: Optional[str] = None
    error_message: Optional[str] = None
    is_cancelled: bool = False
