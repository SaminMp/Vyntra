"""
Windows detached update installer.
Safely replaces the locked running Vyntra executable after process exit,
provides automatic rollback upon failure, and launches the updated version.
"""

import os
from pathlib import Path
import subprocess
import sys

from vyntra.updater.constants import get_updates_dir
from vyntra.updater.installers.base import BaseInstaller
from vyntra.utils.logger import logger


class WindowsInstaller(BaseInstaller):
    """
    Windows-specific update installer.
    Generates a standalone updater batch script, executes it in a detached
    background process, and exits the current instance.
    """

    def install_and_restart(self, staged_file: Path, target_path: Path) -> None:
        """
        Executes update replacement via detached Windows script.
        """
        if not staged_file.exists():
            raise FileNotFoundError(f"Staged update file not found: {staged_file}")

        pid = os.getpid()
        updates_dir = get_updates_dir()
        updater_script = updates_dir / "vyntra_updater.bat"

        logger.info("[Updater] Preparing Windows updater script: %s", updater_script)
        logger.info("[Updater] Target executable: %s | New payload: %s", target_path, staged_file)

        # Batch script template with loop wait, backup, replacement, and rollback
        script_content = f"""@echo off
setlocal enabledelayedexpansion
title Vyntra Updater

set "PID={pid}"
set "TARGET={target_path}"
set "NEW_EXE={staged_file}"
set "BACKUP={target_path}.bak"

echo [Vyntra Updater] Waiting for running process !PID! to terminate...
:wait_process
tasklist /fi "PID eq !PID!" 2>NUL | find /I "!PID!" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak >NUL
    goto wait_process
)

:: Brief pause to ensure all OS file locks and handles are released
timeout /t 1 /nobreak >NUL

echo [Vyntra Updater] Creating backup of existing executable...
if exist "!BACKUP!" del /f /q "!BACKUP!" 2>NUL
move /y "!TARGET!" "!BACKUP!" >NUL 2>&1
if errorlevel 1 (
    echo [Vyntra Updater ERROR] Could not backup existing executable.
    goto rollback
)

echo [Vyntra Updater] Installing updated executable...
move /y "!NEW_EXE!" "!TARGET!" >NUL 2>&1
if errorlevel 1 (
    echo [Vyntra Updater ERROR] Could not replace executable with new version.
    goto rollback
)

echo [Vyntra Updater] Starting updated Vyntra...
start "" "!TARGET!"
if errorlevel 1 goto rollback

:: Wait brief moment, then clean backup
timeout /t 3 /nobreak >NUL
if exist "!BACKUP!" del /f /q "!BACKUP!" 2>NUL
exit 0

:rollback
echo [Vyntra Updater] Performing rollback to previous version...
if exist "!BACKUP!" (
    move /y "!BACKUP!" "!TARGET!" >NUL 2>&1
    start "" "!TARGET!"
)
exit 1
"""

        with open(updater_script, "w", encoding="utf-8") as f:
            f.write(script_content)

        logger.info("[Updater] Launching detached updater helper process...")

        # Detached process flags for Windows (DETACHED_PROCESS = 0x00000008, CREATE_NO_WINDOW = 0x08000000)
        creation_flags = 0x00000008 | 0x08000000

        try:
            subprocess.Popen(
                ["cmd.exe", "/c", str(updater_script)],
                close_fds=True,
                creationflags=creation_flags,
            )
        except Exception as e:
            logger.error("[Updater] Failed to spawn updater script: %s", e)
            raise RuntimeError(f"Could not spawn update process: {e}") from e

        logger.info("[Updater] Updater spawned successfully. Terminating Vyntra instance for replacement.")
        # Exit running process gracefully
        sys.exit(0)
