#!/usr/bin/env python3
"""
Standalone utility script to export all jobs from the SQLite database
into an Excel (.xlsx) file with direct clickable application URLs.

Usage:
  python export_excel.py
  python export_excel.py --output reports/all_jobs.xlsx
"""

import argparse
import os
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.config import load_settings
from src.excel_exporter import export_db_to_excel


def main():
    parser = argparse.ArgumentParser(description="Export all jobs from database to Excel (.xlsx)")
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to SQLite database file (default: data/jobs.db)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output Excel file path (default: reports/database_export_<timestamp>.xlsx)",
    )

    args = parser.parse_args()

    settings = load_settings()
    default_db = os.path.join(settings.data_dir, "jobs.db") if settings.data_dir else str(root_dir / "data" / "jobs.db")
    db_path = args.db or default_db

    if not os.path.exists(db_path):
        print(f"[ERROR] Database file not found at: {db_path}")
        print("Run 'python run_search.py' first to search and save jobs.")
        sys.exit(1)

    print(f"Exporting jobs from database ({db_path}) to Excel...")
    out_path = export_db_to_excel(db_path=db_path, output_path=args.output)
    print(f"✅ Excel spreadsheet successfully exported to:\n  -> {out_path}")


if __name__ == "__main__":
    main()
