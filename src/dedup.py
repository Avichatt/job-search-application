"""Job deduplication using multi-signal matching."""

from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

try:
    from rapidfuzz import fuzz
except ImportError:
    import difflib

    class _FuzzFallback:
        @staticmethod
        def ratio(s1: str, s2: str) -> int:
            return int(difflib.SequenceMatcher(None, s1 or "", s2 or "").ratio() * 100)

        @staticmethod
        def token_sort_ratio(s1: str, s2: str) -> int:
            t1 = " ".join(sorted((s1 or "").lower().split()))
            t2 = " ".join(sorted((s2 or "").lower().split()))
            return int(difflib.SequenceMatcher(None, t1, t2).ratio() * 100)

        @staticmethod
        def partial_ratio(s1: str, s2: str) -> int:
            s1 = (s1 or "").lower()
            s2 = (s2 or "").lower()
            if not s1 or not s2:
                return 0
            if len(s1) > len(s2):
                s1, s2 = s2, s1
            best = 0
            for i in range(len(s2) - len(s1) + 1):
                sub = s2[i : i + len(s1)]
                score = int(difflib.SequenceMatcher(None, s1, sub).ratio() * 100)
                if score > best:
                    best = score
            return best

    fuzz = _FuzzFallback()

from src.models import Job


def _normalize_company(name: str) -> str:
    """Normalize company name for comparison."""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [" inc", " inc.", " ltd", " ltd.", " llc", " gmbh",
                   " ag", " co.", " corp", " corp.", " plc", " limited",
                   " technologies", " technology", " tech", " group",
                   " solutions", " services"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    # Remove punctuation
    name = re.sub(r'[^\w\s]', '', name)
    return name.strip()


def _normalize_title(title: str) -> str:
    """Normalize job title for comparison."""
    title = title.lower().strip()
    # Remove common noise
    title = re.sub(r'\(m/f/d\)', '', title)
    title = re.sub(r'\(m/w/d\)', '', title)
    title = re.sub(r'\(f/m/x\)', '', title)
    title = re.sub(r'\(all genders\)', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()


def _normalize_url(url: str) -> str:
    """
    Normalize a URL for comparison by removing tracking parameters
    and standardizing the format.
    """
    if not url:
        return ""

    try:
        parsed = urlparse(url.lower().strip())

        # Remove common tracking params
        tracking_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_content",
            "utm_term", "ref", "referer", "source", "src", "trk",
            "tracking", "click_id", "campaign_id", "fbclid", "gclid",
        }

        query = parse_qs(parsed.query, keep_blank_values=False)
        clean_query = {
            k: v for k, v in query.items() if k not in tracking_params
        }

        clean_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip("/"),
            parsed.params,
            urlencode(clean_query, doseq=True) if clean_query else "",
            "",  # drop fragment
        ))
        return clean_url
    except Exception:
        return url.lower().strip()


def _is_company_career_url(url: str) -> bool:
    """Check if the URL is a direct company careers page (preferred)."""
    url_lower = url.lower()
    career_indicators = [
        "/careers/", "/jobs/", "/career/", "/job/",
        "careers.", "jobs.", "apply.", "talent.",
        "greenhouse.io", "lever.co", "ashbyhq.com",
        "workday.com", "smartrecruiters.com", "bamboohr.com",
        "myworkday", "taleo", "icims.com",
    ]
    return any(indicator in url_lower for indicator in career_indicators)


def _url_source_priority(url: str) -> int:
    """
    Return a priority score for the URL source (lower = better).
    1 = Direct employer / ATS
    2 = Company career page
    3 = Job board
    4 = Aggregator / unknown
    """
    url_lower = url.lower()

    # ATS systems (direct application)
    ats_domains = [
        "greenhouse.io", "lever.co", "ashbyhq.com", "workday.com",
        "smartrecruiters.com", "bamboohr.com", "icims.com",
        "myworkday", "taleo",
    ]
    if any(d in url_lower for d in ats_domains):
        return 1

    # Company career pages
    if _is_company_career_url(url):
        return 2

    # Known job boards
    boards = [
        "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
        "monster.com", "reed.co.uk",
    ]
    if any(d in url_lower for d in boards):
        return 3

    return 4


def deduplicate_jobs(jobs: list[Job]) -> list[Job]:
    """
    Deduplicate jobs using multiple signals:
    1. Exact match on (company + title + location + external_id)
    2. Fuzzy match on (company + title + city) with >85% similarity
    3. URL canonicalization
    4. Description similarity (Jaccard on tokens, >80% threshold)

    When duplicates are found, prefer the source with the best application URL.
    """
    if not jobs:
        return []

    # Group candidates
    unique: list[Job] = []
    seen_exact: set[str] = set()

    for job in jobs:
        # Signal 1: Exact key match
        exact_key = (
            f"{_normalize_company(job.company)}|"
            f"{_normalize_title(job.title)}|"
            f"{job.location.lower().strip()}"
        )

        if job.job_id_external:
            exact_key += f"|{job.job_id_external}"

        if exact_key in seen_exact:
            # Duplicate — but check if this source has a better URL
            _maybe_upgrade_url(unique, job)
            continue

        # Signal 2: Fuzzy match against existing unique jobs
        is_dup = False
        for existing in unique:
            if _is_fuzzy_duplicate(existing, job):
                # Upgrade URL if this source is better
                _maybe_upgrade_url_single(existing, job)
                is_dup = True
                break

        if is_dup:
            continue

        # Signal 3: URL-based dedup
        if job.application_url:
            norm_url = _normalize_url(job.application_url)
            url_dup = False
            for existing in unique:
                if existing.application_url and _normalize_url(existing.application_url) == norm_url:
                    url_dup = True
                    break
            if url_dup:
                continue

        seen_exact.add(exact_key)
        unique.append(job)

    return unique


def _is_fuzzy_duplicate(a: Job, b: Job) -> bool:
    """Check if two jobs are likely the same using fuzzy matching."""
    company_sim = fuzz.ratio(
        _normalize_company(a.company),
        _normalize_company(b.company)
    )
    title_sim = fuzz.ratio(
        _normalize_title(a.title),
        _normalize_title(b.title)
    )

    # High confidence: company and title both very similar
    if company_sim >= 85 and title_sim >= 85:
        return True

    # Medium confidence: same company, similar title, same city
    if company_sim >= 80 and title_sim >= 75:
        city_a = a.city.lower().strip() if a.city else ""
        city_b = b.city.lower().strip() if b.city else ""
        if city_a and city_b and city_a == city_b:
            return True

    # Description similarity as fallback
    if company_sim >= 70 and title_sim >= 70:
        if a.description and b.description:
            desc_sim = _jaccard_similarity(a.description, b.description)
            if desc_sim > 0.80:
                return True

    return False


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """Calculate Jaccard similarity between two texts."""
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _maybe_upgrade_url(unique_jobs: list[Job], candidate: Job):
    """If the candidate has a better URL, upgrade the matching job."""
    for existing in unique_jobs:
        if (
            _normalize_company(existing.company) == _normalize_company(candidate.company)
            and fuzz.ratio(_normalize_title(existing.title), _normalize_title(candidate.title)) >= 85
        ):
            _maybe_upgrade_url_single(existing, candidate)
            return


def _maybe_upgrade_url_single(existing: Job, candidate: Job):
    """Upgrade existing job's URL if candidate has a better source."""
    if not candidate.application_url:
        return
    if not existing.application_url:
        existing.application_url = candidate.application_url
        return

    existing_priority = _url_source_priority(existing.application_url)
    candidate_priority = _url_source_priority(candidate.application_url)

    if candidate_priority < existing_priority:
        existing.application_url = candidate.application_url
        existing.source = candidate.source
