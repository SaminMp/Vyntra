"""
Theme and design tokens for Vyntra desktop interface.
"""

from typing import Tuple


class Theme:
    """Color palette, fonts, and dimensional tokens for Vyntra UI."""

    # Brand & Core Accents
    PRIMARY = "#6366F1"          # Indigo 500
    PRIMARY_HOVER = "#4F46E5"    # Indigo 600
    PRIMARY_ACTIVE = "#4338CA"   # Indigo 700

    ACCENT_CYAN = "#06B6D4"      # Cyan 500
    ACCENT_CYAN_HOVER = "#0891B2"

    # Status Colors
    SUCCESS = "#10B981"          # Emerald 500
    SUCCESS_BG = "#064E3B"
    WARNING = "#F59E0B"          # Amber 500
    WARNING_BG = "#78350F"
    ERROR = "#EF4444"            # Rose 500
    ERROR_BG = "#7F1D1D"

    # Backgrounds (Deep Slate / Obsidian)
    BG_MAIN = "#0B0F19"          # Darkest background
    BG_SIDEBAR = "#111827"       # Secondary background
    BG_CARD = "#1E293B"          # Card background
    BG_CARD_HOVER = "#283548"    # Card hover
    BG_CARD_SELECTED = "#272E48" # Selected card
    BG_INPUT = "#1E293B"         # Input background
    BG_MUTED = "#334155"         # Subtle muted container

    # Borders & Dividers
    BORDER_SUBTLE = "#1F2937"
    BORDER_CARD = "#334155"
    BORDER_SELECTED = "#6366F1"
    BORDER_HIGHLIGHT = "#38BDF8"

    # Typography Colors
    TEXT_PRIMARY = "#F8FAFC"     # White / Near white
    TEXT_SECONDARY = "#94A3B8"   # Slate 400
    TEXT_MUTED = "#64748B"       # Slate 500
    TEXT_ACCENT = "#818CF8"      # Light Indigo

    # Fonts
    FONT_FAMILY = "Segoe UI"     # Cross-platform fallback handled by CTk
    
    FONT_TITLE: Tuple[str, int, str] = (FONT_FAMILY, 20, "bold")
    FONT_HEADER: Tuple[str, int, str] = (FONT_FAMILY, 15, "bold")
    FONT_SUBHEADER: Tuple[str, int, str] = (FONT_FAMILY, 13, "bold")
    FONT_BODY: Tuple[str, int, str] = (FONT_FAMILY, 12, "normal")
    FONT_BODY_BOLD: Tuple[str, int, str] = (FONT_FAMILY, 12, "bold")
    FONT_CAPTION: Tuple[str, int, str] = (FONT_FAMILY, 11, "normal")
    FONT_BADGE: Tuple[str, int, str] = (FONT_FAMILY, 10, "bold")

    # Dimensions & Corner Radii
    RADIUS_CARD = 12
    RADIUS_BUTTON = 8
    RADIUS_INPUT = 8
    RADIUS_BADGE = 6
