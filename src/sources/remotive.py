"""Remotive API source adapter — free, no API key required."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import requests

from src.models import Job, CandidateProfile, WorkMode, EmploymentType
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)

API_URL = "https://remotive.com/api/remote-jobs"

# Remotive category slugs
CATEGORY_MAP = {
    "software": "software-dev",
    "engineer": "software-dev",
    "developer": "software-dev",
    "frontend": "software-dev",
    "backend": "software-dev",
    "full stack": "software-dev",
    "devops": "devops-sysadmin",
    "sysadmin": "devops-sysadmin",
    "data": "data",
    "analyst": "data",
    "data science": "data",
    "machine learning": "data",
    "product": "product",
    "design": "design",
    "marketing": "marketing",
    "sales": "sales",
    "customer": "customer-support",
    "hr": "hr",
    "finance": "finance-legal",
    "qa": "qa",
    "testing": "qa",
    "writing": "writing",
    "project manager": "project-management",
}


class RemotiveSource(BaseSource):
    """Searches Remotive for remote job listings."""

    name = "remotive"

    def search(
        self,
        profile: CandidateProfile,
        max_results: int = 50,
        hours_old: int = 24,
    ) -> list[Job]:
        all_jobs: list[Job] = []
        categories_searched = set()

        # Determine categories from target roles
        categories = self._get_categories(profile)

        for category in categories:
            if category in categories_searched:
                continue
            categories_searched.add(category)

            try:
                params = {"limit": min(max_results, 50)}
                if category:
                    params["category"] = category

                logger.info(f"[remotive] Searching category: {category or 'all'}")
                resp = requests.get(API_URL, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                jobs_data = data.get("jobs", [])
                for item in jobs_data:
                    job = self._parse_job(item, profile)
                    if job:
                        all_jobs.append(job)

            except Exception as e:
                logger.warning(f"[remotive] Error fetching category {category}: {e}")

        # Also do a keyword search if we have specific terms
        for term in profile.target_roles[:2]:
            try:
                params = {"search": term, "limit": 30}
                resp = requests.get(API_URL, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("jobs", []):
                    job = self._parse_job(item, profile)
                    if job:
                        all_jobs.append(job)

            except Exception as e:
                logger.warning(f"[remotive] Error searching term '{term}': {e}")

        # Build accepted-location filter
        accepted: set[str] = set()
        for c in profile.preferred_countries:
            accepted.add(c.lower())
        for c in profile.preferred_cities:
            accepted.add(c.lower())
        # Remote / worldwide posts are always OK
        accepted.update({"remote", "worldwide", "anywhere", "global", ""})

        if accepted - {"", "remote", "worldwide", "anywhere", "global"}:
            # User has country preference — filter strictly
            all_jobs = [
                j for j in all_jobs
                if any(token in j.location.lower() for token in accepted)
            ]

        return all_jobs

    def _get_categories(self, profile: CandidateProfile) -> list[str]:
        """Map target roles to Remotive category slugs."""
        cats = set()
        for role in profile.target_roles + [profile.current_role]:
            role_lower = role.lower()
            for keyword, category in CATEGORY_MAP.items():
                if keyword in role_lower:
                    cats.add(category)
        return list(cats) if cats else ["data"]  # Default to data, not software-dev

    def _parse_job(
        self, item: dict, profile: CandidateProfile
    ) -> Optional[Job]:
        """Parse a Remotive API job item into a Job model."""
        try:
            title = item.get("title", "").strip()
            company = item.get("company_name", "").strip()

            if not title or not company:
                return None

            # Parse location / country
            candidate_region = item.get("candidate_required_location", "")
            location = candidate_region if candidate_region else "Remote"

            # Try to match against preferred countries
            country = ""
            location_lower = location.lower()
            if profile.preferred_countries:
                for c in profile.preferred_countries:
                    if c.lower() in location_lower:
                        country = c
                        break

            # If "Worldwide" or "Anywhere", it's open
            if any(w in location_lower for w in ["worldwide", "anywhere", "global"]):
                country = "Worldwide"

            # Parse date
            posted_at = None
            pub_date = item.get("publication_date")
            if pub_date:
                try:
                    posted_at = datetime.fromisoformat(
                        pub_date.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except Exception:
                    try:
                        posted_at = datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%S")
                    except Exception:
                        pass

            # Parse job type
            job_type_str = item.get("job_type", "").lower()
            emp_type = EmploymentType.FULL_TIME
            if "contract" in job_type_str:
                emp_type = EmploymentType.CONTRACT
            elif "part" in job_type_str:
                emp_type = EmploymentType.PART_TIME
            elif "intern" in job_type_str:
                emp_type = EmploymentType.INTERNSHIP

            # Build application URL
            apply_url = item.get("url", "")

            # Description
            description = item.get("description", "")

            # Salary
            salary = item.get("salary", "")

            # Tags
            tags = item.get("tags", [])

            return Job(
                company=company,
                title=title,
                location=location,
                country=country,
                city="",
                work_mode=WorkMode.REMOTE,
                employment_type=emp_type,
                posted_at=posted_at,
                discovered_at=datetime.utcnow(),
                source="remotive",
                application_url=apply_url,
                description=description,
                salary=salary,
                job_id_external=str(item.get("id", "")),
                tags=tags if isinstance(tags, list) else [],
            )
        except Exception as e:
            logger.debug(f"[remotive] Failed to parse job: {e}")
            return None
