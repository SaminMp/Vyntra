#!/usr/bin/env bash
# ==============================================================================
# Vyntra 1-Click Desktop Launcher for macOS (Apple Silicon M-Series & Intel Macs)
# Allows Mac users to launch Vyntra directly by double-clicking in macOS Finder.
# ==============================================================================

# Change working directory to the project root where this script lives
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
ROOT_DIR="$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )"
cd "$ROOT_DIR" || exit 1

echo "=========================================================="
echo "          Starting Vyntra Desktop for macOS...            "
echo "=========================================================="

# 1. Check for Python 3
if ! command -v python3 &>/dev/null; then
  echo "⚠️ Python 3 is required to run Vyntra on macOS."
  osascript -e 'display alert "Vyntra Desktop" message "Python 3 is required to run Vyntra. Please install Python 3 or Homebrew (https://brew.sh) and try again." as critical'
  exit 1
fi

# 2. Check or initialize Python virtual environment
VENV_DIR="$ROOT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "📦 Initializing dedicated Python virtual environment for Vyntra..."
  python3 -m venv "$VENV_DIR"
  if [ $? -ne 0 ]; then
    echo "❌ Failed to create virtual environment."
    exit 1
  fi
  echo "📥 Installing required dependencies..."
  "$VENV_DIR/bin/pip" install --upgrade pip
  "$VENV_DIR/bin/pip" install -r "$ROOT_DIR/requirements.txt"
fi

# 3. Check FFmpeg on macOS
if ! command -v ffmpeg &>/dev/null && [ ! -f "/opt/homebrew/bin/ffmpeg" ] && [ ! -f "/usr/local/bin/ffmpeg" ]; then
  echo "💡 Tip: Install FFmpeg via Homebrew for high-res video muxing and MP3 conversion:"
  echo "   brew install ffmpeg"
fi

# 4. Launch Vyntra in background and release terminal
echo "🚀 Launching Vyntra..."
"$VENV_DIR/bin/python" "$ROOT_DIR/run.py" "$@" &

# Wait a brief moment to confirm process spawn
PID=$!
sleep 1
if kill -0 $PID 2>/dev/null; then
  echo "✓ Vyntra launched successfully (PID: $PID)."
  # Close terminal if opened via double-click in Finder
  osascript -e 'tell application "Terminal" to close (every window whose name contains "Vyntra.command")' &>/dev/null &
  exit 0
else
  echo "❌ Error starting Vyntra. Please check the logs above."
  read -p "Press [Enter] to exit..."
  exit 1
fi
