"""
Logging utility for Vyntra with timestamped and structured output.
"""

import logging
import sys


def setup_logger(name: str = "Vyntra", level: int = logging.INFO) -> logging.Logger:
    """
    Configures and returns a logger instance for Vyntra.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(level)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False

    return logger


logger = setup_logger()
