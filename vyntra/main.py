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
    finally:
        try:
            from vyntra.services.stream_service import stream_service
            stream_service.stop_playback()
        except Exception:
            pass
        try:
            from vyntra.services.search_service import search_service
            search_service.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        try:
            from vyntra.services.download_service import download_service
            download_service.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        try:
            from vyntra.services.image_service import image_service
            image_service.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        try:
            import logging
            logging.shutdown()
        except Exception:
            pass
        # os._exit(0) terminates cleanly at the OS level, preventing PyInstaller
        # and C-extension DLL unload access violations on Windows application exit
        import os
        os._exit(0)


if __name__ == "__main__":
    main()
