"""Configuration loader for the Job Search Agent."""

from __future__ import annotations

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from src.models import CandidateProfile


# Base directory is the project root (where run_search.py lives)
BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class SmtpConfig:
    server: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_address: str = ""
    to_address: str = ""
    use_tls: bool = True


@dataclass
class AdzunaConfig:
    enabled: bool = False
    app_id: str = ""
    app_key: str = ""


@dataclass
class SourceFlags:
    jobspy: bool = True
    remotive: bool = True
    remoteok: bool = True
    himalayas: bool = True
    arbeitnow: bool = True
    adzuna: bool = False  # Requires API key


@dataclass
class Settings:
    freshness_hours: int = 24
    min_match_score: int = 70
    schedule_interval_hours: int = 4
    max_results_per_source: int = 50
    smtp: SmtpConfig = field(default_factory=SmtpConfig)
    adzuna: AdzunaConfig = field(default_factory=AdzunaConfig)
    sources: SourceFlags = field(default_factory=SourceFlags)
    save_html_reports: bool = True
    reports_dir: str = ""
    data_dir: str = ""
    resume_path: str = ""


def _expand_role_variations(target_roles: list[str]) -> list[str]:
    """Generate common title variations for the target roles."""
    prefixes = ["", "Senior ", "Junior ", "Lead ", "Staff ", "Principal "]
    suffixes_map = {
        "data analyst": [
            "Business Data Analyst", "Product Data Analyst", "BI Analyst",
            "Business Intelligence Analyst", "Analytics Analyst",
            "Reporting Analyst", "Data Analytics Specialist",
        ],
        "data engineer": [
            "Analytics Engineer", "Data Platform Engineer", "ETL Developer",
            "Big Data Engineer", "Data Infrastructure Engineer",
        ],
        "data scientist": [
            "Machine Learning Engineer", "ML Scientist", "Applied Scientist",
            "Research Scientist", "AI Scientist", "Quantitative Analyst",
        ],
        "software engineer": [
            "Software Developer", "Backend Engineer", "Backend Developer",
            "Full Stack Developer", "Full Stack Engineer", "SDE",
            "Application Developer",
        ],
        "frontend developer": [
            "Frontend Engineer", "UI Developer", "UI Engineer",
            "React Developer", "Web Developer",
        ],
        "devops engineer": [
            "Site Reliability Engineer", "SRE", "Platform Engineer",
            "Infrastructure Engineer", "Cloud Engineer",
        ],
        "product manager": [
            "Product Owner", "Technical Product Manager", "Group PM",
        ],
        "project manager": [
            "Program Manager", "Scrum Master", "Delivery Manager",
        ],
    }

    variations = set()
    for role in target_roles:
        variations.add(role)
        role_lower = role.lower().strip()

        # Add prefix variations
        for prefix in prefixes:
            candidate = f"{prefix}{role}".strip()
            if candidate:
                variations.add(candidate)

        # Add domain-specific synonyms
        if role_lower in suffixes_map:
            for syn in suffixes_map[role_lower]:
                variations.add(syn)

    return sorted(variations)


def load_profile(path: Optional[str] = None) -> CandidateProfile:
    """Load the candidate profile from profile.yaml."""
    if path is None:
        path = str(BASE_DIR / "config" / "profile.yaml")

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Profile not found at {path}. "
            "Please create config/profile.yaml from the template."
        )

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    candidate = data.get("candidate", {})

    profile = CandidateProfile(
        total_experience_years=candidate.get("total_experience_years", 0),
        current_role=candidate.get("current_role", ""),
        target_roles=candidate.get("target_roles", []),
        primary_skills=[s.lower() for s in candidate.get("primary_skills", [])],
        secondary_skills=[s.lower() for s in candidate.get("secondary_skills", [])],
        industries=candidate.get("industries", []),
        preferred_countries=[c.lower() for c in candidate.get("preferred_countries", [])],
        preferred_cities=[c.lower() for c in candidate.get("preferred_cities", [])],
        work_preference=candidate.get("work_preference", "any").lower(),
        min_salary=candidate.get("min_salary", ""),
        employment_type=candidate.get("employment_type", "full-time").lower(),
        visa_status=candidate.get("visa_status", ""),
        education=candidate.get("education", []),
        certifications=candidate.get("certifications", []),
        languages=candidate.get("languages", []),
    )

    # Auto-expand search title variations
    manual_variations = candidate.get("search_title_variations", [])
    if manual_variations:
        profile.search_title_variations = manual_variations
    else:
        profile.search_title_variations = _expand_role_variations(profile.target_roles)

    return profile


def load_settings(path: Optional[str] = None) -> Settings:
    """Load application settings from settings.yaml."""
    if path is None:
        path = str(BASE_DIR / "config" / "settings.yaml")

    if not os.path.exists(path):
        # Return defaults if no settings file exists
        settings = Settings()
        settings.reports_dir = str(BASE_DIR / "reports")
        settings.data_dir = str(BASE_DIR / "data")
        settings.resume_path = str(BASE_DIR / "resume")
        return settings

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    smtp_data = data.get("smtp", {})
    smtp = SmtpConfig(
        server=smtp_data.get("server", ""),
        port=smtp_data.get("port", 587),
        username=smtp_data.get("username", ""),
        password=smtp_data.get("password", ""),
        from_address=smtp_data.get("from_address", ""),
        to_address=smtp_data.get("to_address", ""),
        use_tls=smtp_data.get("use_tls", True),
    )

    adzuna_data = data.get("adzuna", {})
    adzuna = AdzunaConfig(
        enabled=adzuna_data.get("enabled", False),
        app_id=adzuna_data.get("app_id", ""),
        app_key=adzuna_data.get("app_key", ""),
    )

    sources_data = data.get("sources", {})
    sources = SourceFlags(
        jobspy=sources_data.get("jobspy", True),
        remotive=sources_data.get("remotive", True),
        remoteok=sources_data.get("remoteok", True),
        himalayas=sources_data.get("himalayas", True),
        arbeitnow=sources_data.get("arbeitnow", True),
        adzuna=sources_data.get("adzuna", False),
    )

    settings = Settings(
        freshness_hours=data.get("freshness_hours", 24),
        min_match_score=data.get("min_match_score", 70),
        schedule_interval_hours=data.get("schedule_interval_hours", 4),
        max_results_per_source=data.get("max_results_per_source", 50),
        smtp=smtp,
        adzuna=adzuna,
        sources=sources,
        save_html_reports=data.get("save_html_reports", True),
        reports_dir=data.get("reports_dir", str(BASE_DIR / "reports")),
        data_dir=data.get("data_dir", str(BASE_DIR / "data")),
        resume_path=data.get("resume_path", str(BASE_DIR / "resume")),
    )

    return settings
