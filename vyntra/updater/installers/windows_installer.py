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
    background process, and exits the current instance immediately to release
    file locks on the running executable.
    """

    def install_and_restart(self, staged_file: Path, target_path: Path) -> None:
        """
        Executes in-place update replacement via detached Windows script.
        Updates the exact executable the user launched and removes all temporary files.
        """
        if not staged_file.exists():
            raise FileNotFoundError(f"Staged update file not found: {staged_file}")

        pid = os.getpid()
        updates_dir = get_updates_dir()
        updater_script = updates_dir / "vyntra_updater.bat"
        updater_log = updates_dir / "vyntra_updater.log"

        logger.info("[Updater] Preparing Windows updater script: %s", updater_script)
        logger.info("[Updater] Target executable: %s | New payload: %s", target_path, staged_file)

        # Batch script template:
        # 1. Waits for PID to terminate (with 6s failsafe taskkill)
        # 2. Retries copying new executable directly over the target executable in-place
        # 3. Cleans up staging payload and backup file so no extra exe remains
        # 4. Launches the updated target executable in its directory
        script_content = f"""@echo off
setlocal enabledelayedexpansion
title Vyntra Updater

set "PID={pid}"
set "TARGET={target_path}"
set "NEW_EXE={staged_file}"
set "BACKUP={target_path}.bak"
set "LOG={updater_log}"

echo [%DATE% %TIME%] [Vyntra Updater] Started update replacement. > "!LOG!"
echo [%DATE% %TIME%] [Vyntra Updater] PID=!PID!, TARGET=!TARGET!, NEW_EXE=!NEW_EXE! >> "!LOG!"

echo [Vyntra Updater] Waiting for running process !PID! to terminate...
set /a WAIT_COUNT=0
:wait_process
tasklist /fi "PID eq !PID!" 2>NUL | find /I "!PID!" >NUL
if not errorlevel 1 (
    set /a WAIT_COUNT+=1
    if !WAIT_COUNT! gtr 6 (
        echo [%DATE% %TIME%] [Vyntra Updater] Terminating unresponsive process !PID!... >> "!LOG!"
        taskkill /f /pid !PID! >NUL 2>&1
    )
    timeout /t 1 /nobreak >NUL
    goto wait_process
)

echo [%DATE% %TIME%] [Vyntra Updater] Process !PID! terminated. Waiting for handle release... >> "!LOG!"
timeout /t 1 /nobreak >NUL

echo [Vyntra Updater] Updating executable in-place...
set /a ATTEMPTS=0
:replace_loop
set /a ATTEMPTS+=1

if exist "!BACKUP!" del /f /q "!BACKUP!" >NUL 2>&1
copy /y "!TARGET!" "!BACKUP!" >NUL 2>&1

copy /y "!NEW_EXE!" "!TARGET!" >NUL 2>&1
if not errorlevel 1 goto replace_success

move /y "!NEW_EXE!" "!TARGET!" >NUL 2>&1
if not errorlevel 1 goto replace_success

echo [%DATE% %TIME%] [Vyntra Updater] Replace attempt !ATTEMPTS! failed. Retrying... >> "!LOG!"
if !ATTEMPTS! leq 10 (
    timeout /t 1 /nobreak >NUL
    goto replace_loop
)

goto rollback

:replace_success
echo [%DATE% %TIME%] [Vyntra Updater] Successfully updated !TARGET! in-place. >> "!LOG!"

:: Remove temporary files so only the single updated executable remains
if exist "!NEW_EXE!" del /f /q "!NEW_EXE!" >NUL 2>&1
if exist "!BACKUP!" del /f /q "!BACKUP!" >NUL 2>&1

echo [Vyntra Updater] Starting updated Vyntra...
for %%I in ("!TARGET!") do set "TARGET_DIR=%%~dpI"
start "" /d "!TARGET_DIR!" "!TARGET!"
echo [%DATE% %TIME%] [Vyntra Updater] Launched updated Vyntra. Exiting updater. >> "!LOG!"
exit 0

:rollback
echo [%DATE% %TIME%] [Vyntra Updater ERROR] Replacement failed after 10 attempts. Rolling back... >> "!LOG!"
if exist "!BACKUP!" (
    copy /y "!BACKUP!" "!TARGET!" >NUL 2>&1
    del /f /q "!BACKUP!" >NUL 2>&1
    for %%I in ("!TARGET!") do set "TARGET_DIR=%%~dpI"
    start "" /d "!TARGET_DIR!" "!TARGET!"
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
        import logging
        logging.shutdown()
        import time
        time.sleep(0.5)

        # os._exit terminates the entire process immediately, releasing locks on the executable
        # even when called from a secondary worker thread
        os._exit(0)
