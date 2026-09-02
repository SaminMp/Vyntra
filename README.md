# 🎵 Vyntra

A modern, high-performance desktop application for searching YouTube and downloading audio (**MP3**) or video (**MP4**) with real-time speed, ETA, and progress indicators. Built with **Python** and **CustomTkinter**.

---

## ✨ Features

- 🔍 **Instant YouTube Search**: Search directly by song/video title or paste a direct YouTube video URL.
- 🎨 **Modern Dark UI**: Aesthetic dark-mode interface built with CustomTkinter, custom scrollbars, and high-DPI scaling.
- 🖼️ **Thumbnail Previews**: Asynchronously fetched video thumbnails with duration and view count overlays.
- 🎧 **MP3 & MP4 Downloads**: Choose between crystal-clear audio (up to 320 kbps MP3) or high-definition video (MP4).
- ⚡ **Non-Blocking Architecture**: Fully multi-threaded; UI never freezes or stutters during searches, downloads, or media conversions.
- 📊 **Real-time Progress & Metrics**: Live percentage bar, download speed (MB/s), estimated time remaining (ETA), and conversion statuses.
- 🌐 **Full Unicode & Persian Support**: Handles Persian, Arabic, CJK, and international characters seamlessly with path-safe filename sanitization.
- ⚙️ **Customizable Preferences**: Configure default destination directory, default format, and audio quality presets.
- 🛠️ **Smart FFmpeg Integration**: Auto-detects FFmpeg with graceful fallbacks and clear setup guidance.

---

## 🚀 Quick Start

### 1. Prerequisites

- **Python 3.10+** (Tested on Python 3.10 - 3.13)
- *(Optional but Recommended)* **FFmpeg** for high-bitrate MP3 conversion and 1080p+ video muxing:
  - **macOS**: `brew install ffmpeg`
  - **Windows**: `winget install Gyan.FFmpeg`
  - **Linux**: `sudo apt install ffmpeg`

### 2. Installation

Clone the repository and set up a virtual environment:

```bash
# Navigate to project directory
cd Vyntra

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS / Linux:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Launch Vyntra

```bash
python run.py
```

---

## 📁 Project Architecture

```
Vyntra/
├── requirements.txt               # Dependencies (customtkinter, yt-dlp, pillow, requests)
├── README.md                      # Project documentation
├── run.py                         # Root launcher script
├── tests/                         # Unit & integration test suites
│   ├── test_step1.py
│   ├── test_step2.py
│   └── test_step3.py
└── vyntra/
    ├── __init__.py                # Package version & metadata
    ├── main.py                    # Application bootstrap
    ├── config.py                  # Persistent JSON configuration manager (~/.vyntra/config.json)
    ├── models.py                  # Strongly-typed data models (SearchResult, DownloadTask, etc.)
    ├── services/
    │   ├── search_service.py      # YouTube search & direct URL metadata parser (yt-dlp)
    │   ├── download_service.py    # Media download engine with live progress, speed & cancellation
    │   ├── ffmpeg_service.py      # FFmpeg detection, path resolution & diagnostics
    │   └── image_service.py       # Asynchronous thumbnail fetcher and LRU caching
    ├── ui/
    │   ├── app.py                 # Main CustomTkinter window & layout orchestrator
    │   ├── theme.py               # Color palette, dark theme tokens, typography
    │   ├── components/
    │   │   ├── search_bar.py      # Search input, clear button & action triggers
    │   │   ├── result_card.py     # Interactive video card with thumbnail, title & meta
    │   │   ├── results_list.py    # Scrollable results container with empty/loading states
    │   │   ├── download_panel.py  # Format picker (MP3/MP4), folder selector & progress bar
    │   │   └── status_banner.py   # Toast / status alerts & FFmpeg diagnostics
    │   └── views/
    │       └── settings_modal.py  # Preferences dialog
    └── utils/
        ├── filename.py            # Unicode/Persian-safe filename sanitizer
        ├── formatters.py          # Formatters for duration, file sizes, speed & view counts
        └── logger.py              # Structured, thread-safe logger
```

---

## 🧪 Running Tests

To run the automated test suite across all modules:

```bash
.venv/bin/python -m unittest discover tests
```

---

## 📄 License

This project is licensed under the MIT License.
