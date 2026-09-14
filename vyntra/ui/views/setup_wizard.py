"""
Simplified Initial Onboarding and Setup Wizard for Vyntra with 1-Click Google Sign-In.
"""

from pathlib import Path
from tkinter import filedialog
from typing import Callable, Optional
import customtkinter as ctk

from vyntra.config import config_manager
from vyntra.models import MediaFormat
from vyntra.services.auth_service import auth_service
from vyntra.ui.theme import Theme


class SetupWizard(ctk.CTkToplevel):
    """Multi-step onboarding wizard for first-time setup and 1-click Google authentication."""

    def __init__(self, master, on_completed: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(master, **kwargs)

        self.on_completed = on_completed
        self.title("Welcome to Vyntra - Initial Setup")
        self.geometry("620x560")
        self.resizable(False, False)
        self.configure(fg_color=Theme.BG_MAIN)

        try:
            self.transient(master)
            if master and master.winfo_ismapped():
                self.grab_set()
        except Exception:
            pass

        self._current_step = 1

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=0, sticky="nsew", padx=28, pady=24)
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(1, weight=1)

        self._show_step(1)

    def _clear_container(self):
        for child in self.main_container.winfo_children():
            child.destroy()

    def _show_step(self, step_number: int):
        self._current_step = step_number
        self._clear_container()

        if step_number == 1:
            self._render_step_welcome()
        elif step_number == 2:
            self._render_step_auth()
        elif step_number == 3:
            self._render_step_preferences()
        elif step_number == 4:
            self._render_step_finish()

    # --- STEP 1: WELCOME ---
    def _render_step_welcome(self):
        step_lbl = ctk.CTkLabel(self.main_container, text="STEP 1 OF 3  •  WELCOME", font=Theme.FONT_BADGE, text_color=Theme.PRIMARY)
        step_lbl.pack(anchor="w", pady=(0, 10))

        icon_lbl = ctk.CTkLabel(self.main_container, text="🎵", font=(Theme.FONT_FAMILY, 54))
        icon_lbl.pack(pady=(16, 10))

        title_lbl = ctk.CTkLabel(self.main_container, text="Welcome to Vyntra", font=Theme.FONT_TITLE, text_color=Theme.TEXT_PRIMARY)
        title_lbl.pack(pady=(0, 6))

        sub_lbl = ctk.CTkLabel(
            self.main_container,
            text="The modern YouTube media player & high-quality audio/video downloader for your desktop.",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_SECONDARY,
            wraplength=480,
            justify="center",
        )
        sub_lbl.pack(pady=(0, 20))

        card = ctk.CTkFrame(self.main_container, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        card.pack(fill="x", pady=(0, 24), padx=8)

        items = [
            ("🔍 Instant YouTube Search", "Search millions of tracks, albums, and videos in real time."),
            ("🎬 Live Full Player", "Watch and listen from start to finish with video and audio."),
            ("🎧 Crystal-Clear MP3 / MP4", "High-bitrate conversion with automatic metadata tagging."),
        ]

        for head, desc in items:
            row_frame = ctk.CTkFrame(card, fg_color="transparent")
            row_frame.pack(fill="x", padx=16, pady=8)
            h = ctk.CTkLabel(row_frame, text=head, font=Theme.FONT_BODY_BOLD, text_color=Theme.TEXT_PRIMARY)
            h.pack(anchor="w")
            d = ctk.CTkLabel(row_frame, text=desc, font=Theme.FONT_CAPTION, text_color=Theme.TEXT_MUTED)
            d.pack(anchor="w")

        next_btn = ctk.CTkButton(
            self.main_container,
            text="Get Started  →",
            font=Theme.FONT_SUBHEADER,
            height=40,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=lambda: self._show_step(2),
        )
        next_btn.pack(side="bottom", fill="x", padx=8)

    # --- STEP 2: 1-CLICK GOOGLE SIGN-IN ---
    def _render_step_auth(self):
        step_lbl = ctk.CTkLabel(self.main_container, text="STEP 2 OF 3  •  AUTHENTICATION", font=Theme.FONT_BADGE, text_color=Theme.PRIMARY)
        step_lbl.pack(anchor="w", pady=(0, 6))

        title_lbl = ctk.CTkLabel(self.main_container, text="Connect Your YouTube Account", font=Theme.FONT_TITLE, text_color=Theme.TEXT_PRIMARY)
        title_lbl.pack(anchor="w", pady=(0, 4))

        info_box = ctk.CTkFrame(self.main_container, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        info_box.pack(fill="x", pady=(6, 14))

        info_text = (
            "Google sign-in is required to authorize YouTube access for streaming video, "
            "format extraction, and downloads.\n\n"
            "🛡️ Privacy & Security Guarantee:\n"
            "• Vyntra does NOT store, collect, or share your personal data or password.\n"
            "• You authenticate directly through official Google OAuth 2.0.\n"
            "• Credentials are stored exclusively in your local device OS Keyring."
        )
        info_lbl = ctk.CTkLabel(
            info_box,
            text=info_text,
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_SECONDARY,
            justify="left",
            wraplength=520,
        )
        info_lbl.pack(padx=16, pady=12, anchor="w")

        # Action Box
        auth_card = ctk.CTkFrame(self.main_container, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        auth_card.pack(fill="x", pady=(0, 16))

        btn_box = ctk.CTkFrame(auth_card, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=16)

        self.signin_btn = ctk.CTkButton(
            btn_box,
            text="🌐 Sign in with Google",
            font=Theme.FONT_HEADER,
            height=42,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.ACCENT_CYAN,
            hover_color=Theme.ACCENT_CYAN_HOVER,
            command=self._handle_signin,
        )
        self.signin_btn.pack(fill="x", pady=(0, 10))

        status_key, label, msg = auth_service.get_connection_status()
        status_color = Theme.SUCCESS if status_key == "connected" else Theme.TEXT_MUTED

        self.status_label = ctk.CTkLabel(
            btn_box,
            text=f"Status: {label}",
            font=Theme.FONT_BODY_BOLD,
            text_color=status_color,
        )
        self.status_label.pack(anchor="center")

        # Bottom Navigation
        nav_row = ctk.CTkFrame(self.main_container, fg_color="transparent")
        nav_row.pack(side="bottom", fill="x")

        self.continue_btn = ctk.CTkButton(
            nav_row,
            text="Continue  →",
            font=Theme.FONT_SUBHEADER,
            height=38,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY if status_key == "connected" else Theme.BG_MUTED,
            hover_color=Theme.PRIMARY_HOVER if status_key == "connected" else Theme.BG_CARD_HOVER,
            state="normal" if status_key == "connected" else "disabled",
            command=lambda: self._show_step(3),
        )
        self.continue_btn.pack(side="right")

    def _handle_signin(self):
        self.signin_btn.configure(state="disabled", text="Opening Google Sign-In...")
        self.status_label.configure(text="Complete sign-in in your browser...", text_color=Theme.TEXT_MUTED)

        def _on_done(success: bool, msg: str):
            self.after(0, lambda: self._on_signin_finished(success, msg))

        auth_service.launch_google_signin(_on_done)

    def _on_signin_finished(self, success: bool, msg: str):
        self.signin_btn.configure(state="normal", text="🌐 Sign in with Google")
        status_key, label, _ = auth_service.get_connection_status()
        is_connected = (status_key == "connected")
        self.status_label.configure(
            text=f"Status: {label}",
            text_color=Theme.SUCCESS if is_connected else Theme.ERROR,
        )
        if hasattr(self, "continue_btn") and self.continue_btn.winfo_exists():
            if is_connected:
                self.continue_btn.configure(
                    state="normal",
                    fg_color=Theme.PRIMARY,
                    hover_color=Theme.PRIMARY_HOVER,
                )
            else:
                self.continue_btn.configure(
                    state="disabled",
                    fg_color=Theme.BG_MUTED,
                    hover_color=Theme.BG_CARD_HOVER,
                )

    # --- STEP 3: PREFERENCES ---
    def _render_step_preferences(self):
        step_lbl = ctk.CTkLabel(self.main_container, text="STEP 3 OF 3  •  DOWNLOAD PREFERENCES", font=Theme.FONT_BADGE, text_color=Theme.PRIMARY)
        step_lbl.pack(anchor="w", pady=(0, 6))

        title_lbl = ctk.CTkLabel(self.main_container, text="Configure Download Folder", font=Theme.FONT_TITLE, text_color=Theme.TEXT_PRIMARY)
        title_lbl.pack(anchor="w", pady=(0, 16))

        pref_card = ctk.CTkFrame(self.main_container, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        pref_card.pack(fill="x", pady=(0, 20))
        pref_card.grid_columnconfigure(0, weight=1)

        f_lbl = ctk.CTkLabel(pref_card, text="Save Destination Folder:", font=Theme.FONT_BODY_BOLD, text_color=Theme.TEXT_PRIMARY)
        f_lbl.grid(row=0, column=0, columnspan=2, padx=16, pady=(16, 4), sticky="w")

        self.folder_entry = ctk.CTkEntry(pref_card, font=Theme.FONT_CAPTION, fg_color=Theme.BG_INPUT, border_color=Theme.BORDER_CARD, height=32)
        self.folder_entry.insert(0, config_manager.config.download_directory)
        self.folder_entry.grid(row=1, column=0, padx=(16, 8), pady=(0, 14), sticky="ew")

        b_btn = ctk.CTkButton(
            pref_card,
            text="Browse",
            font=Theme.FONT_CAPTION,
            width=70,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=self._browse_folder,
        )
        b_btn.grid(row=1, column=1, padx=(0, 16), pady=(0, 14), sticky="e")

        fmt_lbl = ctk.CTkLabel(pref_card, text="Default Download Format:", font=Theme.FONT_BODY_BOLD, text_color=Theme.TEXT_PRIMARY)
        fmt_lbl.grid(row=2, column=0, padx=16, pady=4, sticky="w")

        self.fmt_seg = ctk.CTkSegmentedButton(
            pref_card,
            values=[MediaFormat.MP3.value, MediaFormat.MP4.value],
            selected_color=Theme.PRIMARY,
            command=self._on_format_changed,
        )
        self.fmt_seg.set(config_manager.config.default_format)
        self.fmt_seg.grid(row=2, column=1, padx=16, pady=4, sticky="e")

        self.q_lbl = ctk.CTkLabel(pref_card, text="Default Quality:", font=Theme.FONT_BODY_BOLD, text_color=Theme.TEXT_PRIMARY)
        self.q_lbl.grid(row=3, column=0, padx=16, pady=(10, 16), sticky="w")

        self.q_opt = ctk.CTkOptionMenu(pref_card, values=["320 kbps (Best)", "256 kbps", "192 kbps", "128 kbps"], fg_color=Theme.BG_MUTED, button_color=Theme.PRIMARY)
        self.q_opt.grid(row=3, column=1, padx=16, pady=(10, 16), sticky="e")
        self._on_format_changed(config_manager.config.default_format)

        nav_row = ctk.CTkFrame(self.main_container, fg_color="transparent")
        nav_row.pack(side="bottom", fill="x")

        back_btn = ctk.CTkButton(
            nav_row,
            text="← Back",
            font=Theme.FONT_BODY,
            height=38,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            command=lambda: self._show_step(2),
        )
        back_btn.pack(side="left")

        finish_step_btn = ctk.CTkButton(
            nav_row,
            text="Complete Setup  →",
            font=Theme.FONT_SUBHEADER,
            height=38,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._finish_preferences,
        )
        finish_step_btn.pack(side="right")

    def _browse_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.folder_entry.get())
        if chosen:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, chosen)

    def _on_format_changed(self, value: str):
        if value == MediaFormat.MP3.value:
            self.q_lbl.configure(text="Default Audio Quality:")
            self.q_opt.configure(values=["320 kbps (Best)", "256 kbps", "192 kbps", "128 kbps"])
            self.q_opt.set("320 kbps (Best)")
        else:
            self.q_lbl.configure(text="Default Video Quality:")
            self.q_opt.configure(values=["Best (Auto)", "1080p (FHD)", "720p (HD)", "480p (SD)", "360p"])
            self.q_opt.set("Best (Auto)")

    def _finish_preferences(self):
        folder = self.folder_entry.get().strip() or str(Path.home() / "Downloads" / "Vyntra")
        fmt = self.fmt_seg.get()
        q_str = self.q_opt.get()

        update_kwargs = {
            "download_directory": folder,
            "default_format": fmt,
        }

        if fmt == MediaFormat.MP3.value:
            q_val = "320"
            if "192" in q_str:
                q_val = "192"
            elif "256" in q_str:
                q_val = "256"
            elif "128" in q_str:
                q_val = "128"
            update_kwargs["audio_quality"] = q_val
        else:
            v_val = "best"
            for res in ["1080p", "720p", "480p", "360p"]:
                if res in q_str.lower():
                    v_val = res
                    break
            update_kwargs["video_quality"] = v_val

        config_manager.update(**update_kwargs)
        self._show_step(4)

    # --- STEP 4: READY / FINISH ---
    def _render_step_finish(self):
        icon_lbl = ctk.CTkLabel(self.main_container, text="🎉", font=(Theme.FONT_FAMILY, 54))
        icon_lbl.pack(pady=(20, 10))

        title_lbl = ctk.CTkLabel(self.main_container, text="You're All Set!", font=Theme.FONT_TITLE, text_color=Theme.TEXT_PRIMARY)
        title_lbl.pack(pady=(0, 8))

        sub_lbl = ctk.CTkLabel(
            self.main_container,
            text="Vyntra is configured and ready for search, full video streaming, and media downloads.",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_SECONDARY,
            wraplength=480,
            justify="center",
        )
        sub_lbl.pack(pady=(0, 20))

        card = ctk.CTkFrame(self.main_container, fg_color=Theme.BG_CARD, corner_radius=Theme.RADIUS_CARD)
        card.pack(fill="x", padx=16, pady=(0, 24))

        status_key, label, _ = auth_service.get_connection_status()
        status_color = Theme.SUCCESS if status_key == "connected" else Theme.TEXT_MUTED

        summary_rows = [
            ("YouTube Account", label, status_color),
            ("Save Destination", config_manager.config.download_directory, Theme.TEXT_PRIMARY),
            ("Default Format", config_manager.config.default_format, Theme.TEXT_PRIMARY),
        ]

        for head, val, col in summary_rows:
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=8)
            h = ctk.CTkLabel(r, text=head, font=Theme.FONT_BODY_BOLD, text_color=Theme.TEXT_SECONDARY)
            h.pack(side="left")
            v = ctk.CTkLabel(r, text=val, font=Theme.FONT_CAPTION, text_color=col)
            v.pack(side="right")

        launch_btn = ctk.CTkButton(
            self.main_container,
            text="🚀 Launch Vyntra",
            font=Theme.FONT_HEADER,
            height=44,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._complete_setup,
        )
        launch_btn.pack(side="bottom", fill="x", padx=12)

    def _complete_setup(self):
        config_manager.update(setup_completed=True)
        if self.on_completed:
            self.on_completed()
        self.destroy()

    def destroy(self):
        try:
            for aid in self.tk.splitlist(self.tk.eval("after info")):
                try:
                    self.tk.eval(f"after cancel {aid}")
                except Exception:
                    pass
        except Exception:
            pass
        try:
            super().destroy()
        except Exception:
            pass
