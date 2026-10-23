"""Excel Exporter — exports all discovered jobs and matches to a single unified Excel (.xlsx) workbook and CSV."""

from __future__ import annotations

import csv
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.freshness import format_age
from src.models import Job, MatchResult, SearchRun

logger = logging.getLogger(__name__)


def export_to_excel(
    matches: list[MatchResult],
    all_results: list[MatchResult] | list[Job],
    run: SearchRun,
    output_dir: Optional[str] = None,
) -> tuple[str, str]:
    """
    Export all search results across all sources (LinkedIn, Remotive, RemoteOK,
    Arbeitnow, Himalayas, Adzuna, JobSpy) into a single, unified Excel (.xlsx) workbook and CSV.

    Sheet 1 ('📋 All Jobs & Matches') contains EVERY SINGLE JOB from ALL sources with:
      - Match Score (%) & Priority
      - Job Title, Company, Location, Work Mode
      - DIRECT CLICKABLE APPLY URL
      - Source, Posted Age, Salary
      - Matched Skills, Skill Gaps, Match Highlights
      - Application Status Tracker ('To Apply', 'Applied', etc.)

    Sheet 2 ('🎯 Top Matches (70%+)') contains only high-confidence matches.

    Returns:
        (xlsx_path, csv_path)
    """
    if output_dir is None:
        output_dir = str(Path(__file__).resolve().parent.parent / "reports")

    os.makedirs(output_dir, exist_ok=True)

    # Save only the 'latest' files — overwritten each run so the folder
    # doesn't fill up with timestamped duplicates (Bug fix: was creating 4 files/run)
    xlsx_path = os.path.join(output_dir, "latest_job_matches.xlsx")
    csv_path = os.path.join(output_dir, "latest_job_matches.csv")

    # Convert all_results to MatchResult items if Job objects were passed
    normalized_results: list[MatchResult] = []
    for item in all_results:
        if isinstance(item, MatchResult):
            normalized_results.append(item)
        elif isinstance(item, Job):
            normalized_results.append(MatchResult(job=item, total_score=0))

    # NOTE: We intentionally do NOT merge old DB records here.
    # Merging from the DB was causing stale results (e.g., old Software Engineer
    # jobs from a previous profile) to appear in new exports. The current run's
    # normalized_results already contains all relevant jobs scored this session.


    # Sort all results by score descending, then age
    normalized_results.sort(
        key=lambda m: (
            m.total_score,
            -(m.job.age_hours if m.job.age_hours is not None else 999),
        ),
        reverse=True,
    )

    # 1. Generate Excel via openpyxl
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()

        # Styles
        header_fill_primary = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_fill_secondary = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        border_thin = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )
        font_regular = Font(name="Segoe UI", size=10)
        font_bold = Font(name="Segoe UI", size=10, bold=True)
        font_link = Font(name="Segoe UI", size=10, color="2563EB", underline="single")

        # ── Sheet 1: ALL JOBS & MATCHES (One Unified Sheet) ──
        ws_all = wb.active
        ws_all.title = "📋 All Jobs & Matches"
        ws_all.views.sheetView[0].showGridLines = True

        headers = [
            "Match Score",
            "Priority",
            "Job Title",
            "Company",
            "Direct Apply URL",
            "Source",
            "Location",
            "Work Mode",
            "Posted Age",
            "Salary",
            "Matched Skills",
            "Missing Skills / Gaps",
            "Match Highlights",
            "Application Status",
            "Job ID",
        ]

        ws_all.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws_all.cell(row=1, column=col_idx)
            cell.fill = header_fill_primary
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        ws_all.row_dimensions[1].height = 28

        for row_idx, m in enumerate(normalized_results, start=2):
            job = m.job
            priority_text = f"{m.priority_emoji} {m.priority_label}" if m.total_score >= 70 else "Explore"
            matched_str = ", ".join(m.matched_skills) if m.matched_skills else "—"
            missing_str = ", ".join(m.missing_skills) if m.missing_skills else "—"
            reasons_str = " | ".join(m.match_reasons) if m.match_reasons else "—"
            age_str = format_age(job)
            score_str = f"{m.total_score}%" if m.total_score > 0 else "N/A"

            row_data = [
                score_str,
                priority_text,
                job.title,
                job.company,
                job.application_url or "—",
                job.source.capitalize() if job.source else "Web",
                job.location or "—",
                job.work_mode.value.capitalize() if hasattr(job.work_mode, "value") else str(job.work_mode).capitalize(),
                age_str,
                job.salary or "—",
                matched_str,
                missing_str,
                reasons_str,
                "To Apply",
                job.id,
            ]
            ws_all.append(row_data)

            for col_idx in range(1, len(row_data) + 1):
                cell = ws_all.cell(row=row_idx, column=col_idx)
                cell.font = font_regular
                cell.border = border_thin
                cell.alignment = Alignment(vertical="center")

                # Format Score column
                if col_idx == 1:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.font = font_bold
                    if m.total_score >= 90:
                        cell.fill = PatternFill(start_color="DCFCE7", fill_type="solid")
                    elif m.total_score >= 80:
                        cell.fill = PatternFill(start_color="FEF3C7", fill_type="solid")
                    elif m.total_score >= 70:
                        cell.fill = PatternFill(start_color="DBEAFE", fill_type="solid")

                # Format Priority
                elif col_idx == 2:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.font = font_bold

                # Format Direct Apply URL as clickable hyperlink
                elif col_idx == 5 and job.application_url and job.application_url.startswith("http"):
                    cell.font = font_link
                    cell.hyperlink = job.application_url

                # Format Source
                elif col_idx == 6:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.font = font_bold
                    if job.source.lower() == "linkedin":
                        cell.fill = PatternFill(start_color="E0F2FE", fill_type="solid")  # LinkedIn blue tint
                    elif job.source.lower() == "arbeitnow":
                        cell.fill = PatternFill(start_color="F3E8FF", fill_type="solid")  # Purple tint
                    elif job.source.lower() == "remotive":
                        cell.fill = PatternFill(start_color="ECFDF5", fill_type="solid")  # Green tint
                    elif job.source.lower() == "remoteok":
                        cell.fill = PatternFill(start_color="FFF1F2", fill_type="solid")  # Red tint

                # Format Status
                elif col_idx == 14:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.font = font_bold
                    cell.fill = PatternFill(start_color="F8FAFC", fill_type="solid")

            ws_all.row_dimensions[row_idx].height = 22

        # ── Sheet 2: TOP MATCHES (≥70%) ──
        top_matches = [m for m in normalized_results if m.total_score >= 70]
        if top_matches:
            ws_top = wb.create_sheet(title="🎯 Top Matches (70%+)")
            ws_top.views.sheetView[0].showGridLines = True
            ws_top.append(headers)

            for col_idx in range(1, len(headers) + 1):
                cell = ws_top.cell(row=1, column=col_idx)
                cell.fill = header_fill_secondary
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            ws_top.row_dimensions[1].height = 28

            for row_idx, m in enumerate(top_matches, start=2):
                job = m.job
                priority_text = f"{m.priority_emoji} {m.priority_label}"
                matched_str = ", ".join(m.matched_skills) if m.matched_skills else "—"
                missing_str = ", ".join(m.missing_skills) if m.missing_skills else "—"
                reasons_str = " | ".join(m.match_reasons) if m.match_reasons else "—"
                age_str = format_age(job)

                row_data = [
                    f"{m.total_score}%",
                    priority_text,
                    job.title,
                    job.company,
                    job.application_url or "—",
                    job.source.capitalize() if job.source else "Web",
                    job.location or "—",
                    job.work_mode.value.capitalize() if hasattr(job.work_mode, "value") else str(job.work_mode).capitalize(),
                    age_str,
                    job.salary or "—",
                    matched_str,
                    missing_str,
                    reasons_str,
                    "To Apply",
                    job.id,
                ]
                ws_top.append(row_data)

                for col_idx in range(1, len(row_data) + 1):
                    cell = ws_top.cell(row=row_idx, column=col_idx)
                    cell.font = font_regular
                    cell.border = border_thin
                    cell.alignment = Alignment(vertical="center")

                    if col_idx == 1:
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                        cell.font = font_bold
                        if m.total_score >= 90:
                            cell.fill = PatternFill(start_color="DCFCE7", fill_type="solid")
                        elif m.total_score >= 80:
                            cell.fill = PatternFill(start_color="FEF3C7", fill_type="solid")
                        else:
                            cell.fill = PatternFill(start_color="DBEAFE", fill_type="solid")
                    elif col_idx == 2:
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                        cell.font = font_bold
                    elif col_idx == 5 and job.application_url and job.application_url.startswith("http"):
                        cell.font = font_link
                        cell.hyperlink = job.application_url

                ws_top.row_dimensions[row_idx].height = 22

        # Auto-adjust column widths for all sheets
        for ws in wb.worksheets:
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    val_str = str(cell.value or "")
                    if len(val_str) > max_len:
                        max_len = len(val_str)
                ws.column_dimensions[col_letter].width = max(12, min(max_len + 4, 45))

        # Save timestamped and master Excel file
        wb.save(xlsx_path)
        logger.info(f"Excel report saved to: {xlsx_path}")

    except PermissionError:
        logger.warning(f"{xlsx_path} is currently open in Excel — close it and re-run.")
    except Exception as e:
        logger.error(f"Failed to generate Excel report via openpyxl: {e}", exc_info=True)

    # 2. Export CSV (all jobs, UTF-8 BOM for Excel compatibility)
    try:
        _write_csv(normalized_results, csv_path)
    except PermissionError:
        logger.warning(f"{csv_path} is currently open in Excel. Close it to overwrite.")
    except Exception as e:
        logger.warning(f"Failed to write CSV: {e}")

    return xlsx_path, csv_path


def _write_csv(matches: list[MatchResult], filepath: str):
    """Write all jobs to CSV with UTF-8 BOM so Excel opens it with proper formatting."""
    fieldnames = [
        "Match Score",
        "Priority",
        "Job Title",
        "Company",
        "Direct Apply URL",
        "Source",
        "Location",
        "Work Mode",
        "Posted Age",
        "Salary",
        "Matched Skills",
        "Missing Skills",
        "Match Highlights",
        "Application Status",
        "Job ID",
    ]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for m in matches:
            job = m.job
            writer.writerow({
                "Match Score": f"{m.total_score}%" if m.total_score > 0 else "N/A",
                "Priority": m.priority_label if m.total_score >= 70 else "Explore",
                "Job Title": job.title,
                "Company": job.company,
                "Direct Apply URL": job.application_url,
                "Source": job.source.capitalize() if job.source else "Web",
                "Location": job.location,
                "Work Mode": job.work_mode.value if hasattr(job.work_mode, "value") else str(job.work_mode),
                "Posted Age": format_age(job),
                "Salary": job.salary,
                "Matched Skills": "; ".join(m.matched_skills),
                "Missing Skills": "; ".join(m.missing_skills),
                "Match Highlights": " | ".join(m.match_reasons),
                "Application Status": "To Apply",
                "Job ID": job.id,
            })


def export_db_to_excel(db_path: str, output_path: Optional[str] = None) -> str:
    """Export all jobs saved in the SQLite database to a single unified Excel spreadsheet."""
    import sqlite3
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    if output_path is None:
        reports_dir = str(Path(db_path).resolve().parent.parent / "reports")
        os.makedirs(reports_dir, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(reports_dir, f"database_export_{timestamp}.xlsx")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM jobs ORDER BY match_score DESC, posted_at DESC").fetchall()
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "📋 All Jobs"
    ws.views.sheetView[0].showGridLines = True

    headers = [
        "Match Score", "Job Title", "Company", "Direct Apply URL",
        "Source", "Location", "Work Mode", "Posted At", "Discovered At",
        "Salary", "Status", "Job ID"
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    font_regular = Font(name="Segoe UI", size=10)
    font_bold = Font(name="Segoe UI", size=10, bold=True)
    font_link = Font(name="Segoe UI", size=10, color="2563EB", underline="single")
    border_thin = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, r in enumerate(rows, start=2):
        score_val = r["match_score"] or 0
        score_str = f"{score_val}%" if score_val > 0 else "N/A"
        row_data = [
            score_str,
            r["title"],
            r["company"],
            r["application_url"] or "—",
            (r["source"] or "Web").capitalize(),
            r["location"] or "—",
            (r["work_mode"] or "").capitalize(),
            r["posted_at"] or "—",
            r["discovered_at"] or "—",
            r["salary"] or "—",
            (r["status"] or "New").capitalize(),
            r["id"],
        ]
        ws.append(row_data)

        for col_idx in range(1, len(row_data) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = font_regular
            cell.border = border_thin
            cell.alignment = Alignment(vertical="center")

            if col_idx == 1:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = font_bold
                if score_val >= 90:
                    cell.fill = PatternFill(start_color="DCFCE7", fill_type="solid")
                elif score_val >= 80:
                    cell.fill = PatternFill(start_color="FEF3C7", fill_type="solid")
                elif score_val >= 70:
                    cell.fill = PatternFill(start_color="DBEAFE", fill_type="solid")

            elif col_idx == 4 and r["application_url"] and r["application_url"].startswith("http"):
                cell.font = font_link
                cell.hyperlink = r["application_url"]

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(12, min(max_len + 4, 45))

    wb.save(output_path)
    return output_path
