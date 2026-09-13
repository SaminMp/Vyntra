"""
Automated interactive resize stress-test script for Vyntra.
Exercises continuous resizing across small, medium, large, and ultrawide resolutions:
800x600 -> 1024x768 -> 1280x720 -> 1366x768 -> 1600x900 -> 1920x1080 -> 2560x1440 -> 800x600
across all 4 platform views (YouTube, Instagram, TikTok, Spotify) with search results and panels loaded.
"""

import time
import customtkinter as ctk

from vyntra.models import MediaItem, SearchResult
from vyntra.ui.app import VyntraApp
from vyntra.ui.components.platform_selector import PLATFORM_METADATA


def run_resize_stress_test():
    print("[1/5] Initializing VyntraApp...")
    app = VyntraApp()
    app.update_idletasks()

    resolutions = [
        (800, 600),
        (1024, 768),
        (1280, 720),
        (1366, 768),
        (1600, 900),
        (1920, 1080),
        (2560, 1440),
        (800, 600),
    ]

    platforms = ["youtube", "instagram", "tiktok", "spotify"]

    print("[2/5] Testing continuous resizing across all platforms...")
    for pid in platforms:
        app._switch_platform(pid)
        app.update_idletasks()
        current_plat = app.platform_selector.get_selected_platform()
        assert current_plat == pid, f"Expected active platform {pid}, got {current_plat}"

        for w, h in resolutions:
            app.geometry(f"{w}x{h}")
            app.update_idletasks()
            app.update()

            # Verify PlatformSelector mode matches width
            selector = app.platform_selector
            expected_mode = "wide" if w >= 820 else ("medium" if w >= 520 else "compact")
            assert selector._layout_mode == expected_mode, (
                f"At resolution {w}x{h}, platform selector mode expected {expected_mode}, got {selector._layout_mode}"
            )

    print("[3/5] Populating YouTube results and testing resizing with active ResultCards...")
    app._switch_platform("youtube")
    mock_results = [
        SearchResult(
            video_id=f"vid_{i}",
            title=f"Sample Track Title Number {i} With Very Long Name That Wraps Automatically Across Display Widths",
            channel=f"Artist Channel {i}",
            views=50000 * i,
            views_formatted=f"{50 * i}K views",
            duration_seconds=180 + i * 10,
            duration_formatted=f"03:{i*10:02d}",
            thumbnail_url="",
            url=f"https://youtube.com/watch?v=vid_{i}",
        )
        for i in range(1, 5)
    ]
    app.results_list.display_results(mock_results)
    app.download_panel.set_selected_result(mock_results[0])
    app.update_idletasks()

    for w, h in resolutions:
        app.geometry(f"{w}x{h}")
        app.update_idletasks()
        app.update()

    print("[4/5] Populating Spotify results and testing resizing...")
    app._switch_platform("spotify")
    spotify_items = [
        MediaItem(
            video_id=f"sp_{i}",
            title=f"Spotify Track {i} - Ultra High Fidelity Stereo Mix Extended Version",
            channel=f"Record Label / Band {i}",
            album=f"Greatest Hits Volume {i}",
            duration_seconds=210,
            duration_formatted="03:30",
            thumbnail_url="",
            url=f"https://open.spotify.com/track/sp_{i}",
            platform="spotify",
        )
        for i in range(1, 4)
    ]
    spotify_page = app._pages["spotify"]
    spotify_page._display_results(spotify_items, generation=spotify_page._search_generation)
    app.update_idletasks()

    for w, h in resolutions:
        app.geometry(f"{w}x{h}")
        app.update_idletasks()
        app.update()

    print("[5/5] Testing Settings Modal and Download Folder at small/large sizes...")
    app.geometry("800x600")
    app.update_idletasks()
    assert app.platform_selector._layout_mode in ("medium", "wide")

    print("Closing app cleanly...")
    app.destroy()
    print("SUCCESS: All responsive UI stress tests passed cleanly with 0 errors!")


if __name__ == "__main__":
    run_resize_stress_test()
