"""
Backward-compatibility alias module for StatusBanner.
Points to FooterTerminal to provide persistent footer-based notifications and logging.
"""

from vyntra.ui.components.footer_terminal import FooterTerminal

# Direct backward compatibility alias
StatusBanner = FooterTerminal

__all__ = ["StatusBanner", "FooterTerminal"]

