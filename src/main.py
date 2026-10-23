"""Job Search Agent main orchestrator pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.config import load_profile, load_settings, Settings
from src.db import JobDatabase
from src.dedup import deduplicate_jobs
from src.fraud_filter import filter_fraudulent_jobs
from src.freshness import filter_fresh_jobs
from src.models import Job, MatchResult, SearchRun, CandidateProfile
from src.notifier import send_email_report
from src.report import generate_console_summary, generate_report
from src.excel_exporter import export_to_excel
from src.resume_parser import ResumeData
from src.scorer import score_job
from src.sources.base import BaseSource
from src.sources.jobspy_source import JobSpySource
from src.sources.remotive import RemotiveSource
from src.sources.remoteok import RemoteOKSource
from src.sources.himalayas import HimalayasSource
from src.sources.arbeitnow import ArbeitnowSource
from src.sources.adzuna import AdzunaSource
from src.sources.linkedin_direct import LinkedInSource
from src.sources.jobicy import JobicySource

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("job_agent")


def get_active_sources(settings: Settings) -> list[BaseSource]:
    """Instantiate enabled source adapters based on configuration."""
    sources: list[BaseSource] = []

    # Direct LinkedIn source (always active if jobspy/linkedin is enabled)
    if settings.sources.jobspy:
        sources.append(LinkedInSource())

    if settings.sources.remotive:
        sources.append(RemotiveSource())

    if settings.sources.remoteok:
        sources.append(RemoteOKSource())

    if settings.sources.himalayas:
        sources.append(HimalayasSource())

    if settings.sources.arbeitnow:
        sources.append(ArbeitnowSource())

    # Jobicy live remote developer source
    sources.append(JobicySource())

    if settings.sources.adzuna and settings.adzuna.enabled:
        sources.append(
            AdzunaSource(
                app_id=settings.adzuna.app_id,
                app_key=settings.adzuna.app_key,
            )
        )

    # Secondary multi-scraper if python-jobspy is available
    if settings.sources.jobspy:
        sources.append(JobSpySource())

    return sources


def run_pipeline(
    profile_path: Optional[str] = None,
    settings_path: Optional[str] = None,
    dry_run: bool = False,
    no_email: bool = False,
    min_score_override: Optional[int] = None,
    max_age_hours_override: Optional[int] = None,
) -> tuple[list[MatchResult], SearchRun]:
    """
    Execute the end-to-end automated job search pipeline.

    Returns:
        (matches, search_run_metadata)
    """
    start_time = datetime.utcnow()
    run_id = f"run_{start_time.strftime('%Y%m%d_%H%M%S')}"
    run = SearchRun(id=run_id, started_at=start_time)

    # 1. Load Configurations
    logger.info("Loading candidate profile and application settings...")
    profile = load_profile(profile_path)
    settings = load_settings(settings_path)

    if min_score_override is not None:
        settings.min_match_score = min_score_override
    if max_age_hours_override is not None:
        settings.freshness_hours = max_age_hours_override

    # 2. Parse Resume
    resume = ResumeData(settings.resume_path)
    if resume.is_loaded:
        logger.info(f"Loaded resume with {len(resume.skills)} detected skills.")
    else:
        logger.info("No resume file loaded. Scoring will rely on profile.yaml skills.")

    # 3. Initialize Database
    db_path = os.path.join(settings.data_dir, "jobs.db") if settings.data_dir else None
    db = JobDatabase(db_path)
    reported_ids = db.get_all_reported_ids()
    logger.info(f"Database initialized. Total previously reported jobs: {len(reported_ids)}")

    # 4. Initialize Sources
    sources = get_active_sources(settings)
    run.sources_searched = [s.name for s in sources]
    logger.info(f"Active sources ({len(sources)}): {', '.join(run.sources_searched)}")

    # 5. Fetch Jobs from all sources
    raw_jobs: list[Job] = []
    for source in sources:
        logger.info(f"Querying {source.name}...")
        try:
            source_jobs = source.safe_search(
                profile=profile,
                max_results=settings.max_results_per_source,
                hours_old=settings.freshness_hours,
            )
            raw_jobs.extend(source_jobs)
        except Exception as e:
            err_msg = f"Error querying {source.name}: {e}"
            logger.error(err_msg, exc_info=True)
            run.errors.append(err_msg)

    run.jobs_discovered = len(raw_jobs)
    logger.info(f"Total raw jobs discovered across sources: {run.jobs_discovered}")

    # 6. Apply Freshness Filter (< 24h)
    fresh_jobs = filter_fresh_jobs(raw_jobs, max_age_hours=settings.freshness_hours)
    run.jobs_fresh = len(fresh_jobs)
    logger.info(f"Jobs passing strict freshness check (<={settings.freshness_hours}h): {run.jobs_fresh}")

    # 7. Apply Quality & Fraud Filter
    clean_jobs, flagged = filter_fraudulent_jobs(fresh_jobs)
    if flagged:
        logger.info(f"Filtered out {len(flagged)} suspicious / low-quality jobs.")

    # 8. Deduplicate Jobs
    unique_jobs = deduplicate_jobs(clean_jobs)
    logger.info(f"Unique jobs after cross-source deduplication: {len(unique_jobs)}")

    # Filter out previously reported jobs
    unseen_jobs = [j for j in unique_jobs if j.id not in reported_ids]
    logger.info(f"New unseen jobs to evaluate: {len(unseen_jobs)}")

    # 9. Match Scoring (0-100)
    all_scored_results: list[MatchResult] = []
    matches: list[MatchResult] = []

    for job in unique_jobs:
        result = score_job(job, profile, resume)
        all_scored_results.append(result)
        if result.total_score >= settings.min_match_score and job.id not in reported_ids:
            matches.append(result)

    # Sort matches by total score descending, then by freshness
    matches.sort(
        key=lambda m: (
            m.total_score,
            -(m.job.age_hours if m.job.age_hours is not None else 999),
        ),
        reverse=True,
    )

    all_scored_results.sort(
        key=lambda m: (
            m.total_score,
            -(m.job.age_hours if m.job.age_hours is not None else 999),
        ),
        reverse=True,
    )

    run.jobs_relevant = len(matches)
    run.jobs_reported = len(matches)
    run.completed_at = datetime.utcnow()

    # 10. Persist to Database if not dry run
    if not dry_run:
        # Save all discovered unique jobs with their computed scores to DB
        for result in all_scored_results:
            db.upsert_job(
                result.job,
                match_score=result.total_score,
                match_details=json.dumps(result.score_breakdown()),
            )
        for m in matches:
            db.mark_reported(m.job.id, run_id)

        db.save_search_run(
            run_id=run.id,
            started_at=run.started_at,
            completed_at=run.completed_at,
            jobs_discovered=run.jobs_discovered,
            jobs_fresh=run.jobs_fresh,
            jobs_relevant=run.jobs_relevant,
            jobs_reported=run.jobs_reported,
            sources_searched=run.sources_searched,
            errors=run.errors,
        )
        logger.info(f"Persisted {len(all_scored_results)} jobs and {len(matches)} new matches to database.")

    # 11. Generate HTML, Excel & Console Reports
    reports_output_dir = settings.reports_dir if settings.reports_dir else None
    html_content, html_path = generate_report(
        matches=matches,
        run=run,
        output_dir=reports_output_dir,
    )
    xlsx_path, csv_path = export_to_excel(
        matches=matches,
        all_results=all_scored_results,
        run=run,
        output_dir=reports_output_dir,
    )
    console_text = generate_console_summary(matches, run)
    print(console_text)
    logger.info(f"HTML report saved to: {html_path}")
    logger.info(f"Excel report saved to: {xlsx_path}")
    logger.info(f"Master Excel file updated: {os.path.join(reports_output_dir or 'reports', 'latest_job_matches.xlsx')}")

    # 12. Send Email Notification
    if settings.smtp.server and settings.smtp.to_address and not no_email and not dry_run:
        logger.info(f"Dispatching email report to {settings.smtp.to_address}...")
        sent = send_email_report(
            smtp_config=settings.smtp,
            html_content=html_content,
            match_count=len(matches),
            report_filepath=html_path,
        )
        if sent:
            logger.info("Email notification delivered successfully.")
        else:
            logger.warning("Email notification failed or was skipped.")

    db.close()
    return matches, run


def main():
    """CLI entry point with flag support."""
    parser = argparse.ArgumentParser(
        description="Personal AI Job Search Agent — Instant Fresh Job Matcher"
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Path to custom candidate profile YAML file",
    )
    parser.add_argument(
        "--settings",
        type=str,
        default=None,
        help="Path to custom application settings YAML file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run search & scoring without saving to database or sending emails",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Skip sending email notifications even if configured",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=None,
        help="Override minimum match score threshold (0-100)",
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=None,
        help="Override maximum job posting age in hours (e.g. 24 or 48)",
    )

    args = parser.parse_args()

    try:
        run_pipeline(
            profile_path=args.profile,
            settings_path=args.settings,
            dry_run=args.dry_run,
            no_email=args.no_email,
            min_score_override=args.min_score,
            max_age_hours_override=args.max_age,
        )
    except KeyboardInterrupt:
        logger.info("Search interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Fatal error in pipeline: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
