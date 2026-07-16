#!/usr/bin/env python3
"""Run the home companion e-paper server from the repository root."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from home_companian.__main__ import main  # noqa: E402


if __name__ == "__main__":
    main()

