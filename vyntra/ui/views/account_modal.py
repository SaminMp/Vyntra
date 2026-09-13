"""
YouTube Account and Authentication Management Dialog for Vyntra.
"""

from typing import Callable, Optional
import customtkinter as ctk

from vyntra.services.auth_service import auth_service
from vyntra.ui.theme import Theme


class AccountModal(ctk.CTkToplevel):
    """Dialog for managing in-app YouTube / Google account connection."""

    def __init__(self, master, on_changed: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(master, **kwargs)

        self.on_changed = on_changed
        self.title("YouTube Account & Session Management")
        self.geometry("520x490")
        self.resizable(False, False)
        self.configure(fg_color=Theme.BG_MAIN)

        try:
            self.transient(master)
            if master and master.winfo_ismapped():
                self.grab_set()
        except Exception:
            pass

        self._auth_listener = self._on_external_auth_changed
        auth_service.add_auth_listener(self._auth_listener)

        self.grid_columnconfigure(0, weight=1)

        # Header Title
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=24, pady=(20, 10))

        title_label = ctk.CTkLabel(
            header_frame,
            text="🔐 YouTube Account",
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_PRIMARY,
        )
        title_label.pack(anchor="w")

        # Container Card
        self.card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        self.card.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        self.card.grid_columnconfigure(0, weight=1)

        self._build_content()

    def _build_content(self):
        # 1. Status Banner
        status_box = ctk.CTkFrame(self.card, fg_color=Theme.BG_MAIN, corner_radius=Theme.RADIUS_BUTTON)
        status_box.pack(fill="x", padx=16, pady=16)

        status_key, label, msg = auth_service.get_connection_status()
        status_color = Theme.SUCCESS if status_key == "connected" else Theme.TEXT_MUTED

        self.status_title = ctk.CTkLabel(status_box, text=label, font=Theme.FONT_HEADER, text_color=status_color)
        self.status_title.pack(padx=14, pady=(10, 2), anchor="w")

        self.status_msg = ctk.CTkLabel(status_box, text=msg, font=Theme.FONT_CAPTION, text_color=Theme.TEXT_SECONDARY, justify="left", wraplength=440)
        self.status_msg.pack(padx=14, pady=(0, 6), anchor="w")

        _, media_label, media_msg = auth_service.get_media_access_status()
        self.media_status_lbl = ctk.CTkLabel(
            status_box,
            text=f"{media_label}  —  {media_msg}",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            justify="left",
            wraplength=440,
        )
        self.media_status_lbl.pack(padx=14, pady=(0, 10), anchor="w")

        # 2. Action Buttons
        btn_box = ctk.CTkFrame(self.card, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=(4, 14))

        self.signin_btn = ctk.CTkButton(
            btn_box,
            text="🌐 Sign in with Google",
            font=Theme.FONT_SUBHEADER,
            height=36,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.ACCENT_CYAN,
            hover_color=Theme.ACCENT_CYAN_HOVER,
            command=self._handle_signin,
        )
        self.signin_btn.pack(side="left", padx=(0, 10))

        self.signout_btn = ctk.CTkButton(
            btn_box,
            text="Sign Out",
            font=Theme.FONT_BODY,
            height=36,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.ERROR_BG,
            command=self._handle_signout,
        )
        self.signout_btn.pack(side="left", padx=(0, 10))

        self.test_btn = ctk.CTkButton(
            btn_box,
            text="🧪 Test Connection",
            font=Theme.FONT_CAPTION,
            height=36,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._handle_test,
        )
        self.test_btn.pack(side="left")

        # 3. Security Guarantee & Architecture Note Box
        sec_box = ctk.CTkFrame(self.card, fg_color=Theme.BG_MAIN, corner_radius=Theme.RADIUS_BUTTON)
        sec_box.pack(fill="x", padx=16, pady=(4, 16))

        sec_lbl = ctk.CTkLabel(
            sec_box,
            text=(
                "🔒 Google Identity & YouTube Media Architecture:\n"
                "• Google OAuth authenticates your identity, profile, and playlists.\n"
                "• Vyntra NEVER sees, captures, or stores your Google password.\n"
                "• Media extraction (playback/downloads) is powered by Innertube media sessions "
                "configured in Settings ⚙️ -> Media Access."
            ),
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            justify="left",
            wraplength=440,
        )
        sec_lbl.pack(padx=12, pady=10, anchor="w")

        # Bottom Close Button
        close_btn = ctk.CTkButton(
            self,
            text="Close",
            font=Theme.FONT_SUBHEADER,
            height=36,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self.destroy,
        )
        close_btn.pack(side="bottom", padx=24, pady=(0, 20), fill="x")

    def destroy(self):
        try:
            if hasattr(self, "_auth_listener"):
                auth_service.remove_auth_listener(self._auth_listener)
        except Exception:
            pass
        super().destroy()

    def _on_external_auth_changed(self):
        try:
            if self.winfo_exists():
                self.after(0, self._refresh_ui)
        except Exception:
            pass

    def _refresh_ui(self):
        try:
            if not self.winfo_exists():
                return
            status_key, label, details = auth_service.get_connection_status()
            status_color = Theme.SUCCESS if status_key == "connected" else Theme.TEXT_MUTED
            self.status_title.configure(text=label, text_color=status_color)
            self.status_msg.configure(text=details, text_color=Theme.TEXT_SECONDARY)
            _, media_label, media_msg = auth_service.get_media_access_status()
            self.media_status_lbl.configure(text=f"{media_label}  —  {media_msg}")
            if self.on_changed:
                self.on_changed()
        except Exception:
            pass

    def _handle_signin(self):
        self.signin_btn.configure(state="disabled", text="Opening Browser...")
        self.status_msg.configure(text="Complete sign-in in your browser...", text_color=Theme.TEXT_MUTED)

        def _on_done(success: bool, msg: str):
            self.after(0, lambda: self._on_signin_finished(success, msg))

        auth_service.launch_google_signin(_on_done)

    def _on_signin_finished(self, success: bool, msg: str):
        try:
            if not self.winfo_exists():
                if self.on_changed:
                    self.on_changed()
                return
            self.signin_btn.configure(state="normal", text="🌐 Sign in with Google")
            status_key, label, details = auth_service.get_connection_status()
            if success:
                self.status_title.configure(text=label, text_color=Theme.SUCCESS)
                self.status_msg.configure(text=msg, text_color=Theme.TEXT_SECONDARY)
            else:
                self.status_title.configure(text="⚠️ Google Sign-In Failed", text_color=Theme.WARNING)
                self.status_msg.configure(text=f"Google authentication could not be completed:\n{msg}", text_color=Theme.WARNING)

            _, media_label, media_msg = auth_service.get_media_access_status()
            self.media_status_lbl.configure(text=f"{media_label}  —  {media_msg}")

            if self.on_changed:
                self.on_changed()
        except Exception:
            if self.on_changed:
                try:
                    self.on_changed()
                except Exception:
                    pass


    def _handle_signout(self):
        auth_service.disconnect()
        status_key, label, details = auth_service.get_connection_status()
        self.status_title.configure(text=label, text_color=Theme.TEXT_MUTED)
        self.status_msg.configure(text=details)
        if self.on_changed:
            self.on_changed()

    def _handle_test(self):
        self.test_btn.configure(state="disabled", text="Testing...")
        self.status_msg.configure(text="Verifying connection with Google and YouTube...")

        def _worker():
            success, msg = auth_service.test_connection()
            self.after(0, lambda: self._on_test_finished(success, msg))

        import threading
        threading.Thread(target=_worker, daemon=True).start()

    def _on_test_finished(self, success: bool, msg: str):
        self.test_btn.configure(state="normal", text="🧪 Test Connection")
        self.status_msg.configure(text=msg)
        _, media_label, media_msg = auth_service.get_media_access_status()
        self.media_status_lbl.configure(text=f"{media_label}  —  {media_msg}")
