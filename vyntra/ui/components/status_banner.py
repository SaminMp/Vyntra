"""
Notification and status banner component for Vyntra.
"""

import os
import subprocess
import sys
from typing import Callable, Optional
import customtkinter as ctk

from vyntra.ui.theme import Theme


class StatusBanner(ctk.CTkFrame):
    """Dynamic alert banner for warnings, successes, and errors."""

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.WARNING_BG,
            border_width=1,
            border_color=Theme.WARNING,
            **kwargs,
        )

        self.grid_columnconfigure(1, weight=1)

        # Icon / Type indicator
        self.icon_label = ctk.CTkLabel(
            self,
            text="⚠️",
            font=(Theme.FONT_FAMILY, 14),
            width=28,
        )
        self.icon_label.grid(row=0, column=0, padx=(12, 6), pady=8, sticky="w")

        # Message Text
        self.message_label = ctk.CTkLabel(
            self,
            text="",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_PRIMARY,
            anchor="w",
            justify="left",
            wraplength=600,
        )
        self.message_label.grid(row=0, column=1, padx=6, pady=8, sticky="ew")

        # Optional Action Button (e.g. 'Open Folder' or 'Copy Command')
        self.action_btn = ctk.CTkButton(
            self,
            text="Action",
            font=Theme.FONT_CAPTION,
            height=26,
            width=90,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._on_action_click,
        )
        self.action_callback: Optional[Callable[[], None]] = None

        # Dismiss Button
        self.dismiss_btn = ctk.CTkButton(
            self,
            text="✕",
            font=(Theme.FONT_FAMILY, 12, "bold"),
            width=24,
            height=24,
            corner_radius=12,
            fg_color="transparent",
            hover_color=Theme.BG_CARD_HOVER,
            text_color=Theme.TEXT_SECONDARY,
            command=self.hide,
        )
        self.dismiss_btn.grid(row=0, column=3, padx=(6, 10), pady=8, sticky="e")

        # Hidden by default
        self._is_visible = False

    def show_warning(self, message: str, action_text: Optional[str] = None, on_action: Optional[Callable[[], None]] = None):
        """Displays warning banner with amber styling."""
        self.configure(fg_color=Theme.WARNING_BG, border_color=Theme.WARNING)
        self.icon_label.configure(text="⚠️")
        self._show(message, action_text, on_action)

    def show_success(self, message: str, action_text: Optional[str] = None, on_action: Optional[Callable[[], None]] = None):
        """Displays success banner with emerald styling."""
        self.configure(fg_color=Theme.SUCCESS_BG, border_color=Theme.SUCCESS)
        self.icon_label.configure(text="✓")
        self._show(message, action_text, on_action)

    def show_error(self, message: str, action_text: Optional[str] = None, on_action: Optional[Callable[[], None]] = None):
        """Displays error banner with rose styling."""
        self.configure(fg_color=Theme.ERROR_BG, border_color=Theme.ERROR)
        self.icon_label.configure(text="✕")
        self._show(message, action_text, on_action)

    def show_info(self, message: str):
        """Displays info banner with indigo styling."""
        self.configure(fg_color=Theme.BG_CARD, border_color=Theme.PRIMARY)
        self.icon_label.configure(text="ℹ")
        self._show(message, None, None)

    def _show(self, message: str, action_text: Optional[str], on_action: Optional[Callable[[], None]]):
        self.message_label.configure(text=message)
        self.action_callback = on_action

        if action_text and on_action:
            self.action_btn.configure(text=action_text)
            self.action_btn.grid(row=0, column=2, padx=8, pady=8, sticky="e")
        else:
            self.action_btn.grid_forget()

        if not self._is_visible:
            self.grid(row=1, column=0, sticky="ew", padx=16, pady=(6, 0))
            self._is_visible = True

    def hide(self):
        """Hides the banner."""
        if self._is_visible:
            self.grid_remove()
            self._is_visible = False

    def _on_action_click(self):
        if self.action_callback:
            self.action_callback()
