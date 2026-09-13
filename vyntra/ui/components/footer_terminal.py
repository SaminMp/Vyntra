"""
Interactive bottom terminal / activity console component for Vyntra.
Provides a persistent, futuristic footer terminal that records all notifications,
downloads, platform events, and system statuses without ever overlapping or
obscuring navigation buttons.
"""

from datetime import datetime
import threading
from typing import Callable, Optional
import customtkinter as ctk

from vyntra.ui.theme import Theme


class FooterTerminal(ctk.CTkFrame):
    """
    Sleek, futuristic footer terminal and activity log.
    Sits persistently at the bottom of the window, displaying timestamped,
    color-coded notification events, download progress logs, and system messages.
    Supports expansion/collapse, action buttons, and buffer clearing.
    """

    MAX_BUFFER_LINES = 250

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            corner_radius=Theme.RADIUS_CARD,
            fg_color=Theme.BG_CARD,
            border_width=1,
            border_color=Theme.BORDER_CARD,
            **kwargs,
        )

        self._is_collapsed = False
        self._action_callback: Optional[Callable[[], None]] = None
        self._line_count = 0

        self.grid_columnconfigure(0, weight=1)

        # 1. Header Control Bar
        self.header_bar = ctk.CTkFrame(self, fg_color="transparent", height=28)
        self.header_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 4))
        self.header_bar.grid_columnconfigure(2, weight=1)

        # Terminal prompt prefix
        self.title_label = ctk.CTkLabel(
            self.header_bar,
            text=">_ Terminal",
            font=(Theme.FONT_FAMILY, 11, "bold"),
            text_color="#94A3B8",
        )
        self.title_label.grid(row=0, column=0, padx=(2, 6), sticky="w")

        # Status badge indicator (● LIVE / ● READY)
        self.status_badge = ctk.CTkLabel(
            self.header_bar,
            text="● READY",
            font=(Theme.FONT_FAMILY, 10, "bold"),
            text_color="#10B981",
            fg_color="#064E3B",
            corner_radius=6,
            padx=6,
            pady=1,
        )
        self.status_badge.grid(row=0, column=1, padx=(0, 10), sticky="w")

        # Latest message summary preview
        self.summary_label = ctk.CTkLabel(
            self.header_bar,
            text="System initialized. Ready for media search and downloads.",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            anchor="w",
        )
        self.summary_label.grid(row=0, column=2, padx=4, sticky="ew")

        # Context action button (e.g. 'Open Folder', 'Copy Command')
        self.action_btn = ctk.CTkButton(
            self.header_bar,
            text="Action",
            font=Theme.FONT_CAPTION,
            height=22,
            width=80,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._on_action_clicked,
        )
        self.action_btn.grid(row=0, column=3, padx=(4, 6), sticky="e")
        self.action_btn.grid_remove()

        # Clear terminal button
        self.clear_btn = ctk.CTkButton(
            self.header_bar,
            text="Clear",
            font=Theme.FONT_CAPTION,
            height=22,
            width=46,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            text_color=Theme.TEXT_MUTED,
            command=self.clear,
        )
        self.clear_btn.grid(row=0, column=4, padx=(0, 6), sticky="e")

        # Minimize / Expand toggle button
        self.toggle_btn = ctk.CTkButton(
            self.header_bar,
            text="▼ Minimize",
            font=Theme.FONT_CAPTION,
            height=22,
            width=76,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            text_color=Theme.TEXT_MUTED,
            command=self.toggle_collapse,
        )
        self.toggle_btn.grid(row=0, column=5, sticky="e")

        # 2. Terminal Text Display Box
        self.textbox = ctk.CTkTextbox(
            self,
            height=76,
            fg_color="#070B12",
            text_color="#E2E8F0",
            font=("Consolas", 11),
            wrap="word",
            corner_radius=6,
            border_width=1,
            border_color="#1E293B",
        )
        self.textbox.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        # Text tag color styling
        self.textbox.tag_config("time", foreground="#64748B")
        self.textbox.tag_config("info", foreground="#38BDF8")
        self.textbox.tag_config("success", foreground="#10B981")
        self.textbox.tag_config("warning", foreground="#F59E0B")
        self.textbox.tag_config("error", foreground="#EF4444")
        self.textbox.tag_config("msg", foreground="#E2E8F0")

        # Start ready log entry
        self.log("Vyntra terminal initialized. Hardware A/V engine active.", level="info")

    def log(
        self,
        message: str,
        level: str = "info",
        action_text: Optional[str] = None,
        on_action: Optional[Callable[[], None]] = None,
    ):
        """
        Thread-safe logger method that writes a color-coded timestamped line to the terminal.
        """
        # If called from background thread, marshal to Tkinter event loop
        if threading.current_thread() is not threading.main_thread():
            try:
                self.after(0, lambda: self.log(message, level, action_text, on_action))
            except Exception:
                pass
            return

        lvl = level.lower()
        now_str = datetime.now().strftime("%H:%M:%S")

        # Level display mapping
        tag_map = {
            "info": "INFO",
            "success": "SUCCESS",
            "warning": "WARN",
            "error": "ERROR",
        }
        tag_text = tag_map.get(lvl, lvl.upper())

        # Update summary in header
        clean_msg = message.replace("\n", " ").strip()
        if self.summary_label.winfo_exists():
            self.summary_label.configure(text=clean_msg)

        # Update status badge
        if self.status_badge.winfo_exists():
            if lvl == "error":
                self.status_badge.configure(text="● ERROR", text_color="#EF4444", fg_color="#450A0A")
            elif lvl == "warning":
                self.status_badge.configure(text="● ALERT", text_color="#F59E0B", fg_color="#451A03")
            elif lvl == "success":
                self.status_badge.configure(text="● SUCCESS", text_color="#10B981", fg_color="#064E3B")
            else:
                self.status_badge.configure(text="● READY", text_color="#38BDF8", fg_color="#082F49")

        # Handle Action Button
        self._action_callback = on_action
        if action_text and on_action and self.action_btn.winfo_exists():
            self.action_btn.configure(text=action_text)
            self.action_btn.grid()
        elif self.action_btn.winfo_exists():
            self.action_btn.grid_remove()

        # Insert into textbox
        if self.textbox.winfo_exists():
            self.textbox.configure(state="normal")

            # Prune buffer if exceeding line threshold
            self._line_count += 1
            if self._line_count > self.MAX_BUFFER_LINES:
                self.textbox.delete("1.0", "50.0")
                self._line_count -= 49

            self.textbox.insert("end", f"[{now_str}] ", "time")
            self.textbox.insert("end", f"[{tag_text:^7}] ", lvl if lvl in tag_map else "info")
            self.textbox.insert("end", f"{clean_msg}\n", "msg")
            self.textbox.see("end")
            self.textbox.configure(state="disabled")

    # -------------------------------------------------------------------------
    # Backward Compatibility Methods with StatusBanner Interface
    # -------------------------------------------------------------------------
    def show_info(self, message: str):
        """Logs informational notification."""
        self.log(message, level="info")

    def show_success(
        self,
        message: str,
        action_text: Optional[str] = None,
        on_action: Optional[Callable[[], None]] = None,
    ):
        """Logs success notification with optional action button."""
        self.log(message, level="success", action_text=action_text, on_action=on_action)

    def show_warning(
        self,
        message: str,
        action_text: Optional[str] = None,
        on_action: Optional[Callable[[], None]] = None,
    ):
        """Logs warning notification with optional action button."""
        self.log(message, level="warning", action_text=action_text, on_action=on_action)

    def show_error(
        self,
        message: str,
        action_text: Optional[str] = None,
        on_action: Optional[Callable[[], None]] = None,
    ):
        """Logs error notification with optional action button."""
        self.log(message, level="error", action_text=action_text, on_action=on_action)

    def hide(self):
        """Safe no-op for backward compatibility."""
        if self.action_btn.winfo_exists():
            self.action_btn.grid_remove()

    def clear(self):
        """Clears terminal buffer and resets status."""
        if self.textbox.winfo_exists():
            self.textbox.configure(state="normal")
            self.textbox.delete("1.0", "end")
            self.textbox.configure(state="disabled")
        self._line_count = 0
        if self.summary_label.winfo_exists():
            self.summary_label.configure(text="Terminal buffer cleared.")
        if self.status_badge.winfo_exists():
            self.status_badge.configure(text="● READY", text_color="#10B981", fg_color="#064E3B")
        if self.action_btn.winfo_exists():
            self.action_btn.grid_remove()

    def toggle_collapse(self):
        """Toggles between expanded terminal view and minimized single-line summary bar."""
        self._is_collapsed = not self._is_collapsed
        if self._is_collapsed:
            self.textbox.grid_remove()
            self.toggle_btn.configure(text="▲ Expand")
        else:
            self.textbox.grid()
            self.toggle_btn.configure(text="▼ Minimize")
            self.textbox.see("end")

    def _on_action_clicked(self):
        if self._action_callback:
            try:
                self._action_callback()
            except Exception as e:
                self.log(f"Action execution error: {e}", level="error")
