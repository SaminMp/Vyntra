"""
Application entry point for Vyntra.
"""

import sys
import customtkinter as ctk

from vyntra import __app_name__, __version__
from vyntra.config import config_manager
from vyntra.ui.app import VyntraApp
from vyntra.utils.logger import logger


def main():
    """Bootstraps and launches the Vyntra desktop application."""
    logger.info("[Vyntra] Vyntra version %s", __version__)
    logger.info("Initializing Vyntra Application...")

    # Configure CustomTkinter Appearance
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    try:
        app = VyntraApp()
        logger.info("Starting Vyntra main UI loop.")
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Application closed by user interrupt.")
    except Exception as err:
        logger.critical("Fatal error running Vyntra: %s", err, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
