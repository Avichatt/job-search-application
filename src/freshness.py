"""Strict 24-hour freshness filter for job listings."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from src.models import Job


def is_fresh(job: Job, max_age_hours: int = 24) -> bool:
    """
    Check if a job meets the strict freshness requirement.

    Rules:
    - Only include jobs whose original posting time is max_age_hours old or newer.
    - If the exact posting time cannot be established, the job is excluded.
    - We do NOT interpret "recent", "new", "this week" as being within the window.
    """
    if job.posted_at is None:
        # Cannot verify freshness — exclude
        job.freshness_verified = False
        return False

    now = datetime.utcnow()
    age = now - job.posted_at

    max_age = timedelta(hours=max_age_hours)

    if age <= max_age:
        job.freshness_verified = True
        return True

    return False


def filter_fresh_jobs(jobs: list[Job], max_age_hours: int = 24) -> list[Job]:
    """
    Filter a list of jobs to only include those within the freshness window.

    Returns:
        List of jobs that pass the freshness check.
    """
    fresh = []
    for job in jobs:
        if is_fresh(job, max_age_hours):
            fresh.append(job)
    return fresh


def format_age(job: Job) -> str:
    """Format a job's age as a human-readable string."""
    age = job.age_hours
    if age is None:
        return "Unknown"
    if age < 1:
        minutes = int(age * 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif age < 24:
        hours = int(age)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(age / 24)
        return f"{days} day{'s' if days != 1 else ''} ago"
