#!/usr/bin/env python3
"""
Entry point shortcut script for the AI Job Search Agent.

Usage:
  python run_search.py
  python run_search.py --dry-run
  python run_search.py --min-score 75 --max-age 12
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.main import main

if __name__ == "__main__":
    main()
