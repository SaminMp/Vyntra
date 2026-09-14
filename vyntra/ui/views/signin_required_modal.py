"""
Mandatory Google Sign-In Modal for Vyntra.

Enforces authentication before allowing application usage, providing
clear explanation regarding YouTube authorization and local privacy guarantees.
"""

import sys
from typing import Callable, Optional
import customtkinter as ctk

from vyntra.services.auth_service import auth_service
from vyntra.ui.theme import Theme
from vyntra.utils.logger import logger


class SignInRequiredModal(ctk.CTkToplevel):
    """
    Mandatory modal dialog displayed when user is not authenticated.
    Blocks app interaction until Google sign-in completes successfully.
    """

    def __init__(self, master, on_success: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(master, **kwargs)

        self.on_success = on_success
        self.title("Vyntra - Sign-In Required")
        self.geometry("540x510")
        self.resizable(False, False)
        self.configure(fg_color=Theme.BG_MAIN)

        try:
            self.transient(master)
            if master and master.winfo_ismapped():
                self.grab_set()
        except Exception:
            pass

        # Closing this window exits the application because sign-in is mandatory
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self._auth_listener = self._on_auth_state_changed
        auth_service.add_auth_listener(self._auth_listener)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=0, sticky="nsew", padx=28, pady=24)
        self.main_container.grid_columnconfigure(0, weight=1)

        self._build_ui()

    def _build_ui(self):
        # 1. Header Banner
        header_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 14))

        badge = ctk.CTkLabel(
            header_frame,
            text="AUTHENTICATION REQUIRED",
            font=Theme.FONT_BADGE,
            text_color=Theme.PRIMARY,
        )
        badge.pack(anchor="center", pady=(0, 6))

        icon_lbl = ctk.CTkLabel(header_frame, text="🎵", font=(Theme.FONT_FAMILY, 48))
        icon_lbl.pack(pady=(4, 6))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="Welcome to Vyntra",
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_PRIMARY,
        )
        title_lbl.pack(anchor="center")

        subtitle_lbl = ctk.CTkLabel(
            header_frame,
            text="Please sign in with your Google account to continue",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_SECONDARY,
        )
        subtitle_lbl.pack(anchor="center", pady=(2, 0))

        # 2. Explanation & Privacy Guarantee Card
        info_card = ctk.CTkFrame(self.main_container, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        info_card.pack(fill="x", pady=(0, 18), padx=4)

        # YouTube Authorization Note
        yt_head = ctk.CTkLabel(
            info_card,
            text="🔐 Why is Sign-In Required?",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.TEXT_PRIMARY,
        )
        yt_head.pack(anchor="w", padx=16, pady=(14, 4))

        yt_desc = ctk.CTkLabel(
            info_card,
            text=(
                "Google sign-in is required to authorize YouTube access for streaming video, "
                "extracting high-quality formats, and downloading media."
            ),
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_SECONDARY,
            justify="left",
            wraplength=440,
        )
        yt_desc.pack(anchor="w", padx=16, pady=(0, 12))

        # Privacy Guarantee Note
        priv_head = ctk.CTkLabel(
            info_card,
            text="🛡️ Your Privacy is 100% Protected",
            font=Theme.FONT_BODY_BOLD,
            text_color=Theme.SUCCESS,
        )
        priv_head.pack(anchor="w", padx=16, pady=(0, 4))

        priv_desc = ctk.CTkLabel(
            info_card,
            text=(
                "• Vyntra does NOT store, collect, or share your personal data or password.\n"
                "• All authentication happens securely through official Google OAuth 2.0.\n"
                "• Credentials are stored exclusively in your local device OS Keyring."
            ),
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            justify="left",
            wraplength=440,
        )
        priv_desc.pack(anchor="w", padx=16, pady=(0, 14))

        # 3. Action Button & Live Status
        action_card = ctk.CTkFrame(self.main_container, fg_color="transparent")
        action_card.pack(fill="x", pady=(0, 10))

        self.signin_btn = ctk.CTkButton(
            action_card,
            text="🌐 Sign in with Google",
            font=Theme.FONT_HEADER,
            height=44,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.ACCENT_CYAN,
            hover_color=Theme.ACCENT_CYAN_HOVER,
            command=self._handle_signin,
        )
        self.signin_btn.pack(fill="x", pady=(0, 8))

        status_key, label, _ = auth_service.get_connection_status()
        status_color = Theme.SUCCESS if status_key == "connected" else Theme.TEXT_MUTED

        self.status_label = ctk.CTkLabel(
            action_card,
            text=f"Status: {label}",
            font=Theme.FONT_BODY_BOLD,
            text_color=status_color,
        )
        self.status_label.pack(anchor="center")

    def _handle_signin(self):
        self.signin_btn.configure(state="disabled", text="Opening Google Sign-In...")
        self.status_label.configure(
            text="Complete sign-in in your system browser...",
            text_color=Theme.TEXT_MUTED,
        )

        def _on_done(success: bool, msg: str):
            self.after(0, lambda: self._on_signin_finished(success, msg))

        auth_service.launch_google_signin(_on_done)

    def _on_signin_finished(self, success: bool, msg: str):
        if not self.winfo_exists():
            return
        self.signin_btn.configure(state="normal", text="🌐 Sign in with Google")
        status_key, label, _ = auth_service.get_connection_status()

        if success and status_key == "connected":
            self.status_label.configure(text=f"Status: {label}", text_color=Theme.SUCCESS)
            self.after(600, self._complete_success)
        else:
            self.status_label.configure(text=f"⚠️ {msg}", text_color=Theme.ERROR)

    def _on_auth_state_changed(self):
        if not self.winfo_exists():
            return
        status_key, label, _ = auth_service.get_connection_status()
        if status_key == "connected":
            self.status_label.configure(text=f"Status: {label}", text_color=Theme.SUCCESS)
            self.after(600, self._complete_success)

    def _complete_success(self):
        auth_service.remove_auth_listener(self._auth_listener)
        try:
            self.grab_release()
        except Exception:
            pass
        if self.on_success:
            self.on_success()
        self.destroy()

    def _on_window_close(self):
        """Exits the application if user closes without signing in."""
        logger.info("[Auth] User closed mandatory sign-in dialog. Exiting application.")
        auth_service.remove_auth_listener(self._auth_listener)
        try:
            self.grab_release()
        except Exception:
            pass
        if self.master:
            self.master.destroy()
        sys.exit(0)
