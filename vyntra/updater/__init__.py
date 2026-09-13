"""
Vyntra Automated Update Subsystem.
Provides background release discovery, cryptographic verification,
and detached platform-specific application replacement.
"""

from vyntra.updater.manager import UpdateManager, UpdateState, update_manager
from vyntra.updater.models import DownloadProgress, ReleaseAsset, ReleaseInfo, UpdateCheckResult
from vyntra.updater.version_utils import is_newer, normalize_tag, parse_version

__all__ = [
    "update_manager",
    "UpdateManager",
    "UpdateState",
    "ReleaseAsset",
    "ReleaseInfo",
    "UpdateCheckResult",
    "DownloadProgress",
    "is_newer",
    "normalize_tag",
    "parse_version",
]
