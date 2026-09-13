"""
Packages Vyntra into a native macOS Application Bundle (dist/Vyntra.app)
and a portable release archive (dist/Vyntra-macOS-Portable.zip).
Can be run on Windows, Linux, or macOS to produce Apple-compatible deliverables.
"""

import os
from pathlib import Path
import shutil
import stat
import sys
import zipfile

def package_mac_app():
    root_dir = Path(__file__).resolve().parent.parent
    dist_dir = root_dir / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    app_bundle = dist_dir / "Vyntra.app"
    contents_dir = app_bundle / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"

    print(f"[Mac Packager] Building macOS Application Bundle at: {app_bundle}")

    # 1. Clean previous bundle
    if app_bundle.exists():
        shutil.rmtree(app_bundle)

    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    # Read version dynamically
    sys.path.insert(0, str(root_dir))
    import vyntra
    version = getattr(vyntra, "__version__", "1.2.0")

    # 2. Write Info.plist
    info_plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleDisplayName</key>
    <string>Vyntra</string>
    <key>CFBundleExecutable</key>
    <string>Vyntra</string>
    <key>CFBundleIconFile</key>
    <string>icon.icns</string>
    <key>CFBundleIdentifier</key>
    <string>com.saminmp.vyntra</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Vyntra</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>{version}</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleVersion</key>
    <string>{version}</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSRequiresAquaSystemAppearance</key>
    <false/>
    <key>LSApplicationCategoryType</key>
    <string>public.app-category.music</string>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © 2026 Vyntra. All rights reserved.</string>
</dict>
</plist>
"""
    with open(contents_dir / "Info.plist", "w", encoding="utf-8", newline="\n") as f:
        f.write(info_plist_content)

    # 3. Write PkgInfo
    with open(contents_dir / "PkgInfo", "wb") as f:
        f.write(b"APPL????")

    # 4. Write macOS Launcher Script (Contents/MacOS/Vyntra) with Unix LF
    launcher_script = """#!/bin/bash
# ==============================================================================
# Vyntra Native Launcher for macOS (Inside Vyntra.app)
# Compatible with Apple Silicon (M1/M2/M3/M4) and Intel Macs
# ==============================================================================

DIR="$(cd "$(dirname "$0")" && pwd)"
RESOURCES_DIR="$(cd "$DIR/../Resources" && pwd)"

# Find Python 3 on macOS (Homebrew, MacPorts, Pyenv, or System)
PYTHON_CANDIDATES=(
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
    "$(which python3 2>/dev/null)"
    "$(which python 2>/dev/null)"
)

PYTHON_EXE=""
for py in "${PYTHON_CANDIDATES[@]}"; do
    if [ -n "$py" ] && [ -x "$py" ]; then
        ver=$("$py" -c 'import sys; print(sys.version_info[0])' 2>/dev/null)
        if [ "$ver" = "3" ]; then
            PYTHON_EXE="$py"
            break
        fi
    fi
done

if [ -z "$PYTHON_EXE" ]; then
    osascript -e 'display alert "Python 3 Required" message "Vyntra requires Python 3 to run on macOS. Please install Python 3 or Homebrew (https://brew.sh) and try again." as critical'
    exit 1
fi

# Dedicated user virtual environment inside ~/Library/Application Support/Vyntra
APP_SUPPORT="$HOME/Library/Application Support/Vyntra"
VENV_DIR="$APP_SUPPORT/venv"
mkdir -p "$APP_SUPPORT"

# Check if venv exists and is functional
if [ ! -f "$VENV_DIR/bin/python" ]; then
    osascript -e 'display notification "Setting up Vyntra environment (first run only)..." with title "Vyntra"'
    "$PYTHON_EXE" -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$RESOURCES_DIR/requirements.txt"
fi

# Change working directory to Resources
cd "$RESOURCES_DIR"

# Launch Vyntra desktop application
exec "$VENV_DIR/bin/python" "$RESOURCES_DIR/run.py" "$@"
"""
    launcher_path = macos_dir / "Vyntra"
    with open(launcher_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(launcher_script)

    # 5. Copy Icons and metadata to Resources
    assets_dir = root_dir / "assets"
    if (assets_dir / "icon.icns").is_file():
        shutil.copy2(assets_dir / "icon.icns", resources_dir / "icon.icns")
    if (assets_dir / "icon.png").is_file():
        shutil.copy2(assets_dir / "icon.png", resources_dir / "icon.png")
    if (root_dir / "credentials.json").is_file():
        shutil.copy2(root_dir / "credentials.json", resources_dir / "credentials.json")
    if (root_dir / "requirements.txt").is_file():
        shutil.copy2(root_dir / "requirements.txt", resources_dir / "requirements.txt")
    if (root_dir / "run.py").is_file():
        shutil.copy2(root_dir / "run.py", resources_dir / "run.py")

    # 6. Copy vyntra source tree
    def ignore_patterns(path, names):
        return [n for n in names if n in ("__pycache__", ".pytest_cache") or n.endswith((".pyc", ".pyo"))]

    dest_vyntra = resources_dir / "vyntra"
    if dest_vyntra.exists():
        shutil.rmtree(dest_vyntra)
    shutil.copytree(root_dir / "vyntra", dest_vyntra, ignore=ignore_patterns)

    print(f"[OK] Vyntra.app assembled successfully at: {app_bundle}")

    # 7. Create Zip archive with Unix executable permission flags preserved
    zip_path = dist_dir / "Vyntra-macOS-Portable.zip"
    print(f"[Mac Packager] Creating portable ZIP with Unix permissions: {zip_path}")
    
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in app_bundle.rglob("*"):
            if file_path.is_file():
                arcname = str(file_path.relative_to(dist_dir)).replace("\\", "/")
                zinfo = zipfile.ZipInfo.from_file(file_path, arcname=arcname)
                
                # If executable script in MacOS folder or .sh, mark with 0o755
                if file_path.name == "Vyntra" or file_path.suffix in (".sh", ".command"):
                    zinfo.external_attr = (0o755 | 0o100000) << 16
                else:
                    zinfo.external_attr = (0o644 | 0o100000) << 16
                
                with open(file_path, "rb") as fp:
                    zf.writestr(zinfo, fp.read())

    print(f"[OK] Portable macOS release created: {zip_path} ({zip_path.stat().st_size / 1024:.1f} KB)")
    print("\n" + "=" * 60)
    print("  MACOS PACKAGING COMPLETE IN dist/")
    print(f"  1. Application Bundle: {app_bundle}")
    print(f"  2. Portable Zip:       {zip_path}")
    print("=" * 60)

if __name__ == "__main__":
    package_mac_app()
