#!/usr/bin/env python3
"""Convenience root entrypoint for submission contract validation."""
import sys
from pathlib import Path

# Add code directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "code"))
from evaluation.validate_submission import main

if __name__ == "__main__":
    raise SystemExit(main())
