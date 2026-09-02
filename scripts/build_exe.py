"""
Build script for Vyntra Windows Executable.
Automates icon generation, cleans build artifacts, and packages via PyInstaller.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys

def main():
    root_dir = Path(__file__).resolve().parent.parent
    os.chdir(root_dir)
    print(f"[Build] Working directory: {root_dir}")

    # 1. Ensure assets exist
    icon_path = root_dir / "assets" / "icon.ico"
    if not icon_path.exists():
        print("[Build] Generating application icon...")
        from scripts.generate_icons import create_icon
        create_icon()

    # 2. Check credentials.json
    creds_path = root_dir / "credentials.json"
    if creds_path.exists():
        print(f"[Build] Verified developer credentials found: {creds_path.name}")
    else:
        print("[Build] WARNING: credentials.json not found in root. App will rely on built-in fallback.")

    # 3. Locate pyinstaller in current environment
    python_exe = sys.executable
    print(f"[Build] Using Python interpreter: {python_exe}")

    # 4. Clean previous dist/build directories
    build_dir = root_dir / "build"
    dist_dir = root_dir / "dist"
    
    # Run PyInstaller
    spec_path = root_dir / "Vyntra.spec"
    cmd = [python_exe, "-m", "PyInstaller", "--clean", "--noconfirm", str(spec_path)]
    print(f"[Build] Executing command: {' '.join(cmd)}")
    
    res = subprocess.run(cmd, cwd=str(root_dir))
    if res.returncode != 0:
        print(f"\n[Build ERROR] PyInstaller failed with exit code {res.returncode}")
        sys.exit(res.returncode)

    exe_path = dist_dir / "Vyntra.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print("\n" + "=" * 60)
        print("  BUILD SUCCESSFUL!")
        print(f"  Executable: {exe_path}")
        print(f"  Size: {size_mb:.2f} MB")
        print("=" * 60)
    else:
        print(f"\n[Build ERROR] Expected executable not found at: {exe_path}")
        sys.exit(1)

if __name__ == "__main__":
    main()
