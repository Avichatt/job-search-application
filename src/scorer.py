"""Match scoring engine — scores jobs 0–100 against the candidate profile."""

from __future__ import annotations

import re
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

from src.models import (
    Job, MatchResult, CandidateProfile, WorkMode, EmploymentType,
)
from src.resume_parser import ResumeData, extract_skills_from_text


def score_job(
    job: Job,
    profile: CandidateProfile,
    resume: ResumeData,
) -> MatchResult:
    """
    Score a job against the candidate's profile and resume.

    Weights:
        Role/title relevance:     25%  (0-25)
        Required skills match:    20%  (0-20)
        Experience/responsibility: 20% (0-20)
        Seniority match:          10%  (0-10)
        Industry/domain match:    10%  (0-10)
        Location/work-mode match:  5%  (0-5)
        Education/certification:   5%  (0-5)
        Other requirements:        5%  (0-5)
    """
    result = MatchResult(job=job)

    # ── 1. Role/Title Relevance (0-25) ──────────────────────
    result.role_score = _score_role(job, profile)

    # ── 2. Skills Match (0-20) ──────────────────────────────
    result.skills_score, matched, missing = _score_skills(job, profile, resume)
    result.matched_skills = matched
    result.missing_skills = missing

    # ── 3. Experience/Responsibility Match (0-20) ───────────
    result.experience_score = _score_experience(job, resume)

    # ── 4. Seniority Match (0-10) ───────────────────────────
    result.seniority_score = _score_seniority(job, profile)

    # ── 5. Industry/Domain Match (0-10) ─────────────────────
    result.industry_score = _score_industry(job, profile, resume)

    # ── 6. Location/Work-Mode Match (0-5) ───────────────────
    result.location_score = _score_location(job, profile)

    # ── 7. Education/Certification Match (0-5) ──────────────
    result.education_score = _score_education(job, profile, resume)

    # ── 8. Other Requirements (0-5) ─────────────────────────
    result.other_score = _score_other(job, profile)

    # ── Total ───────────────────────────────────────────────
    result.total_score = int(round(
        result.role_score
        + result.skills_score
        + result.experience_score
        + result.seniority_score
        + result.industry_score
        + result.location_score
        + result.education_score
        + result.other_score
    ))

    # Clamp to 0-100
    result.total_score = max(0, min(100, result.total_score))

    # Build match reasons
    result.match_reasons = _build_match_reasons(result, profile)
    result.gaps = _build_gaps(result)

    return result


# ─── Component Scorers ──────────────────────────────────────────


def _score_role(job: Job, profile: CandidateProfile) -> float:
    """Score role/title relevance (0-25)."""
    if not profile.target_roles and not profile.search_title_variations:
        return 12.5  # Neutral if no target roles configured

    job_title = job.title.lower().strip()
    best_score = 0.0

    # Check against all role variations
    all_targets = set()
    for r in profile.target_roles:
        all_targets.add(r.lower())
    for r in profile.search_title_variations:
        all_targets.add(r.lower())

    for target in all_targets:
        # Exact match
        if target == job_title:
            return 25.0

        # Fuzzy match
        ratio = fuzz.token_sort_ratio(target, job_title)
        score = (ratio / 100.0) * 25.0
        best_score = max(best_score, score)

        # Partial containment bonus
        if target in job_title or job_title in target:
            best_score = max(best_score, 22.0)

    return min(best_score, 25.0)


def _score_skills(
    job: Job, profile: CandidateProfile, resume: ResumeData
) -> tuple[float, list[str], list[str]]:
    """Score skills match (0-20). Returns (score, matched, missing)."""
    # Extract skills mentioned in the job description
    job_skills = extract_skills_from_text(job.description)

    if not job_skills:
        # Can't evaluate — give partial credit
        return 10.0, [], []

    # Also consider skills from tags/requirements
    if job.tags:
        for tag in job.tags:
            job_skills.update(extract_skills_from_text(tag))
    if job.requirements:
        for req in job.requirements:
            job_skills.update(extract_skills_from_text(req))

    # Compare against profile + resume skills
    all_candidate_skills = set(profile.all_skills) | resume.skills

    matched = []
    missing = []
    for skill in job_skills:
        if skill in all_candidate_skills:
            matched.append(skill)
        elif any(fuzz.ratio(skill, cs) > 85 for cs in all_candidate_skills):
            matched.append(skill)
        else:
            missing.append(skill)

    total = len(matched) + len(missing)
    if total == 0:
        return 10.0, matched, missing

    ratio = len(matched) / total
    score = ratio * 20.0

    return round(score, 2), matched, missing


def _score_experience(job: Job, resume: ResumeData) -> float:
    """Score experience/responsibility overlap (0-20)."""
    if not job.description or not resume.is_loaded:
        return 10.0

    # Tokenize and compare key responsibility phrases
    job_tokens = set(job.description.lower().split())
    resume_tokens = set(resume.text_lower.split())

    # Remove stopwords for better signal
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "and", "or", "but", "not", "no", "if", "then", "than",
        "this", "that", "these", "those", "it", "its", "we", "you",
        "they", "our", "your", "their", "as", "so",
    }

    job_tokens -= stopwords
    resume_tokens -= stopwords

    if not job_tokens:
        return 10.0

    overlap = job_tokens & resume_tokens
    ratio = len(overlap) / len(job_tokens)

    # Scale to 0-20
    score = min(ratio * 2.5, 1.0) * 20.0
    return round(score, 2)


def _score_seniority(job: Job, profile: CandidateProfile) -> float:
    """Score seniority fit (0-10)."""
    if not profile.total_experience_years:
        return 5.0  # Neutral

    title_lower = job.title.lower()
    desc_lower = (job.description or "").lower()
    years = profile.total_experience_years

    # Extract required years from description
    req_years = _extract_required_years(desc_lower)

    # Title-based seniority estimation
    if any(word in title_lower for word in ["intern", "trainee", "junior", "entry"]):
        expected_range = (0, 3)
    elif any(word in title_lower for word in ["senior", "sr.", "sr "]):
        expected_range = (5, 15)
    elif any(word in title_lower for word in ["lead", "principal", "staff"]):
        expected_range = (7, 20)
    elif any(word in title_lower for word in ["director", "vp", "head of"]):
        expected_range = (10, 30)
    elif any(word in title_lower for word in ["manager"]):
        expected_range = (5, 20)
    else:
        expected_range = (2, 10)  # Mid-level default

    # Check fit
    if req_years:
        if years >= req_years:
            return 10.0
        elif years >= req_years - 2:
            return 7.0
        else:
            return 3.0

    min_exp, max_exp = expected_range
    if min_exp <= years <= max_exp:
        return 10.0
    elif abs(years - min_exp) <= 2 or abs(years - max_exp) <= 2:
        return 7.0
    else:
        return 3.0


def _score_industry(
    job: Job, profile: CandidateProfile, resume: ResumeData
) -> float:
    """Score industry/domain match (0-10)."""
    if not profile.industries:
        return 5.0

    desc_lower = (job.description or "").lower()
    company_lower = job.company.lower()

    for industry in profile.industries:
        ind_lower = industry.lower()
        if ind_lower in desc_lower or ind_lower in company_lower:
            return 10.0

    # Partial match through related terms
    industry_terms = {
        "technology": ["tech", "software", "digital", "it ", "saas"],
        "fintech": ["fintech", "financial technology", "payments", "banking tech"],
        "finance": ["finance", "banking", "investment", "trading", "financial"],
        "healthcare": ["health", "medical", "clinical", "pharma", "biotech"],
        "ecommerce": ["e-commerce", "ecommerce", "retail", "marketplace"],
        "saas": ["saas", "cloud", "platform", "subscription"],
        "education": ["edtech", "education", "learning", "university"],
        "gaming": ["gaming", "game", "entertainment"],
    }

    for industry in profile.industries:
        ind_lower = industry.lower()
        if ind_lower in industry_terms:
            for term in industry_terms[ind_lower]:
                if term in desc_lower:
                    return 8.0

    return 3.0


def _score_location(job: Job, profile: CandidateProfile) -> float:
    """Score location/work-mode fit (0-5)."""
    score = 0.0

    # Country match
    if profile.preferred_countries:
        job_country = job.country.lower().strip()
        if any(c.lower() == job_country for c in profile.preferred_countries):
            score += 2.5
        elif job.work_mode == WorkMode.REMOTE:
            score += 2.0  # Remote jobs transcend geography somewhat
        else:
            score += 0.0

    else:
        score += 2.5  # No preference = full credit

    # Work mode match
    if profile.work_preference == "any":
        score += 2.5
    elif profile.work_preference == "remote" and job.work_mode == WorkMode.REMOTE:
        score += 2.5
    elif profile.work_preference == "hybrid" and job.work_mode in (WorkMode.HYBRID, WorkMode.REMOTE):
        score += 2.5
    elif profile.work_preference == "onsite" and job.work_mode in (WorkMode.ONSITE, WorkMode.UNKNOWN):
        score += 2.0
    elif job.work_mode == WorkMode.UNKNOWN:
        score += 1.5  # Can't penalize for missing info
    else:
        score += 0.5

    return min(score, 5.0)


def _score_education(
    job: Job, profile: CandidateProfile, resume: ResumeData
) -> float:
    """Score education/certification match (0-5)."""
    desc_lower = (job.description or "").lower()

    # Check if job requires specific degrees
    degree_patterns = [
        (r"(?:phd|ph\.d|doctorate)", "phd"),
        (r"(?:master'?s?|m\.s\.|msc|m\.eng|mba)", "masters"),
        (r"(?:bachelor'?s?|b\.s\.|bsc|b\.eng|b\.a\.)", "bachelors"),
    ]

    profile_education_lower = " ".join(e.lower() for e in profile.education)
    resume_text = resume.text_lower if resume.is_loaded else ""

    for pattern, level in degree_patterns:
        if re.search(pattern, desc_lower):
            if re.search(pattern, profile_education_lower) or re.search(pattern, resume_text):
                return 5.0
            elif level == "bachelors":
                # Most common requirement — partial credit if not matched
                return 3.0
            else:
                return 2.0

    # No specific education requirement — full credit
    return 5.0


def _score_other(job: Job, profile: CandidateProfile) -> float:
    """Score other requirements — language, employment type, etc. (0-5)."""
    score = 5.0

    # Employment type mismatch
    if profile.employment_type != "any":
        job_type = job.employment_type.value.lower()
        if job_type != "unknown" and job_type != profile.employment_type:
            score -= 2.0

    # Language requirements
    desc_lower = (job.description or "").lower()
    language_requirements = []
    for lang in ["german", "french", "spanish", "dutch", "mandarin", "japanese"]:
        if f"fluent {lang}" in desc_lower or f"{lang} required" in desc_lower or f"native {lang}" in desc_lower:
            language_requirements.append(lang)

    if language_requirements and profile.languages:
        profile_langs = [l.lower() for l in profile.languages]
        for req_lang in language_requirements:
            if req_lang not in profile_langs:
                score -= 2.0
                break

    return max(0.0, min(score, 5.0))


# ─── Helpers ────────────────────────────────────────────────────


def _extract_required_years(text: str) -> int | None:
    """Extract required years of experience from job description."""
    patterns = [
        r'(\d+)\+?\s*years?\s*(?:of\s+)?(?:experience|exp)',
        r'(?:minimum|at least|min)\s*(\d+)\s*years?',
        r'(\d+)\s*-\s*\d+\s*years?\s*(?:of\s+)?(?:experience|exp)',
    ]
    min_years = None
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            y = int(m)
            if 0 < y < 30:
                if min_years is None or y < min_years:
                    min_years = y
    return min_years


def _build_match_reasons(result: MatchResult, profile: CandidateProfile) -> list[str]:
    """Build human-readable match reasons."""
    reasons = []

    if result.role_score >= 20:
        reasons.append(f"Role closely matches target: {result.job.title}")

    if result.matched_skills:
        top_skills = result.matched_skills[:6]
        reasons.append(f"Skills match: {', '.join(top_skills)}")

    if result.experience_score >= 15:
        reasons.append("Strong responsibility/experience overlap")

    if result.seniority_score >= 8:
        if profile.total_experience_years:
            reasons.append(f"{profile.total_experience_years}+ years experience — matches seniority")

    if result.industry_score >= 8:
        reasons.append("Industry/domain experience aligns")

    if result.location_score >= 4:
        reasons.append(f"Location match: {result.job.location}")

    return reasons


def _build_gaps(result: MatchResult) -> list[str]:
    """Build list of potential gaps."""
    gaps = []

    if result.missing_skills:
        top_missing = result.missing_skills[:5]
        for skill in top_missing:
            gaps.append(f"{skill} — not demonstrated in resume")

    if result.seniority_score < 5:
        gaps.append("Seniority level may not align with experience")

    if result.location_score < 2:
        gaps.append("Location/work-mode mismatch")

    return gaps


def score_and_filter_jobs(
    jobs: list[Job],
    profile: CandidateProfile,
    resume: ResumeData,
    min_score: int = 70,
) -> list[MatchResult]:
    """
    Score all jobs and return only those above the minimum threshold,
    sorted by score descending.
    """
    results = []
    for job in jobs:
        match = score_job(job, profile, resume)
        if match.total_score >= min_score:
            results.append(match)

    results.sort(key=lambda r: r.total_score, reverse=True)
    return results
