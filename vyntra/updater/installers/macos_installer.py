"""
macOS detached update installer.
Safely replaces the installed Vyntra.app bundle from a downloaded DMG disk image,
preserves code signatures, clears quarantine flags, and restarts the updated application.
"""

import os
from pathlib import Path
import stat
import subprocess
import sys

from vyntra.updater.constants import get_updates_dir
from vyntra.updater.installers.base import BaseInstaller
from vyntra.utils.logger import logger


class MacOSInstaller(BaseInstaller):
    """
    macOS-specific update installer.
    Generates a detached bash script to mount the DMG, swap the .app bundle,
    clean quarantine attributes, unmount, and relaunch.
    """

    def install_and_restart(self, staged_file: Path, target_path: Path) -> None:
        """
        Executes update replacement via detached macOS bash script.
        """
        if not staged_file.exists():
            raise FileNotFoundError(f"Staged DMG file not found: {staged_file}")

        pid = os.getpid()
        updates_dir = get_updates_dir()
        updater_script = updates_dir / "vyntra_updater.sh"

        logger.info("[Updater] Preparing macOS updater script: %s", updater_script)
        logger.info("[Updater] Target bundle: %s | DMG: %s", target_path, staged_file)

        script_content = f"""#!/usr/bin/env bash
set -e

PID="{pid}"
TARGET="{target_path}"
DMG="{staged_file}"
BACKUP="${{TARGET}}.bak"

echo "[Vyntra Updater] Waiting for PID $PID to terminate..."
WAIT_COUNT=0
while kill -0 "$PID" 2>/dev/null; do
    WAIT_COUNT=$((WAIT_COUNT + 1))
    if [ "$WAIT_COUNT" -gt 6 ]; then
        kill -9 "$PID" 2>/dev/null || true
    fi
    sleep 1
done
sleep 1

echo "[Vyntra Updater] Attaching DMG image..."
MOUNT_DIR=$(hdiutil attach -nobrowse -readonly "$DMG" | grep "/Volumes/" | awk '{{print $NF}}')

if [ -z "$MOUNT_DIR" ] || [ ! -d "$MOUNT_DIR" ]; then
    echo "[Vyntra Updater ERROR] Could not mount DMG: $DMG"
    exit 1
fi

NEW_APP="$MOUNT_DIR/Vyntra.app"
if [ ! -d "$NEW_APP" ]; then
    echo "[Vyntra Updater ERROR] Vyntra.app not found inside DMG: $MOUNT_DIR"
    hdiutil detach "$MOUNT_DIR" 2>/dev/null || true
    exit 1
fi

echo "[Vyntra Updater] Creating backup of current application..."
rm -rf "$BACKUP"
if [ -d "$TARGET" ]; then
    mv "$TARGET" "$BACKUP"
fi

echo "[Vyntra Updater] Copying updated application bundle..."
if cp -R "$NEW_APP" "$TARGET"; then
    echo "[Vyntra Updater] Unmounting DMG..."
    hdiutil detach "$MOUNT_DIR" 2>/dev/null || true
    
    echo "[Vyntra Updater] Clearing quarantine attributes..."
    xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null || true
    
    echo "[Vyntra Updater] Launching updated Vyntra..."
    rm -rf "$BACKUP"
    open "$TARGET"
    exit 0
else
    echo "[Vyntra Updater ERROR] Copy failed. Rolling back..."
    rm -rf "$TARGET"
    if [ -d "$BACKUP" ]; then
        mv "$BACKUP" "$TARGET"
    fi
    hdiutil detach "$MOUNT_DIR" 2>/dev/null || true
    open "$TARGET"
    exit 1
fi
"""

        with open(updater_script, "w", encoding="utf-8") as f:
            f.write(script_content)

        # Ensure script is executable
        updater_script.chmod(updater_script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        logger.info("[Updater] Spawning detached macOS update runner...")
        try:
            subprocess.Popen(
                ["/bin/bash", str(updater_script)],
                close_fds=True,
                start_new_session=True,
            )
        except Exception as e:
            logger.error("[Updater] Failed to spawn macOS updater script: %s", e)
            raise RuntimeError(f"Could not spawn update process: {e}") from e

        logger.info("[Updater] Terminating Vyntra instance for replacement.")
        import logging
        logging.shutdown()
        import time
        time.sleep(0.5)

        # os._exit terminates the entire process immediately, releasing locks on the application bundle
        # even when called from a secondary worker thread
        os._exit(0)
