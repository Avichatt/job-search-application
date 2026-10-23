"""HTML report generator using Jinja2 templates."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from src.models import MatchResult, SearchRun
from src.freshness import format_age


def generate_report(
    matches: list[MatchResult],
    run: SearchRun,
    template_dir: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> tuple[str, str]:
    """
    Generate an HTML report for the search results.

    Returns:
        (html_content, saved_file_path)
    """
    if template_dir is None:
        template_dir = str(Path(__file__).resolve().parent.parent / "templates")

    if output_dir is None:
        output_dir = str(Path(__file__).resolve().parent.parent / "reports")

    os.makedirs(output_dir, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=True,
    )

    # Register custom filters
    env.filters["format_age"] = lambda job: format_age(job)

    template = env.get_template("report.html")

    # Prepare template data
    now = datetime.utcnow()
    urgent = [m for m in matches if m.total_score >= 90 and m.job.age_hours and m.job.age_hours < 6]
    strong = [m for m in matches if 80 <= m.total_score < 90]
    good = [m for m in matches if 70 <= m.total_score < 80]

    # Collect all missing skills across jobs
    all_missing = {}
    for m in matches:
        for skill in m.missing_skills:
            all_missing[skill] = all_missing.get(skill, 0) + 1
    top_gaps = sorted(all_missing.items(), key=lambda x: x[1], reverse=True)[:5]

    best_match = matches[0] if matches else None

    html = template.render(
        matches=matches,
        run=run,
        now=now,
        urgent_count=len(urgent),
        strong_count=len(strong),
        good_count=len(good),
        best_match=best_match,
        urgent_matches=urgent[:5],
        top_gaps=top_gaps,
        format_age=format_age,
    )

    # Save to file — overwrite latest_report.html each run to avoid
    # accumulating timestamped copies in the reports folder
    filename = "latest_report.html"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    return html, filepath


def generate_console_summary(
    matches: list[MatchResult],
    run: SearchRun,
) -> str:
    """Generate a text summary for console output."""
    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append("  📋 JOB SEARCH REPORT")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  Search time:              {run.started_at.strftime('%Y-%m-%d %H:%M UTC') if run.started_at else 'N/A'}")
    lines.append(f"  Sources searched:         {', '.join(run.sources_searched)}")
    lines.append(f"  Jobs discovered:          {run.jobs_discovered}")
    lines.append(f"  Jobs passing freshness:   {run.jobs_fresh}")
    lines.append(f"  Relevant matches (≥70%):  {run.jobs_relevant}")
    lines.append(f"  New jobs reported:        {run.jobs_reported}")
    lines.append("")

    if not matches:
        lines.append("  No new matching jobs found in this run.")
        lines.append("")
        return "\n".join(lines)

    lines.append("-" * 60)

    for match in matches:
        job = match.job
        emoji = match.tier_emoji
        priority = f"{match.priority_emoji} {match.priority_label}"
        age_str = format_age(job)

        lines.append("")
        lines.append(f"  {emoji} {match.total_score}% Match — {job.title}")
        lines.append(f"  {'─' * 50}")
        lines.append(f"  Company:     {job.company}")
        lines.append(f"  Location:    {job.location}")
        lines.append(f"  Work mode:   {job.work_mode.value}")
        lines.append(f"  Posted:      {age_str}")
        lines.append(f"  Source:      {job.source}")
        lines.append(f"  Priority:    {priority}")

        if job.salary:
            lines.append(f"  Salary:      {job.salary}")

        if match.match_reasons:
            lines.append(f"  ✅ Why it matches:")
            for reason in match.match_reasons:
                lines.append(f"     • {reason}")

        if match.gaps:
            lines.append(f"  ⚠️  Potential gaps:")
            for gap in match.gaps[:3]:
                lines.append(f"     • {gap}")

        if job.application_url:
            lines.append(f"  🔗 Apply:    {job.application_url}")

        lines.append("")

    # Summary footer
    lines.append("=" * 60)
    lines.append("  📊 RUN SUMMARY")
    lines.append("=" * 60)

    urgent = [m for m in matches if m.total_score >= 90 and m.job.age_hours and m.job.age_hours < 6]
    lines.append(f"  🔴 Apply Immediately:  {len(urgent)}")
    lines.append(f"  🟠 Apply Today:        {len([m for m in matches if 80 <= m.total_score < 90])}")
    lines.append(f"  🟡 Consider:           {len([m for m in matches if 70 <= m.total_score < 80])}")

    if matches:
        best = matches[0]
        lines.append("")
        lines.append(f"  🏆 Best opportunity: {best.job.title} at {best.job.company} ({best.total_score}%)")

    if urgent:
        lines.append("")
        lines.append("  ⏰ Most urgent applications:")
        for i, m in enumerate(urgent[:3], 1):
            age_str = format_age(m.job)
            lines.append(f"     {i}. {m.job.title} @ {m.job.company} — {m.total_score}% — {age_str}")

    # Skill gaps
    all_missing = {}
    for m in matches:
        for skill in m.missing_skills:
            all_missing[skill] = all_missing.get(skill, 0) + 1
    top_gaps = sorted(all_missing.items(), key=lambda x: x[1], reverse=True)[:5]

    if top_gaps:
        lines.append("")
        lines.append("  📚 Important skill gaps noticed:")
        for skill, count in top_gaps:
            lines.append(f"     • {skill} (mentioned in {count} job{'s' if count > 1 else ''})")

    if run.errors:
        lines.append("")
        lines.append("  ⚠️  Errors during search:")
        for err in run.errors:
            lines.append(f"     • {err}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("")

    return "\n".join(lines)
