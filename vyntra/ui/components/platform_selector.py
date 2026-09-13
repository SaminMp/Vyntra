"""
Centralized multi-platform navigation selector for Vyntra.
Provides high-visibility, visually highlighted platform switching with dedicated
branding accents, clear icons, and centralized platform metadata.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
import customtkinter as ctk

from vyntra.models import Platform
from vyntra.ui.theme import Theme


@dataclass
class PlatformMeta:
    id: str
    name: str
    icon: str
    subtitle: str
    accent_color: str
    active_bg: str


PLATFORM_METADATA: Dict[str, PlatformMeta] = {
    "youtube": PlatformMeta(
        id="youtube",
        name="YouTube",
        icon="▶",
        subtitle="Search, watch and download videos with hardware A/V sync",
        accent_color="#FF3B30",
        active_bg="#2A1418",
    ),
    "instagram": PlatformMeta(
        id="instagram",
        name="Instagram",
        icon="◎",
        subtitle="Search, watch and download supported reels and posts",
        accent_color="#E1306C",
        active_bg="#2A1220",
    ),
    "tiktok": PlatformMeta(
        id="tiktok",
        name="TikTok",
        icon="♪",
        subtitle="Watch and download high-quality videos without watermarks",
        accent_color="#00F2FE",
        active_bg="#0E232B",
    ),
    "spotify": PlatformMeta(
        id="spotify",
        name="Spotify",
        icon="♫",
        subtitle="Search music, stream 30s previews, and download high-fidelity MP3s",
        accent_color="#1DB954",
        active_bg="#102618",
    ),
}


PLATFORM_ORDER = ["youtube", "instagram", "tiktok", "spotify"]


class PlatformSelector(ctk.CTkFrame):
    """
    High-visibility, adaptive platform navigation bar.
    Dynamically reorganizes between:
      - Wide (>= 820px): 4 buttons side-by-side (1x4)
      - Medium (520px - 819px): 2x2 grid of buttons
      - Compact (< 520px): Adaptive platform selector dropdown
    Guarantees no overlapping, clipping, or inaccessible buttons.
    """

    BREAKPOINT_WIDE = 820
    BREAKPOINT_MEDIUM = 520

    def __init__(
        self,
        master,
        current_platform: str = "youtube",
        on_platform_changed: Optional[Callable[[str], None]] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.on_platform_changed = on_platform_changed
        self._current_platform = current_platform.lower()
        self._layout_mode: Optional[str] = None

        self._buttons: Dict[str, ctk.CTkButton] = {}
        self._build_widgets()

        # Initial layout mode
        self._apply_layout("wide")

        # Bind resize configuration to adapt dynamically
        self.bind("<Configure>", self._on_configure)

    def _build_widgets(self):
        """Constructs both navigation buttons and compact fallback selector."""
        # 1. Navigation Buttons for grid modes
        for pid in PLATFORM_ORDER:
            meta = PLATFORM_METADATA[pid]
            btn = ctk.CTkButton(
                self,
                text=f"{meta.icon}  {meta.name}",
                font=Theme.FONT_BODY_BOLD,
                height=40,
                corner_radius=Theme.RADIUS_BUTTON,
                border_width=1,
                command=lambda p=pid: self._select_platform(p),
            )
            self._buttons[pid] = btn

        # 2. Compact container for narrow viewports
        self._compact_frame = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        self._compact_frame.grid_columnconfigure(1, weight=1)

        compact_lbl = ctk.CTkLabel(
            self._compact_frame,
            text="Platform:",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_SECONDARY,
        )
        compact_lbl.grid(row=0, column=0, padx=(14, 8), pady=8, sticky="w")

        compact_options = [f"{PLATFORM_METADATA[p].icon}  {PLATFORM_METADATA[p].name}" for p in PLATFORM_ORDER]
        self._compact_option = ctk.CTkOptionMenu(
            self._compact_frame,
            values=compact_options,
            font=Theme.FONT_BODY_BOLD,
            height=34,
            fg_color=Theme.BG_MUTED,
            button_color=Theme.PRIMARY,
            button_hover_color=Theme.PRIMARY_HOVER,
            dropdown_fg_color=Theme.BG_CARD,
            command=self._on_compact_selected,
        )
        self._compact_option.grid(row=0, column=1, padx=(0, 12), pady=8, sticky="ew")

        self._update_button_styles()

    def _on_configure(self, event):
        """Responds to width changes by switching layout modes smoothly."""
        width = event.width
        if width <= 1:
            return

        if width >= self.BREAKPOINT_WIDE:
            target_mode = "wide"
        elif width >= self.BREAKPOINT_MEDIUM:
            target_mode = "medium"
        else:
            target_mode = "compact"

        if target_mode != self._layout_mode:
            self._apply_layout(target_mode)

    def _apply_layout(self, mode: str):
        """Applies grid layout according to active responsiveness mode."""
        self._layout_mode = mode

        if mode == "wide":
            self._compact_frame.grid_remove()
            self.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="plat_col_wide")
            self.grid_rowconfigure((0, 1), weight=0)

            for col, pid in enumerate(PLATFORM_ORDER):
                btn = self._buttons[pid]
                btn.grid(row=0, column=col, padx=5, pady=4, sticky="ew")

        elif mode == "medium":
            self._compact_frame.grid_remove()
            # 2 columns x 2 rows
            self.grid_columnconfigure((0, 1), weight=1, uniform="plat_col_med")
            self.grid_columnconfigure((2, 3), weight=0, uniform="")
            self.grid_rowconfigure((0, 1), weight=0)

            # Row 0: YouTube, Instagram
            self._buttons["youtube"].grid(row=0, column=0, padx=5, pady=4, sticky="ew")
            self._buttons["instagram"].grid(row=0, column=1, padx=5, pady=4, sticky="ew")
            # Row 1: TikTok, Spotify
            self._buttons["tiktok"].grid(row=1, column=0, padx=5, pady=4, sticky="ew")
            self._buttons["spotify"].grid(row=1, column=1, padx=5, pady=4, sticky="ew")

        elif mode == "compact":
            for btn in self._buttons.values():
                btn.grid_remove()

            self.grid_columnconfigure((1, 2, 3), weight=0, uniform="")
            self.grid_columnconfigure(0, weight=1, uniform="")
            self.grid_rowconfigure(0, weight=0)
            self._compact_frame.grid(row=0, column=0, padx=4, pady=4, sticky="ew")

    def _on_compact_selected(self, selected_str: str):
        """Handles selection change from the compact dropdown."""
        for pid in PLATFORM_ORDER:
            meta = PLATFORM_METADATA[pid]
            if meta.name.lower() in selected_str.lower():
                self._select_platform(pid)
                break

    def _select_platform(self, platform_id: str):
        pid = platform_id.lower()
        if pid == self._current_platform:
            return
        self._current_platform = pid
        self._update_button_styles()
        if self.on_platform_changed:
            self.on_platform_changed(pid)

    def _update_button_styles(self):
        """Applies active and inactive styles across buttons and compact selector."""
        for pid, btn in self._buttons.items():
            meta = PLATFORM_METADATA.get(pid)
            if not meta:
                continue

            if pid == self._current_platform:
                # Active Platform: High-visibility highlight + colored accent border
                btn.configure(
                    fg_color=meta.active_bg,
                    text_color="#FFFFFF",
                    border_color=meta.accent_color,
                    border_width=2,
                    hover_color=meta.active_bg,
                    text=f"●  {meta.icon}  {meta.name}",
                )
            else:
                # Inactive Platform: Subtle background with clear label
                btn.configure(
                    fg_color=Theme.BG_CARD,
                    text_color=Theme.TEXT_SECONDARY,
                    border_color=Theme.BORDER_CARD,
                    border_width=1,
                    hover_color=Theme.BG_CARD_HOVER,
                    text=f"{meta.icon}  {meta.name}",
                )

        # Sync compact option menu
        current_meta = PLATFORM_METADATA.get(self._current_platform)
        if current_meta and hasattr(self, "_compact_option"):
            self._compact_option.set(f"{current_meta.icon}  {current_meta.name}")
            self._compact_option.configure(button_color=current_meta.accent_color)

    def get_selected_platform(self) -> str:
        return self._current_platform

    def set_platform(self, platform_id: str):
        pid = platform_id.lower()
        if pid in PLATFORM_METADATA and pid != self._current_platform:
            self._current_platform = pid
            self._update_button_styles()

