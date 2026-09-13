"""
Donation and project support modal dialog for Vyntra.
Presents the official USDT crypto donation wallet address with one-click copy,
network guidance, and user prompt preferences.
"""

from __future__ import annotations

from typing import Optional, Set
import customtkinter as ctk

from vyntra.config import config_manager
from vyntra.ui.theme import Theme
from vyntra.utils.logger import logger

USDT_WALLET_ADDRESS = "0x9B3493BF0459BAE41B39AbBF0BCdBb9C76699eE7"
SUPPORTED_NETWORKS = ["ERC-20", "BEP-20 (BSC)", "Polygon", "Arbitrum"]


class DonationModal(ctk.CTkToplevel):
    """Interactive modal dialog presenting USDT donation details and clipboard copy."""

    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)

        self._tracked_after_ids: Set[str] = set()

        self.title("Support Vyntra Development")
        self.geometry("540x510")
        self.minsize(480, 460)
        self.configure(fg_color=Theme.BG_MAIN)

        # macOS / Headless safety: only attach transient and grab if master is mapped
        try:
            if master and master.winfo_ismapped():
                self.transient(master)
                self.grab_set()
        except Exception:
            pass

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # 1. Header Banner
        header_frame = ctk.CTkFrame(self, fg_color=Theme.BG_SIDEBAR, height=68, corner_radius=0)
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            header_frame,
            text="💖  Support Vyntra",
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_PRIMARY,
        )
        title_label.grid(row=0, column=0, padx=24, pady=(14, 2), sticky="w")

        subtitle_label = ctk.CTkLabel(
            header_frame,
            text="Help keep Vyntra fast, free, and ad-free for everyone.",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_SECONDARY,
        )
        subtitle_label.grid(row=1, column=0, padx=24, pady=(0, 14), sticky="w")

        # 2. Main Content Card
        content_card = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_CARD,
            corner_radius=Theme.RADIUS_CARD,
            border_width=1,
            border_color=Theme.BORDER_CARD,
        )
        content_card.grid(row=1, column=0, sticky="nsew", padx=24, pady=16)
        content_card.grid_columnconfigure(0, weight=1)

        desc_label = ctk.CTkLabel(
            content_card,
            text=(
                "Vyntra is 100% open-source and maintained with love.\n"
                "If you find it valuable, consider sending a USDT contribution to help "
                "cover ongoing maintenance, API fixes, and new features!"
            ),
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_PRIMARY,
            justify="left",
            wraplength=450,
        )
        desc_label.grid(row=0, column=0, padx=20, pady=(18, 12), sticky="w")

        # Network Badges Container
        net_container = ctk.CTkFrame(content_card, fg_color="transparent")
        net_container.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="w")

        currency_badge = ctk.CTkLabel(
            net_container,
            text="USDT (Tether)",
            font=Theme.FONT_BADGE,
            text_color="#10B981",
            fg_color=Theme.SUCCESS_BG,
            corner_radius=6,
            padx=10,
            pady=3,
        )
        currency_badge.pack(side="left", padx=(0, 8))

        for net in SUPPORTED_NETWORKS:
            badge = ctk.CTkLabel(
                net_container,
                text=net,
                font=Theme.FONT_BADGE,
                text_color=Theme.TEXT_SECONDARY,
                fg_color=Theme.BG_MUTED,
                corner_radius=6,
                padx=8,
                pady=3,
            )
            badge.pack(side="left", padx=3)

        # Wallet Address Container
        addr_frame = ctk.CTkFrame(
            content_card,
            fg_color="#070B12",
            corner_radius=8,
            border_width=1,
            border_color=Theme.BORDER_SUBTLE,
        )
        addr_frame.grid(row=2, column=0, padx=20, pady=(0, 14), sticky="ew")
        addr_frame.grid_columnconfigure(0, weight=1)

        addr_title = ctk.CTkLabel(
            addr_frame,
            text="OFFICIAL USDT WALLET ADDRESS (EVM):",
            font=Theme.FONT_BADGE,
            text_color=Theme.TEXT_MUTED,
        )
        addr_title.grid(row=0, column=0, padx=14, pady=(10, 2), sticky="w")

        self.address_label = ctk.CTkLabel(
            addr_frame,
            text=USDT_WALLET_ADDRESS,
            font=("Consolas", 12, "bold"),
            text_color="#38BDF8",
            justify="left",
        )
        self.address_label.grid(row=1, column=0, padx=14, pady=(0, 12), sticky="w")

        # Copy Address Action Button
        self.copy_btn = ctk.CTkButton(
            content_card,
            text="📋  Copy Wallet Address",
            font=(Theme.FONT_FAMILY, 13, "bold"),
            height=38,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._copy_wallet_address,
        )
        self.copy_btn.grid(row=3, column=0, padx=20, pady=(0, 16), sticky="ew")

        # 3. Bottom Controls (Don't show again + Close)
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 18))
        bottom_frame.grid_columnconfigure(0, weight=1)

        self._dont_show_var = ctk.BooleanVar(master=self, value=config_manager.config.donation_prompt_dismissed)
        self.dont_show_checkbox = ctk.CTkCheckBox(
            bottom_frame,
            text="Don't show this again automatically",
            font=Theme.FONT_CAPTION,
            text_color=Theme.TEXT_MUTED,
            variable=self._dont_show_var,
            command=self._on_toggle_dont_show,
            checkbox_width=18,
            checkbox_height=18,
            corner_radius=4,
        )
        self.dont_show_checkbox.pack(side="left")

        self.close_btn = ctk.CTkButton(
            bottom_frame,
            text="Close",
            font=Theme.FONT_BODY,
            width=88,
            height=32,
            corner_radius=Theme.RADIUS_BUTTON,
            fg_color=Theme.BG_MUTED,
            hover_color=Theme.BG_CARD_HOVER,
            text_color=Theme.TEXT_SECONDARY,
            command=self.destroy,
        )
        self.close_btn.pack(side="right")

    def _copy_wallet_address(self):
        """Copies the USDT wallet address to the system clipboard with visual feedback."""
        try:
            self.clipboard_clear()
            self.clipboard_append(USDT_WALLET_ADDRESS)
            self.update_idletasks()
            logger.info("USDT donation wallet address copied to clipboard.")
        except Exception as err:
            logger.warning("Failed to copy wallet address to clipboard: %s", err)

        # Update button to show feedback
        self.copy_btn.configure(
            text="✓  Copied to Clipboard!",
            fg_color=Theme.SUCCESS,
            hover_color="#059669",
        )

        def reset_btn():
            if self.winfo_exists():
                self.copy_btn.configure(
                    text="📋  Copy Wallet Address",
                    fg_color=Theme.PRIMARY,
                    hover_color=Theme.PRIMARY_HOVER,
                )

        aid = self.after(2500, reset_btn)
        self._tracked_after_ids.add(aid)

    def _on_toggle_dont_show(self):
        """Persists the user preference to skip automatic donation pop-ups."""
        is_dismissed = bool(self._dont_show_var.get())
        config_manager.update(donation_prompt_dismissed=is_dismissed)
        logger.debug("Updated donation_prompt_dismissed = %s", is_dismissed)

    def destroy(self):
        """Cancels scheduled timers and safely destroys the dialog."""
        try:
            for aid in list(self._tracked_after_ids):
                try:
                    self.after_cancel(aid)
                except Exception:
                    pass
            self._tracked_after_ids.clear()
        except Exception:
            pass

        try:
            for aid in self.tk.splitlist(self.tk.eval("after info")):
                try:
                    self.tk.eval(f"after cancel {aid}")
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if hasattr(self, "_dont_show_var"):
                del self._dont_show_var
        except Exception:
            pass

        try:
            super().destroy()
        except Exception:
            pass
