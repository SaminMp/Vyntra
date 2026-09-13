"""
Data models and representations for Vyntra update subsystem.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional






@dataclass
class ReleaseAsset:
    """Represents a downloadable binary or metadata asset attached to a GitHub Release."""
    name: str
    download_url: str
    size: int
    asset_id: Optional[int] = None
    api_url: Optional[str] = None
    sha256: Optional[str] = None
    platform: Optional[str] = None    # "windows" or "darwin"
    arch: Optional[str] = None        # "x64" or "arm64"
    content_type: str = ""

    @property
    def size_mb(self) -> float:
        return self.size / (1024 * 1024) if self.size > 0 else 0.0


@dataclass
class ReleaseInfo:
    """Represents parsed metadata from a published GitHub Release."""
    version: str
    tag: str
    name: str
    release_notes: str
    published_at: str
    is_draft: bool = False
    is_prerelease: bool = False
    assets: List[ReleaseAsset] = field(default_factory=list)
    checksums: Dict[str, str] = field(default_factory=dict)
    html_url: str = ""

    def get_asset_by_name(self, name: str) -> Optional[ReleaseAsset]:
        for a in self.assets:
            if a.name.lower() == name.lower():
                return a
        return None


@dataclass
class UpdateCheckResult:
    """Result of an update check evaluation."""
    status: str                         # "available", "up_to_date", "no_asset", "error", "auth_required"
    current_version: str
    latest_release: Optional[ReleaseInfo] = None
    target_asset: Optional[ReleaseAsset] = None
    error_message: Optional[str] = None
    auth_status: str = "ok"             # "ok", "unauthenticated", "invalid_token"

    @property
    def has_update(self) -> bool:
        return self.status == "available" and self.target_asset is not None


@dataclass
class DownloadProgress:
    """Snapshot of active update download state."""
    downloaded_bytes: int = 0
    total_bytes: int = 0
    percent: float = 0.0
    speed_bps: float = 0.0
    is_complete: bool = False
    status_text: str = ""

    @property
    def downloaded_mb(self) -> float:
        return self.downloaded_bytes / (1024 * 1024)

    @property
    def total_mb(self) -> float:
        return self.total_bytes / (1024 * 1024)

    @property
    def speed_mbps(self) -> float:
        return self.speed_bps / (1024 * 1024)
