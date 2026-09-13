"""
Semantic version parsing, normalization, and comparison utilities for Vyntra.
Guarantees correct numerical evaluation (e.g. 1.10.0 > 1.9.0) and handles
optional leading 'v' prefixes and pre-release identifiers.
"""

from dataclasses import dataclass
import re
from typing import Optional, Tuple


_SEMVER_REGEX = re.compile(
    r"^[vV]?(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?(?:-(?P<prerelease>[0-9A-Za-z.-]+))?$"
)


@dataclass(frozen=True)
class SemVer:
    """Represents a parsed Semantic Version."""
    major: int
    minor: int
    patch: int
    prerelease: Optional[str] = None

    @property
    def is_prerelease(self) -> bool:
        return self.prerelease is not None

    def as_tuple(self) -> Tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            return f"{base}-{self.prerelease}"
        return base

    def __eq__(self, other) -> bool:
        if not isinstance(other, SemVer):
            return False
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.prerelease == other.prerelease
        )

    def __lt__(self, other) -> bool:
        if not isinstance(other, SemVer):
            raise TypeError(f"Cannot compare SemVer with {type(other)}")

        self_core = self.as_tuple()
        other_core = other.as_tuple()

        if self_core != other_core:
            return self_core < other_core

        # Core numbers match: check prerelease
        # According to SemVer specification: a version with a prerelease is LOWER than a normal release
        # e.g. 1.2.0-beta < 1.2.0
        if self.prerelease is not None and other.prerelease is None:
            return True
        if self.prerelease is None and other.prerelease is not None:
            return False
        if self.prerelease is not None and other.prerelease is not None:
            return self.prerelease < other.prerelease

        return False

    def __le__(self, other) -> bool:
        return self == other or self < other

    def __gt__(self, other) -> bool:
        return not self <= other

    def __ge__(self, other) -> bool:
        return not self < other


def parse_version(version_str: str) -> Optional[SemVer]:
    """
    Parses a version string into a SemVer object.
    Strips leading 'v' or 'V' and whitespace.
    Returns None if the string does not conform to semantic versioning.
    """
    if not version_str or not isinstance(version_str, str):
        return None

    clean = version_str.strip()
    match = _SEMVER_REGEX.match(clean)
    if not match:
        return None

    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch_str = match.group("patch")
    patch = int(patch_str) if patch_str is not None else 0
    prerelease = match.group("prerelease")

    return SemVer(major=major, minor=minor, patch=patch, prerelease=prerelease)


def normalize_tag(tag: str) -> str:
    """
    Strips leading 'v' or 'V' from a release tag for standard display.
    Example: 'v1.2.4' -> '1.2.4'
    """
    if not tag:
        return ""
    clean = tag.strip()
    if clean.lower().startswith("v"):
        return clean[1:]
    return clean


def is_newer(candidate_version_str: str, base_version_str: str) -> bool:
    """
    Returns True if candidate_version_str is strictly greater than base_version_str.
    Returns False if either version string is invalid or candidate <= base.
    """
    candidate = parse_version(candidate_version_str)
    base = parse_version(base_version_str)

    if candidate is None or base is None:
        return False

    return candidate > base
