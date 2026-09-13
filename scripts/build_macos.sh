#!/usr/bin/env bash
# ==============================================================================
# Vyntra macOS Standalone .app and .dmg Packaging Script
# Compiles Vyntra into a native macOS Application Bundle (Vyntra.app) and DMG.
# Compatible with Apple Silicon (M1/M2/M3/M4) and Intel x86_64 Macs.
# ==============================================================================

set -e

# Change to project root directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
ROOT_DIR="$( cd "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd )"
cd "$ROOT_DIR"

echo "=========================================================="
echo "    Building Vyntra Standalone for macOS (Apple Devices)  "
echo "=========================================================="

if [[ "$OSTYPE" != "darwin"* ]]; then
  echo "❌ This build script is designed to run on macOS."
  echo "   To build for macOS from Windows, use GitHub Actions or run on a Mac."
  exit 1
fi

# 1. Check Python interpreter
PYTHON_CMD="python3"
if [ -d ".venv" ]; then
  PYTHON_CMD=".venv/bin/python"
fi

echo "[1/5] Using Python: $($PYTHON_CMD --version)"

# 2. Ensure dependencies and pyinstaller are installed
echo "[2/5] Checking dependencies..."
$PYTHON_CMD -m pip install -r requirements.txt
$PYTHON_CMD -m pip install pyinstaller

# 3. Ensure icons exist
echo "[3/5] Verifying macOS ICNS and PNG assets..."
$PYTHON_CMD scripts/generate_icons.py

# 4. Clean previous build artifacts
echo "[4/5] Running PyInstaller with Vyntra.spec..."
rm -rf build/Vyntra dist/Vyntra.app dist/Vyntra dist/Vyntra-*.dmg

$PYTHON_CMD -m PyInstaller --clean --noconfirm Vyntra.spec

if [ ! -d "dist/Vyntra.app" ]; then
  echo "❌ Build failed: dist/Vyntra.app was not created."
  exit 1
fi

echo "✓ Vyntra.app created successfully."

# 5. Create drag-and-drop .dmg disk image using native hdiutil
echo "[5/5] Creating macOS drag-and-drop DMG installer..."
DMG_STAGING="dist/dmg_staging"
rm -rf "$DMG_STAGING"
mkdir -p "$DMG_STAGING"

cp -R "dist/Vyntra.app" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"

VERSION=$($PYTHON_CMD -c "import vyntra; print(vyntra.__version__)")
DMG_OUTPUT="dist/Vyntra-${VERSION}.dmg"
hdiutil create \
  -volname "Vyntra" \
  -srcfolder "$DMG_STAGING" \
  -ov \
  -format UDZO \
  "$DMG_OUTPUT"

rm -rf "$DMG_STAGING"

echo ""
echo "=========================================================="
echo "              MACOS BUILD SUCCESSFUL!                     "
echo "=========================================================="
echo "  Application Bundle: dist/Vyntra.app"
echo "  Disk Image (DMG):   $DMG_OUTPUT"
echo "  File Size:          $(du -h "$DMG_OUTPUT" | cut -f1)"
echo "=========================================================="
