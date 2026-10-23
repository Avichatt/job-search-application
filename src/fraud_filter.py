"""Fraud and quality filter for job listings."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from src.models import Job


# Suspicious keywords in job descriptions
FRAUD_INDICATORS = [
    "pay a fee", "pay to apply", "registration fee", "processing fee",
    "buy equipment", "purchase equipment", "buy laptop from",
    "multi-level marketing", "mlm", "network marketing", "pyramid",
    "work from home stuffing envelopes", "data entry $",
    "guaranteed income", "make money fast", "be your own boss",
    "unlimited earning", "financial freedom",
    "no experience needed, earn $",
    "mystery shopper",
]

# Suspicious URL domains
SUSPICIOUS_DOMAINS = [
    "bit.ly", "tinyurl.com", "t.co", "goo.gl",  # URL shorteners in apply links
    "forms.gle",  # Google forms as application
]

# Known job boards where listings are generally trustworthy (whitelist)
TRUSTED_DOMAINS = [
    "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
    "monster.com", "reed.co.uk", "seek.com", "workday.com",
    "greenhouse.io", "lever.co", "ashbyhq.com", "smartrecruiters.com",
    "bamboohr.com", "icims.com", "taleo", "careers",
    "remotive.com", "remoteok.com", "himalayas.app", "arbeitnow.com",
    "adzuna.com", "wellfound.com", "angellist.com",
]


class FraudFilterResult:
    """Result of running the fraud filter on a job."""

    def __init__(self):
        self.is_suspicious = False
        self.reasons: list[str] = []

    def flag(self, reason: str):
        self.is_suspicious = True
        self.reasons.append(reason)


def check_job(job: Job) -> FraudFilterResult:
    """
    Run quality/fraud checks on a job listing.

    Returns a FraudFilterResult indicating whether the job is suspicious.
    """
    result = FraudFilterResult()

    # 1. Missing or blank company
    if not job.company or job.company.strip().lower() in [
        "unknown", "confidential", "n/a", "na", "-", ".", "company",
    ]:
        result.flag("No clear employer/company name")

    # 2. Check description for fraud indicators
    if job.description:
        desc_lower = job.description.lower()
        for indicator in FRAUD_INDICATORS:
            if indicator in desc_lower:
                result.flag(f"Suspicious keyword in description: '{indicator}'")
                break

    # 3. Suspicious application URL
    if job.application_url:
        _check_url(job.application_url, result)

    # 4. Misleading title detection
    _check_misleading_title(job, result)

    # 5. Unpaid position check
    if job.description:
        desc_lower = job.description.lower()
        unpaid_patterns = [
            r'\bunpaid\b', r'\bvolunteer\b', r'\bno (?:salary|compensation|pay)\b',
            r'\b(?:stipend only|unpaid internship)\b',
        ]
        for pattern in unpaid_patterns:
            if re.search(pattern, desc_lower):
                result.flag("Appears to be an unpaid position")
                break

    return result


def _check_url(url: str, result: FraudFilterResult):
    """Check if the application URL is suspicious."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Check for URL shorteners (suspicious for apply links)
        for sus in SUSPICIOUS_DOMAINS:
            if sus in domain:
                result.flag(f"Suspicious application URL domain: {sus}")
                return

        # Check for no domain at all
        if not domain:
            result.flag("Application URL has no domain")
            return

        # Very short or odd domains
        if len(domain) < 4 and "." not in domain:
            result.flag(f"Suspicious short domain: {domain}")

    except Exception:
        result.flag("Malformed application URL")


def _check_misleading_title(job: Job, result: FraudFilterResult):
    """Detect jobs with misleading titles."""
    if not job.title or not job.description:
        return

    title_lower = job.title.lower()
    desc_lower = job.description.lower()

    # "Manager" title but description is clearly entry-level
    if "manager" in title_lower or "director" in title_lower or "lead" in title_lower:
        entry_signals = [
            "no experience required", "0-1 years", "entry level",
            "fresh graduate", "recent graduate",
        ]
        entry_count = sum(1 for s in entry_signals if s in desc_lower)
        if entry_count >= 2:
            result.flag("Title suggests senior role but description indicates entry-level")


def filter_fraudulent_jobs(jobs: list[Job]) -> tuple[list[Job], list[tuple[Job, FraudFilterResult]]]:
    """
    Filter out suspicious/fraudulent jobs.

    Returns:
        (clean_jobs, flagged_jobs_with_reasons)
    """
    clean = []
    flagged = []

    for job in jobs:
        result = check_job(job)
        if result.is_suspicious:
            flagged.append((job, result))
        else:
            clean.append(job)

    return clean, flagged
