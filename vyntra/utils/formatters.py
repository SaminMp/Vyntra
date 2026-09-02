"""
Formatting utilities for human-readable numbers, durations, speeds, and file sizes.
"""

from typing import Optional, Union


def format_duration(seconds: Optional[Union[int, float]]) -> str:
    """
    Formats a duration in seconds into HH:MM:SS or MM:SS format.

    Examples:
        75 -> "01:15"
        3665 -> "01:01:05"
        None -> "00:00"
    """
    if seconds is None or seconds < 0:
        return "00:00"

    total_secs = int(seconds)
    hours = total_secs // 3600
    minutes = (total_secs % 3600) // 60
    secs = total_secs % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_bytes(num_bytes: Optional[Union[int, float]]) -> str:
    """
    Formats byte count into human-readable string (e.g., KB, MB, GB).

    Examples:
        1024 -> "1.00 KB"
        15728640 -> "15.00 MB"
    """
    if num_bytes is None or num_bytes <= 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    unit_index = 0

    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} B"
    return f"{size:.2f} {units[unit_index]}"


def format_speed(bytes_per_sec: Optional[Union[int, float]]) -> str:
    """
    Formats download speed into human-readable format (e.g. 2.45 MB/s).
    """
    if bytes_per_sec is None or bytes_per_sec <= 0:
        return "-- KB/s"
    return f"{format_bytes(bytes_per_sec)}/s"


def format_view_count(views: Optional[Union[int, float]]) -> str:
    """
    Formats numeric view count into short abbreviation (e.g. 1.5M views, 240K views).
    """
    if views is None:
        return "N/A"

    v = int(views)
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.1f}B views"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M views"
    if v >= 1_000:
        return f"{v / 1_000:.1f}K views"
    return f"{v:,} views"


def format_eta(seconds: Optional[Union[int, float]]) -> str:
    """
    Formats remaining time (ETA) in seconds into human-readable countdown string.
    """
    if seconds is None or seconds < 0:
        return "--:--"
    return format_duration(seconds)
