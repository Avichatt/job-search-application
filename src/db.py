"""SQLite database layer for persisting jobs, runs, and reported state."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models import Job, WorkMode, EmploymentType


_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT NOT NULL,
    country TEXT,
    city TEXT,
    work_mode TEXT,
    employment_type TEXT,
    posted_at TEXT,
    discovered_at TEXT,
    source TEXT,
    application_url TEXT,
    description TEXT,
    salary TEXT,
    match_score INTEGER DEFAULT 0,
    match_details TEXT,
    status TEXT DEFAULT 'new',
    job_id_external TEXT,
    tags TEXT
);

CREATE TABLE IF NOT EXISTS reported_jobs (
    job_id TEXT NOT NULL,
    reported_at TEXT NOT NULL,
    run_id TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS search_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT,
    completed_at TEXT,
    jobs_discovered INTEGER DEFAULT 0,
    jobs_fresh INTEGER DEFAULT 0,
    jobs_relevant INTEGER DEFAULT 0,
    jobs_reported INTEGER DEFAULT 0,
    sources_searched TEXT,
    errors TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_company_title ON jobs(company, title);
CREATE INDEX IF NOT EXISTS idx_jobs_posted ON jobs(posted_at);
CREATE INDEX IF NOT EXISTS idx_reported_job_id ON reported_jobs(job_id);
"""


class JobDatabase:
    """Manages the SQLite database for the job search agent."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base = Path(__file__).resolve().parent.parent / "data"
            base.mkdir(parents=True, exist_ok=True)
            db_path = str(base / "jobs.db")

        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Jobs ────────────────────────────────────────────────

    def upsert_job(self, job: Job, match_score: int = 0, match_details: str = ""):
        """Insert or update a job record."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO jobs
               (id, company, title, location, country, city, work_mode,
                employment_type, posted_at, discovered_at, source,
                application_url, description, salary, match_score,
                match_details, status, job_id_external, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 application_url = COALESCE(excluded.application_url, application_url),
                 match_score = MAX(excluded.match_score, match_score),
                 match_details = COALESCE(excluded.match_details, match_details),
                 discovered_at = MIN(discovered_at, excluded.discovered_at)
            """,
            (
                job.id,
                job.company,
                job.title,
                job.location,
                job.country,
                job.city,
                job.work_mode.value,
                job.employment_type.value,
                job.posted_at.isoformat() if job.posted_at else None,
                job.discovered_at.isoformat() if job.discovered_at else datetime.utcnow().isoformat(),
                job.source,
                job.application_url,
                job.description,
                job.salary,
                match_score,
                match_details,
                "new",
                job.job_id_external,
                json.dumps(job.tags) if job.tags else "[]",
            ),
        )
        conn.commit()

    def is_previously_reported(self, job_id: str) -> bool:
        """Check if a job has already been reported to the user."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM reported_jobs WHERE job_id = ? LIMIT 1", (job_id,)
        ).fetchone()
        return row is not None

    def mark_reported(self, job_id: str, run_id: str):
        """Mark a job as reported in a specific run."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO reported_jobs (job_id, reported_at, run_id) VALUES (?, ?, ?)",
            (job_id, datetime.utcnow().isoformat(), run_id),
        )
        conn.commit()

    def get_all_reported_ids(self) -> set[str]:
        """Return the set of all previously reported job IDs."""
        conn = self._get_conn()
        rows = conn.execute("SELECT DISTINCT job_id FROM reported_jobs").fetchall()
        return {row["job_id"] for row in rows}

    def job_exists(self, job_id: str) -> bool:
        """Check if a job exists in the database."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM jobs WHERE id = ? LIMIT 1", (job_id,)
        ).fetchone()
        return row is not None

    # ── Search Runs ─────────────────────────────────────────

    def save_search_run(
        self,
        run_id: str,
        started_at: datetime,
        completed_at: datetime,
        jobs_discovered: int,
        jobs_fresh: int,
        jobs_relevant: int,
        jobs_reported: int,
        sources_searched: list[str],
        errors: list[str],
    ):
        """Record metadata about a completed search run."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO search_runs
               (id, started_at, completed_at, jobs_discovered, jobs_fresh,
                jobs_relevant, jobs_reported, sources_searched, errors)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                started_at.isoformat(),
                completed_at.isoformat(),
                jobs_discovered,
                jobs_fresh,
                jobs_relevant,
                jobs_reported,
                json.dumps(sources_searched),
                json.dumps(errors),
            ),
        )
        conn.commit()

    def get_last_run_time(self) -> Optional[datetime]:
        """Get the timestamp of the most recent completed run."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT completed_at FROM search_runs ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        if row and row["completed_at"]:
            return datetime.fromisoformat(row["completed_at"])
        return None

    # ── Stats ───────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get summary statistics."""
        conn = self._get_conn()
        total_jobs = conn.execute("SELECT COUNT(*) as c FROM jobs").fetchone()["c"]
        total_reported = conn.execute(
            "SELECT COUNT(DISTINCT job_id) as c FROM reported_jobs"
        ).fetchone()["c"]
        total_runs = conn.execute(
            "SELECT COUNT(*) as c FROM search_runs"
        ).fetchone()["c"]
        return {
            "total_jobs_tracked": total_jobs,
            "total_jobs_reported": total_reported,
            "total_search_runs": total_runs,
        }
