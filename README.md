# Vyntra

Vyntra is a modern desktop multimedia application engineered for discovering, previewing, and downloading media across multiple content platforms. Built with Python and CustomTkinter, Vyntra delivers a responsive dark-themed interface, non-blocking asynchronous background processing, and direct integration with YouTube, Spotify, TikTok, and Instagram.

---

## Overview

Vyntra streamlines the process of accessing and saving audio and video content from popular platforms into organized local files. The application coordinates metadata search, streaming preview playback, and media conversion through a multi-threaded architecture that ensures the graphical interface remains fluid and responsive during intensive download operations.

---

## Core Features

- Multi-Platform Support: Direct integration with YouTube, Spotify, TikTok, and Instagram from a unified interface.
- Format and Quality Selection: Download audio as high-bitrate MP3 (up to 320 kbps) or video as high-definition MP4 (up to 1080p and 4K).
- Integrated Preview Player: Listen to 30-second audio previews for Spotify tracks directly within the application prior to downloading.
- Non-Blocking Asynchronous Engine: Background worker threads manage search queries, image fetching, and media processing without UI stutter.
- Real-Time Progress Telemetry: Live progress bar, transfer speed indicators (MB/s), estimated time remaining (ETA), and an optional collapsible diagnostics terminal.
- International Character Support: Comprehensive Unicode filename sanitization ensuring safe file generation for Persian, Arabic, CJK, and international scripts.
- Automated Application Updates: Integrated background updater connecting directly to official GitHub Releases with cryptographic SHA-256 verification.
- Flexible Storage Configuration: User-defined default download directories with remember-last-folder capabilities and quick folder navigation.

---

## Supported Platforms

### YouTube
- Query search by keyword, song title, or artist name.
- Direct URL parsing for standard videos, playlists, and Shorts.
- High-quality audio extraction (MP3 presets: 128 kbps, 192 kbps, 256 kbps, 320 kbps).
- High-definition video downloads (MP4 with automated audio-video muxing).

### Spotify
- Track and album discovery with real-time metadata display.
- Audio preview playback with integrated controls.
- Single-click MP3 download generation directly from track cards or the dedicated control panel.

### TikTok
- Watermark-free video extraction from standard links and short URLs.
- Direct audio track extraction in MP3 format.

### Instagram
- Video and audio extraction for Reels and standard video posts.
- Direct link processing with automatic quality resolution.

---

## Getting Started

### Option A: Prebuilt Executables (Recommended)

Precompiled standalone packages are available for Windows and macOS under the Releases section of the official GitHub repository:

- Windows: Download `Vyntra-Windows-x64.exe` or `Vyntra-Windows-x64.zip`. Run the executable directly without requiring a Python installation.
- macOS: Download `Vyntra-macOS.dmg`. Open the disk image and drag Vyntra to your Applications folder.

### Option B: Running from Source

#### Prerequisites
- Python 3.10, 3.11, 3.12, 3.13, or 3.14.
- FFmpeg (recommended for high-bitrate audio conversion and video muxing):
  - Windows: `winget install Gyan.FFmpeg` or download from official FFmpeg builds.
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`

#### Installation Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/SaminMp/Vyntra.git
   cd Vyntra
   ```

2. Create and activate a virtual environment:
   - On Windows:
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\activate
     ```
   - On macOS and Linux:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Launch the application:
   ```bash
   python run.py
   ```

---

## User Guide

### 1. Platform Selection
Use the platform selector located at the top of the interface to switch between YouTube, Spotify, TikTok, and Instagram. Each view provides dedicated controls optimized for that media type.

### 2. Searching and Input
- In YouTube or Spotify mode, type your search query into the search bar and press Enter or click the Search button. Alternatively, paste a direct link.
- In TikTok or Instagram mode, paste the target video or Reel URL into the address field and click Resolve.

### 3. Previewing Content
- For Spotify results, click the Preview button on any track card to start immediate audio playback.
- Use the built-in mini-player to play, pause, or adjust preview volume.

### 4. Downloading Media
- Select your preferred destination folder using the Browse button (defaults to your operating system's Downloads directory).
- Choose your output format (MP3 for audio, MP4 for video) and target quality bitrate.
- Click Download directly on the media card or from the bottom action panel.
- Monitor live download metrics, including progress percentage, download speed, and elapsed time.

### 5. Managing Preferences
Click the Settings button in the header to:
- Configure default output directories.
- Set default audio bitrate preferences (e.g., 320 kbps).
- Set default video resolution preferences (e.g., 1080p).
- Check for application updates manually.
- Manage update and notification preferences.

---

## Technical Specifications

- GUI Framework: CustomTkinter (Tkinter with customized high-DPI modern controls)
- Media Engine: yt-dlp with optimized extractor pipelines
- Audio and Video Processing: FFmpeg (system binary or packaged environment)
- Image Processing: Pillow (PIL Fork) with memory LRU caching
- Network Protocols: Requests with streaming HTTP chunking and SHA-256 checksum validation
- Configuration Storage: Local JSON storage located in `~/.vyntra/config.json`

---

## Automated Updates

Vyntra includes a built-in update subsystem that checks official GitHub Releases for new versions:
- Background Checks: Non-blocking checks run silently on launch without delaying application startup.
- Cryptographic Integrity: Downloaded assets are validated against SHA-256 manifests (`SHA256SUMS.txt`) prior to installation.
- Safe Staging: Update payloads are downloaded to an isolated staging directory before platform-specific installation handoff.

---

## License

This project is licensed under the MIT License. See the LICENSE file for details.
