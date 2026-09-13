#!/usr/bin/env python3
"""
Launcher script for Vyntra.
"""

import os
import sys

# Ensure current directory is in Python module search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ensure TCL_LIBRARY and TK_LIBRARY are configured for Windows virtual environments
from pathlib import Path
base_tcl = Path(sys.base_prefix) / "tcl"
if base_tcl.exists():
    for p in base_tcl.glob("tcl8.*"):
        if (p / "init.tcl").exists():
            os.environ.setdefault("TCL_LIBRARY", str(p))
            break
    for p in base_tcl.glob("tk8.*"):
        if (p / "tk.tcl").exists():
            os.environ.setdefault("TK_LIBRARY", str(p))
            break

from vyntra.main import main

if __name__ == "__main__":
    main()
