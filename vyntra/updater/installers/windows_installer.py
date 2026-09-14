"""
Windows detached update installer.
Safely replaces the locked running Vyntra executable after process exit,
provides automatic rollback upon failure, and launches the updated version.
"""

import os
import subprocess
import sys
from pathlib import Path

import zipfile
import tempfile
import shutil

from vyntra.updater.constants import get_updates_dir
from vyntra.updater.installers.base import BaseInstaller
from vyntra.updater.platform_detector import is_frozen
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

        # Safe diagnostic reporting
        is_frozen_app = is_frozen()
        running_exe = str(Path(sys.executable).resolve())
        temp_mei = getattr(sys, "_MEIPASS", "None")
        target_str = str(target_path)
        restart_str = str(target_path)

        logger.info("[Updater] === Windows Update Diagnostics ===")
        logger.info("[Updater] Frozen application: %s", "YES" if is_frozen_app else "NO")
        logger.info("[Updater] Running executable: %s", running_exe)
        logger.info("[Updater] PyInstaller temp directory: %s", temp_mei)
        logger.info("[Updater] Update target: %s", target_str)
        logger.info("[Updater] Restart target: %s", restart_str)

        if staged_file.suffix.lower() == ".zip":
            logger.info("[Updater] Staged file is a zip archive, extracting...")
            extract_dir = Path(tempfile.mkdtemp(prefix="vyntra_update_"))
            with zipfile.ZipFile(staged_file, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            exe_files = list(extract_dir.rglob("*.exe"))
            if not exe_files:
                raise FileNotFoundError(f"No executable found in zip archive: {staged_file}")

            extracted_exe = exe_files[0]
            for exe in exe_files:
                if exe.name.lower() == target_path.name.lower():
                    extracted_exe = exe
                    break
            logger.info("[Updater] Resolved executable from zip: %s", extracted_exe)

            updates_dir = get_updates_dir()
            updates_dir.mkdir(parents=True, exist_ok=True)
            safe_staged_file = updates_dir / extracted_exe.name
            shutil.copy2(extracted_exe, safe_staged_file)
            staged_file = safe_staged_file
            logger.info("[Updater] Copied extracted executable to safe location: %s", staged_file)

            # Cleanup the extracted directory after we have the exe path
            try:
                shutil.rmtree(extract_dir)
            except Exception as e:
                logger.debug("[Updater] Failed to remove temporary extract dir %s: %s", extract_dir, e)

        pid = os.getpid()
        updates_dir = get_updates_dir()
        updater_ps = updates_dir / "vyntra_updater.ps1"
        updater_script = updates_dir / "vyntra_updater.bat"
        updater_log = updates_dir / "vyntra_updater.log"

        logger.info("[Updater] Preparing Windows updater scripts: %s, %s", updater_ps, updater_script)
        logger.info("[Updater] Target executable: %s | New payload: %s", target_path, staged_file)

        ps_target = str(target_path).replace("'", "''")
        ps_new = str(staged_file).replace("'", "''")
        ps_log = str(updater_log).replace("'", "''")
        ps_backup = f"{ps_target}.bak"

        # 1. PowerShell updater script:
        # Purges _MEIPASS2 so the new PyInstaller executable will unpack cleanly,
        # waits for process exit and OS handle release, replaces in-place, and restarts.
        ps_content = f"""param()
# Crucial: Purge PyInstaller runtime temp environment variables so the new executable
# does NOT attempt to reuse the deleted temp extraction directory of the old process.
Remove-Item Env:\\_MEIPASS2 -ErrorAction SilentlyContinue
Remove-Item Env:\\_MEIPASS -ErrorAction SilentlyContinue
[System.Environment]::SetEnvironmentVariable('_MEIPASS2', $null, 'Process')
[System.Environment]::SetEnvironmentVariable('_MEIPASS', $null, 'Process')

$PIDToWait = {pid}
$TargetPath = '{ps_target}'
$NewExePath = '{ps_new}'
$LogPath = '{ps_log}'
$BackupPath = '{ps_backup}'

function Log-Msg($msg) {{
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$timestamp] [Vyntra Updater PS] $msg" | Out-File -FilePath $LogPath -Append -Encoding utf8
}}

Log-Msg "Started update replacement. PID=$PIDToWait, TARGET=$TargetPath, NEW_EXE=$NewExePath"

# Wait for calling Vyntra process to terminate
$waitCount = 0
while ($waitCount -lt 30) {{
    $proc = Get-Process -Id $PIDToWait -ErrorAction SilentlyContinue
    if (-not $proc) {{
        break
    }}
    $waitCount++
    if ($waitCount -gt 12) {{
        Log-Msg "Terminating unresponsive process $PIDToWait..."
        Stop-Process -Id $PIDToWait -Force -ErrorAction SilentlyContinue
    }}
    Start-Sleep -Milliseconds 500
}}

Log-Msg "Process $PIDToWait terminated. Waiting for OS file locks to release..."
Start-Sleep -Seconds 3

$attempts = 0
$success = $false

while ($attempts -lt 20) {{
    $attempts++
    Log-Msg "Attempt $attempts of 20 in-place replacement..."
    try {{
        # Verify file-lock is released by testing write access
        if (Test-Path -LiteralPath $TargetPath) {{
            try {{
                $testStream = [System.IO.File]::Open($TargetPath, 'Open', 'ReadWrite', 'None')
                $testStream.Close()
            }} catch {{
                Log-Msg "File still locked: $($_.Exception.Message). Waiting..."
                Start-Sleep -Seconds 2
                continue
            }}
        }}
        if (Test-Path -LiteralPath $BackupPath) {{
            Remove-Item -LiteralPath $BackupPath -Force -ErrorAction SilentlyContinue
        }}
        if (Test-Path -LiteralPath $TargetPath) {{
            Move-Item -LiteralPath $TargetPath -Destination $BackupPath -Force -ErrorAction Stop
        }}
        Copy-Item -LiteralPath $NewExePath -Destination $TargetPath -Force -ErrorAction Stop

        if (Test-Path -LiteralPath $TargetPath) {{
            $success = $true
            Log-Msg "Successfully updated $TargetPath in-place."
            break
        }}
    }} catch {{
        Log-Msg "Attempt $attempts failed: $($_.Exception.Message). Retrying in 1s..."
        Start-Sleep -Seconds 1
    }}
}}

if ($success) {{
    if (Test-Path -LiteralPath $BackupPath) {{
        Remove-Item -LiteralPath $BackupPath -Force -ErrorAction SilentlyContinue
    }}
    if (Test-Path -LiteralPath $NewExePath) {{
        Remove-Item -LiteralPath $NewExePath -Force -ErrorAction SilentlyContinue
    }}

    $targetDir = Split-Path -Parent $TargetPath
    Log-Msg "Restart target: $TargetPath (workdir: $targetDir)..."
    # Ensure environment is clean before starting the new PyInstaller executable
    Remove-Item Env:\\_MEIPASS2 -ErrorAction SilentlyContinue
    Remove-Item Env:\\_MEIPASS -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Start-Process -FilePath $TargetPath -WorkingDirectory $targetDir -WindowStyle Normal
    Log-Msg "Update completed successfully. Exiting."
    exit 0
}} else {{
    Log-Msg "ERROR: In-place replacement failed after 20 attempts. Rolling back..."
    if (Test-Path -LiteralPath $BackupPath) {{
        Copy-Item -LiteralPath $BackupPath -Destination $TargetPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $BackupPath -Force -ErrorAction SilentlyContinue
        $targetDir = Split-Path -Parent $TargetPath
        Start-Process -FilePath $TargetPath -WorkingDirectory $targetDir
    }}
    exit 1
}}
"""
        with open(updater_ps, "w", encoding="utf-8") as f:
            f.write(ps_content)

        # 2. Batch script wrapper and fallback:
        script_content = f"""@echo off
setlocal enabledelayedexpansion
title Vyntra Updater

rem Cleanse PyInstaller runtime environment variables
set "_MEIPASS2="
set "_MEIPASS="

set "PID={pid}"
set "TARGET={target_path}"
set "NEW_EXE={staged_file}"
set "BACKUP={target_path}.bak"
set "LOG={updater_log}"

echo [%DATE% %TIME%] [Vyntra Updater] Started update replacement. >> "!LOG!"
echo [%DATE% %TIME%] [Vyntra Updater] PID=!PID!, TARGET=!TARGET!, NEW_EXE=!NEW_EXE! >> "!LOG!"

rem Try primary PowerShell updater (fast, reliable, and native to Windows)
where powershell >NUL 2>&1
if not errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{updater_ps}"
    if not errorlevel 1 exit 0
    echo [%DATE% %TIME%] [Vyntra Updater] PowerShell updater exited with error. Using batch fallback... >> "!LOG!"
)

echo [Vyntra Updater] Waiting for running process !PID! to terminate...
set /a WAIT_COUNT=0
:wait_process
tasklist /fi "PID eq !PID!" 2>NUL | find /I "!PID!" >NUL
if not errorlevel 1 (
    set /a WAIT_COUNT+=1
    if !WAIT_COUNT! gtr 10 (
        echo [%DATE% %TIME%] [Vyntra Updater] Terminating unresponsive process !PID!... >> "!LOG!"
        taskkill /f /pid !PID! >NUL 2>&1
    )
    ping 127.0.0.1 -n 2 >NUL
    goto wait_process
)

echo [%DATE% %TIME%] [Vyntra Updater] Process !PID! terminated. Waiting for handle release... >> "!LOG!"
ping 127.0.0.1 -n 5 >NUL

echo [Vyntra Updater] Updating executable in-place...
set /a ATTEMPTS=0
:replace_loop
set /a ATTEMPTS+=1
echo [%DATE% %TIME%] [Vyntra Updater] Attempt !ATTEMPTS! of 20... >> "!LOG!"

rem Ensure any previous backup is removed
if exist "!BACKUP!" del /f /q "!BACKUP!" >NUL 2>&1

rem Rename current target to backup
move /y "!TARGET!" "!BACKUP!" >NUL 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] [Vyntra Updater] Failed to backup target !TARGET!. Retrying... >>"!LOG!"
    goto replace_retry
)

rem Copy new executable into place
copy /y "!NEW_EXE!" "!TARGET!" >NUL 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] [Vyntra Updater] Copy new exe failed. Retrying... >>"!LOG!"
    goto replace_retry
)

rem Verify replacement succeeded by checking file existence
if exist "!TARGET!" (
    goto replace_success
) else (
    echo [%DATE% %TIME%] [Vyntra Updater] Target not found after copy. Retrying... >>"!LOG!"
    goto replace_retry
)

:replace_retry
if !ATTEMPTS! leq 20 (
    ping 127.0.0.1 -n 2 >NUL
    goto replace_loop
)

goto rollback

:replace_success
echo [%DATE% %TIME%] [Vyntra Updater] Successfully updated !TARGET! in-place. >> "!LOG!"

:: Remove temporary files so only the single updated executable remains
if exist "!NEW_EXE!" del /f /q "!NEW_EXE!" >NUL 2>&1
if exist "!BACKUP!" del /f /q "!BACKUP!" >NUL 2>&1

echo [Vyntra Updater] Starting updated Vyntra...
set "_MEIPASS2="
set "_MEIPASS="
for %%I in ("!TARGET!") do set "TARGET_DIR=%%~dpI"
start "" /d "!TARGET_DIR!" "!TARGET!"
echo [%DATE% %TIME%] [Vyntra Updater] Launched updated Vyntra. Exiting updater. >> "!LOG!"
exit 0

:rollback
echo [%DATE% %TIME%] [Vyntra Updater ERROR] Replacement failed after 20 attempts. Rolling back... >> "!LOG!"
if exist "!BACKUP!" (
    copy /y "!BACKUP!" "!TARGET!" >NUL 2>&1
    del /f /q "!BACKUP!" >NUL 2>&1
    set "_MEIPASS2="
    set "_MEIPASS="
    for %%I in ("!TARGET!") do set "TARGET_DIR=%%~dpI"
    start "" /d "!TARGET_DIR!" "!TARGET!"
)
exit 1
"""

        with open(updater_script, "w", encoding="utf-8") as f:
            f.write(script_content)

        logger.info("[Updater] Launching detached updater helper process...")

        # Purge _MEIPASS2 and _MEIPASS from the spawned environment
        clean_env = os.environ.copy()
        clean_env.pop("_MEIPASS2", None)
        clean_env.pop("_MEIPASS", None)

        # CREATE_NO_WINDOW = 0x08000000 ensures hidden background execution without console window flashing
        creation_flags = 0x08000000

        try:
            subprocess.Popen(
                ["cmd.exe", "/c", str(updater_script)],
                env=clean_env,
                close_fds=True,
                creationflags=creation_flags,
            )
        except Exception as e:
            logger.error("[Updater] Failed to spawn updater script: %s", e)
            raise RuntimeError(f"Could not spawn update process: {e}") from e

        logger.info("[Updater] Updater spawned successfully. Terminating Vyntra instance for replacement.")
        # Gracefully withdraw and quit Tkinter if running to prevent secondary-thread DLL aborts
        try:
            import tkinter
            root = getattr(tkinter, "_default_root", None)
            if root:
                root.withdraw()
                root.quit()
        except Exception:
            pass

        try:
            import logging
            logging.shutdown()
        except Exception:
            pass

        import time
        time.sleep(0.5)

        # os._exit terminates the entire process immediately, releasing locks on the executable
        os._exit(0)
