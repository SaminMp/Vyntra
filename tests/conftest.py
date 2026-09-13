"""
Pytest configuration, lifecycle isolation, and teardown harness for Vyntra.
"""

import os
from pathlib import Path
import sys
import pytest

# Ensure sys.path includes workspace root
WORKSPACE_ROOT = Path(__file__).parent.parent.resolve()
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# Ensure TCL_LIBRARY and TK_LIBRARY are set for Windows virtual environments
base_tcl = Path(sys.base_prefix) / "tcl"
if base_tcl.exists():
    for p in base_tcl.glob("tcl8.*"):
        if (p / "init.tcl").exists():
            os.environ.setdefault("TCL_LIBRARY", str(p))
            break
    for p in base_tcl.glob("tk8.*"):
        if (p / "tk.tcl").exists():
            os.environ.setdefault("TK_LIBRARY", str(p))
            break


def pytest_sessionstart(session):
    """Initializes test environment: deactivates background polling and wraps destroy in CustomTkinter."""
    try:
        import customtkinter as ctk
        # Deactivate automatic DPI awareness to prevent the 100ms check_dpi_scaling loop
        ctk.deactivate_automatic_dpi_awareness()
        ctk.set_appearance_mode("Dark")
        from customtkinter.windows.widgets.appearance_mode import AppearanceModeTracker
        AppearanceModeTracker.update_loop_running = False
        AppearanceModeTracker.app_list.clear()

        # Neutralize CTkTextbox continuous scrollbar checking loop during test session
        try:
            from customtkinter.windows.widgets.ctk_textbox import CTkTextbox
            orig_check = CTkTextbox._check_if_scrollbars_needed
            def safe_check_scrollbars(self, event=None, continue_loop=False):
                return orig_check(self, event, continue_loop=False)
            CTkTextbox._check_if_scrollbars_needed = safe_check_scrollbars
        except Exception:
            pass

        # Wrap CTk and CTkToplevel destroy to cancel scheduled timers and clean trackers
        for cls in (ctk.CTk, ctk.CTkToplevel):
            orig_destroy = cls.destroy
            def make_safe_destroy(orig):
                def safe_destroy(self):
                    try:
                        if self.winfo_exists():
                            for aid in self.tk.splitlist(self.tk.eval("after info")):
                                try:
                                    self.tk.eval(f"after cancel {aid}")
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    try:
                        from customtkinter.windows.widgets.appearance_mode import AppearanceModeTracker
                        if self in AppearanceModeTracker.app_list:
                            AppearanceModeTracker.app_list.remove(self)
                    except Exception:
                        pass
                    try:
                        from customtkinter.windows.widgets.scaling import ScalingTracker
                        ScalingTracker.remove_window(None, self)
                        if self in ScalingTracker.window_widgets_dict:
                            del ScalingTracker.window_widgets_dict[self]
                        if self in ScalingTracker.window_dpi_scaling_dict:
                            del ScalingTracker.window_dpi_scaling_dict[self]
                    except Exception:
                        pass
                    try:
                        orig(self)
                    except Exception:
                        pass
                return safe_destroy
            cls.destroy = make_safe_destroy(orig_destroy)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clean_test_lifecycle():
    """Autouse fixture providing per-test lifecycle isolation and Tkinter timer purging."""
    yield

    # Clean up CustomTkinter background trackers
    try:
        from customtkinter.windows.widgets.appearance_mode import AppearanceModeTracker
        AppearanceModeTracker.update_loop_running = False
        AppearanceModeTracker.app_list.clear()
    except Exception:
        pass

    try:
        from customtkinter.windows.widgets.scaling import ScalingTracker
        ScalingTracker.update_loop_running = False
        ScalingTracker.window_widgets_dict.clear()
        ScalingTracker.window_dpi_scaling_dict.clear()
    except Exception:
        pass

    # Cancel any remaining timers on the default root if still present
    try:
        import tkinter
        if getattr(tkinter, "_default_root", None) is not None:
            root = tkinter._default_root
            if root and root.winfo_exists():
                try:
                    pending = root.tk.splitlist(root.tk.eval("after info"))
                    for aid in pending:
                        try:
                            root.tk.eval(f"after cancel {aid}")
                        except Exception:
                            pass
                    root.update_idletasks()
                except Exception:
                    pass
    except Exception:
        pass


def pytest_sessionfinish(session, exitstatus):
    """
    Session finish hook:
    1. Cleanly shuts down all singleton executors (ImageService, DownloadService, SearchService, PlatformRegistry).
    2. Dumps thread diagnostics and verifies no non-daemon worker threads remain alive.
    """
    # 1. Shutdown all service ThreadPoolExecutors
    try:
        from vyntra.services.image_service import image_service
        image_service.shutdown(wait=True)
    except Exception:
        pass

    try:
        from vyntra.services.download_service import download_service
        download_service.shutdown(wait=True)
    except Exception:
        pass

    try:
        from vyntra.services.search_service import search_service
        search_service.shutdown(wait=True)
    except Exception:
        pass

    try:
        from vyntra.platforms.registry import platform_registry
        platform_registry.shutdown_all(wait=True)
    except Exception:
        pass

    # 2. Enumerate live threads
    import threading
    import traceback

    print("\n" + "=" * 50)
    print("=== Vyntra Test Shutdown Diagnostics ===")

    threads = threading.enumerate()
    print(f"Total live threads: {len(threads)}")
    frames = sys._current_frames()

    non_daemon_threads = []
    for t in threads:
        is_main = t is threading.main_thread()
        if not t.daemon and not is_main:
            non_daemon_threads.append(t)
        daemon_str = "MainThread" if is_main else ("daemon" if t.daemon else "NON-DAEMON (BLOCKS EXIT!)")
        print(f"- Thread: '{t.name}' (id: {t.ident}, {daemon_str})")
        if t.ident in frames:
            frame = frames[t.ident]
            stack = traceback.format_stack(frame)
            print(f"  Current stack for '{t.name}':")
            for line in stack[-3:]:
                print(f"    {line.strip()}")

    if non_daemon_threads:
        print(f"\n[WARNING] Found {len(non_daemon_threads)} non-daemon worker thread(s) blocking Python exit!")
    else:
        print("\n[SUCCESS] No rogue non-daemon threads detected. Clean process shutdown guaranteed.")

    print("=" * 50 + "\n")
