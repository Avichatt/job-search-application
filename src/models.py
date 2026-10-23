"""Data models for the Job Search Agent."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional


class WorkMode(Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class EmploymentType(Enum):
    FULL_TIME = "full-time"
    CONTRACT = "contract"
    PART_TIME = "part-time"
    INTERNSHIP = "internship"
    UNKNOWN = "unknown"


class MatchTier(Enum):
    EXCELLENT = "excellent"   # 90-100
    STRONG = "strong"         # 80-89
    GOOD = "good"             # 70-79
    BELOW = "below"           # <70


class ApplicationPriority(Enum):
    APPLY_IMMEDIATELY = "apply_immediately"  # 90%+ & <6h old
    APPLY_TODAY = "apply_today"              # 80-89%
    CONSIDER = "consider"                    # 70-79%


@dataclass
class Job:
    """A single job listing from any source."""
    company: str
    title: str
    location: str
    country: str
    city: str = ""
    work_mode: WorkMode = WorkMode.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    posted_at: Optional[datetime] = None
    discovered_at: Optional[datetime] = None
    source: str = ""
    application_url: str = ""
    description: str = ""
    salary: str = ""
    job_id_external: str = ""
    requirements: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    freshness_verified: bool = True

    @property
    def id(self) -> str:
        """Generate a deterministic hash ID from key fields."""
        raw = f"{self.company.lower().strip()}|{self.title.lower().strip()}|{self.location.lower().strip()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @property
    def age_hours(self) -> Optional[float]:
        """How many hours ago the job was posted."""
        if self.posted_at is None:
            return None
        delta = datetime.utcnow() - self.posted_at
        return delta.total_seconds() / 3600

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["age_hours"] = self.age_hours
        d["work_mode"] = self.work_mode.value
        d["employment_type"] = self.employment_type.value
        if self.posted_at:
            d["posted_at"] = self.posted_at.isoformat()
        if self.discovered_at:
            d["discovered_at"] = self.discovered_at.isoformat()
        return d


@dataclass
class MatchResult:
    """The result of scoring a job against the candidate profile."""
    job: Job
    total_score: int = 0
    role_score: float = 0.0       # 0-25
    skills_score: float = 0.0     # 0-20
    experience_score: float = 0.0 # 0-20
    seniority_score: float = 0.0  # 0-10
    industry_score: float = 0.0   # 0-10
    location_score: float = 0.0   # 0-5
    education_score: float = 0.0  # 0-5
    other_score: float = 0.0      # 0-5
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    match_reasons: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    @property
    def tier(self) -> MatchTier:
        if self.total_score >= 90:
            return MatchTier.EXCELLENT
        elif self.total_score >= 80:
            return MatchTier.STRONG
        elif self.total_score >= 70:
            return MatchTier.GOOD
        return MatchTier.BELOW

    @property
    def priority(self) -> ApplicationPriority:
        age = self.job.age_hours
        if self.total_score >= 90 and age is not None and age < 6:
            return ApplicationPriority.APPLY_IMMEDIATELY
        elif self.total_score >= 80:
            return ApplicationPriority.APPLY_TODAY
        return ApplicationPriority.CONSIDER

    @property
    def tier_emoji(self) -> str:
        return {
            MatchTier.EXCELLENT: "🔥",
            MatchTier.STRONG: "🟢",
            MatchTier.GOOD: "🟡",
            MatchTier.BELOW: "⚪",
        }[self.tier]

    @property
    def priority_emoji(self) -> str:
        return {
            ApplicationPriority.APPLY_IMMEDIATELY: "🔴",
            ApplicationPriority.APPLY_TODAY: "🟠",
            ApplicationPriority.CONSIDER: "🟡",
        }[self.priority]

    @property
    def priority_label(self) -> str:
        return {
            ApplicationPriority.APPLY_IMMEDIATELY: "Apply Immediately",
            ApplicationPriority.APPLY_TODAY: "Apply Today",
            ApplicationPriority.CONSIDER: "Consider",
        }[self.priority]

    def score_breakdown(self) -> dict:
        return {
            "role_relevance": round(self.role_score, 1),
            "skills_match": round(self.skills_score, 1),
            "experience_match": round(self.experience_score, 1),
            "seniority_match": round(self.seniority_score, 1),
            "industry_match": round(self.industry_score, 1),
            "location_match": round(self.location_score, 1),
            "education_match": round(self.education_score, 1),
            "other": round(self.other_score, 1),
            "total": self.total_score,
        }


@dataclass
class CandidateProfile:
    """The job seeker's profile, loaded from profile.yaml."""
    total_experience_years: int = 0
    current_role: str = ""
    target_roles: list[str] = field(default_factory=list)
    primary_skills: list[str] = field(default_factory=list)
    secondary_skills: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    preferred_countries: list[str] = field(default_factory=list)
    preferred_cities: list[str] = field(default_factory=list)
    work_preference: str = "any"  # remote/hybrid/onsite/any
    min_salary: str = ""
    employment_type: str = "full-time"
    visa_status: str = ""
    education: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    # Expanded search terms — auto-generated or manual
    search_title_variations: list[str] = field(default_factory=list)

    @property
    def all_skills(self) -> list[str]:
        return self.primary_skills + self.secondary_skills


@dataclass
class SearchRun:
    """Metadata for a single search execution."""
    id: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    jobs_discovered: int = 0
    jobs_fresh: int = 0
    jobs_relevant: int = 0
    jobs_reported: int = 0
    sources_searched: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
