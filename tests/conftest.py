"""
Pytest configuration and fixture setup for Vyntra tests.
"""

import os
import sys
from pathlib import Path

# Ensure sys.path includes workspace root
WORKSPACE_ROOT = Path(__file__).parent.parent.resolve()
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# Ensure TCL_LIBRARY and TK_LIBRARY are set for Windows virtual environments
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
