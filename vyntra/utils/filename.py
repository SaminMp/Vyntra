"""
Filename sanitization and unique path utilities with full Unicode & Persian support.
"""

import os
import re
import unicodedata
from pathlib import Path
from typing import Union


# Characters forbidden across Windows, macOS, and Linux
FORBIDDEN_CHARS_PATTERN = re.compile(r'[\/\\:\*\?"<>\|\x00-\x1f\x7f]')
# Multiple whitespace or invisible separator characters (excluding Persian ZWNJ \u200c)
MULTIPLE_SPACES_PATTERN = re.compile(r'[\s\u200b\uFEFF]+')


def sanitize_filename(name: str, max_length: int = 180, fallback: str = "Vyntra_Media") -> str:
    """
    Sanitizes a string to be safely used as a filename across all OS platforms,
    while fully preserving valid Unicode (Persian, Arabic, Japanese, European accents, etc.).

    Args:
        name: The raw title or string to sanitize.
        max_length: Maximum allowed length for the base filename (excluding extension).
        fallback: Fallback string if the sanitized result is empty.

    Returns:
        A safe, sanitized filename base string.
    """
    if not name:
        return fallback

    # Normalize Unicode characters (NFC form keeps Persian and composite glyphs intact)
    normalized = unicodedata.normalize("NFC", str(name))

    # Replace invalid filesystem characters with an underscore or space
    cleaned = FORBIDDEN_CHARS_PATTERN.sub(" ", normalized)

    # Collapse consecutive spaces into a single space
    cleaned = MULTIPLE_SPACES_PATTERN.sub(" ", cleaned).strip()

    # Strip leading or trailing periods and spaces (problematic on Windows/macOS)
    cleaned = cleaned.strip(". ")

    # Fallback if empty after cleaning
    if not cleaned:
        cleaned = fallback

    # Truncate length cleanly if needed, avoiding splitting multi-byte unicode code points
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(". ")

    return cleaned


def get_unique_filepath(directory: Union[str, Path], base_name: str, extension: str) -> Path:
    """
    Generates a unique file path in the target directory by appending (1), (2), etc.
    if a file with the same name already exists.

    Args:
        directory: Destination folder path.
        base_name: Desired base filename (sanitized).
        extension: File extension (e.g., '.mp3' or 'mp3').

    Returns:
        A Path object that does not currently exist on disk.
    """
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)

    clean_ext = f".{extension.lstrip('.')}"
    sanitized_base = sanitize_filename(base_name)

    candidate = dir_path / f"{sanitized_base}{clean_ext}"
    counter = 1

    while candidate.exists():
        candidate = dir_path / f"{sanitized_base} ({counter}){clean_ext}"
        counter += 1

    return candidate
