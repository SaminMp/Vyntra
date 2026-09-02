#!/usr/bin/env python3
"""
Launcher script for Vyntra.
"""

import os
import sys

# Ensure current directory is in Python module search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vyntra.main import main

if __name__ == "__main__":
    main()
