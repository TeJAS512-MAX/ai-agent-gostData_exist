#!/usr/bin/env python3
"""
Northstar Shop — Autonomous Deletion Audit Agent
Root entrypoint delegating to code/main.py.
"""
import sys
from pathlib import Path

# Add code directory to path
CODE_DIR = str(Path(__file__).resolve().parent / "code")
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

from main import main

if __name__ == "__main__":
    raise SystemExit(main())
