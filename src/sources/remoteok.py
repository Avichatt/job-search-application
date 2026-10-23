"""RemoteOK API source adapter — free, no API key required."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import requests

from src.models import Job, CandidateProfile, WorkMode, EmploymentType
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)

API_URL = "https://remoteok.com/api"


class RemoteOKSource(BaseSource):
    """Searches RemoteOK for remote job listings."""

    name = "remoteok"

    def search(
        self,
        profile: CandidateProfile,
        max_results: int = 50,
        hours_old: int = 24,
    ) -> list[Job]:

        try:
            logger.info("[remoteok] Fetching job feed")
            headers = {
                "User-Agent": "JobSearchAgent/1.0 (personal use)"
            }
            resp = requests.get(API_URL, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # First item is usually metadata/legal notice, skip it
            job_items = data[1:] if len(data) > 1 else data

            all_jobs: list[Job] = []
            for item in job_items:
                job = self._parse_job(item, profile)
                if job:
                    all_jobs.append(job)

            filtered = self._filter_by_location(all_jobs, profile)
            return filtered[:max_results]

        except Exception as e:
            logger.error(f"[remoteok] Failed to fetch jobs: {e}")
            return []

    def _filter_by_location(
        self, jobs: list[Job], profile: CandidateProfile
    ) -> list[Job]:
        """Filter jobs to preferred countries/cities. Worldwide/remote always pass."""
        if not profile.preferred_countries and not profile.preferred_cities:
            return jobs

        accepted: set[str] = set()
        for c in profile.preferred_countries:
            accepted.add(c.lower())
        for c in profile.preferred_cities:
            accepted.add(c.lower())
        # Worldwide / remote posts always pass through
        accepted.update({"remote", "worldwide", "anywhere", "global", ""})

        return [
            j for j in jobs
            if any(token in j.location.lower() for token in accepted)
        ]


    def _parse_job(
        self, item: dict, profile: CandidateProfile
    ) -> Optional[Job]:
        """Parse a RemoteOK JSON item into a Job model."""
        try:
            title = item.get("position", "").strip()
            company = item.get("company", "").strip()

            if not title or not company:
                return None

            # Parse date
            posted_at = None
            epoch = item.get("epoch")
            date_str = item.get("date")
            if epoch:
                try:
                    posted_at = datetime.utcfromtimestamp(int(epoch))
                except Exception:
                    pass
            elif date_str:
                try:
                    posted_at = datetime.fromisoformat(
                        date_str.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except Exception:
                    pass

            # Location
            location_str = item.get("location", "Remote")
            country = ""
            if profile.preferred_countries:
                loc_lower = location_str.lower()
                for c in profile.preferred_countries:
                    if c.lower() in loc_lower:
                        country = c
                        break
            if not country and any(
                w in location_str.lower()
                for w in ["worldwide", "anywhere", "global", "remote"]
            ):
                country = "Worldwide"

            # Application URL
            apply_url = item.get("apply_url", item.get("url", ""))
            if not apply_url:
                slug = item.get("slug", "")
                if slug:
                    apply_url = f"https://remoteok.com/remote-jobs/{slug}"

            # Description
            description = item.get("description", "")

            # Salary
            salary_min = item.get("salary_min")
            salary_max = item.get("salary_max")
            salary = ""
            if salary_min and salary_max:
                salary = f"${int(salary_min):,} - ${int(salary_max):,}"
            elif salary_min:
                salary = f"${int(salary_min):,}+"

            # Tags
            tags = item.get("tags", [])

            return Job(
                company=company,
                title=title,
                location=location_str,
                country=country,
                city="",
                work_mode=WorkMode.REMOTE,
                employment_type=EmploymentType.FULL_TIME,
                posted_at=posted_at,
                discovered_at=datetime.utcnow(),
                source="remoteok",
                application_url=apply_url,
                description=description,
                salary=salary,
                job_id_external=str(item.get("id", "")),
                tags=tags if isinstance(tags, list) else [],
            )
        except Exception as e:
            logger.debug(f"[remoteok] Failed to parse job: {e}")
            return None
