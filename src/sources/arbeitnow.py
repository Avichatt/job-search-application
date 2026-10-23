"""Arbeitnow API source adapter — free, no API key, EU/UK focus."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import requests

from src.models import Job, CandidateProfile, WorkMode, EmploymentType
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)

API_URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowSource(BaseSource):
    """
    Searches Arbeitnow for job listings.
    Strong coverage for EU/UK, pulls from ATS systems
    (Greenhouse, Lever, Ashby, etc.).
    """

    name = "arbeitnow"

    def search(
        self,
        profile: CandidateProfile,
        max_results: int = 50,
        hours_old: int = 24,
    ) -> list[Job]:
        all_jobs: list[Job] = []
        page = 1
        max_pages = 3

        while page <= max_pages and len(all_jobs) < max_results:
            try:
                logger.info(f"[arbeitnow] Fetching page {page}")
                resp = requests.get(
                    API_URL,
                    params={"page": page},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()

                job_items = data.get("data", [])
                if not job_items:
                    break

                for item in job_items:
                    job = self._parse_job(item, profile)
                    if job:
                        all_jobs.append(job)

                # Check for next page
                links = data.get("links", {})
                if not links.get("next"):
                    break

                page += 1

            except Exception as e:
                logger.warning(f"[arbeitnow] Error on page {page}: {e}")
                break

        # Filter results to preferred countries/cities
        accepted: set[str] = set()
        for c in profile.preferred_countries:
            accepted.add(c.lower())
        for c in profile.preferred_cities:
            accepted.add(c.lower())
        if profile.preferred_countries:
            accepted.update({"remote", "worldwide", "anywhere"})

        if accepted:
            all_jobs = [
                j for j in all_jobs
                if any(token in (j.country + " " + j.location).lower() for token in accepted)
            ]

        return all_jobs[:max_results]

    def _parse_job(
        self, item: dict, profile: CandidateProfile
    ) -> Optional[Job]:
        """Parse an Arbeitnow API job item into a Job model."""
        try:
            title = item.get("title", "").strip()
            company = item.get("company_name", "").strip()

            if not title or not company:
                return None

            # Location
            location = item.get("location", "").strip()
            country = ""
            city = ""

            # Try to extract country
            if location:
                # Arbeitnow locations are typically "City, Country"
                parts = [p.strip() for p in location.split(",")]
                if len(parts) >= 2:
                    city = parts[0]
                    country = parts[-1]
                elif len(parts) == 1:
                    country = parts[0]

            # Country filtering
            if profile.preferred_countries and country:
                country_lower = country.lower()
                matched_country = False
                for c in profile.preferred_countries:
                    if c.lower() in country_lower or country_lower in c.lower():
                        matched_country = True
                        country = c
                        break

                # Check remote
                remote_flag = item.get("remote", False)
                if not matched_country and not remote_flag:
                    return None

            # Remote flag
            work_mode = WorkMode.ONSITE
            if item.get("remote", False):
                work_mode = WorkMode.REMOTE

            # Posted date
            posted_at = None
            created_at = item.get("created_at")
            if created_at:
                try:
                    # Unix timestamp
                    if isinstance(created_at, (int, float)):
                        posted_at = datetime.utcfromtimestamp(created_at)
                    elif isinstance(created_at, str):
                        # Try ISO format
                        posted_at = datetime.fromisoformat(
                            created_at.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                except Exception:
                    pass

            # Employment type
            emp_type = EmploymentType.FULL_TIME
            tags = item.get("tags", [])
            if isinstance(tags, list):
                tags_lower = [t.lower() for t in tags if isinstance(t, str)]
                if "part-time" in tags_lower:
                    emp_type = EmploymentType.PART_TIME
                elif "contract" in tags_lower or "freelance" in tags_lower:
                    emp_type = EmploymentType.CONTRACT
                elif "internship" in tags_lower:
                    emp_type = EmploymentType.INTERNSHIP

            # URL
            apply_url = item.get("url", "")

            # Description
            description = item.get("description", "")

            return Job(
                company=company,
                title=title,
                location=location,
                country=country,
                city=city,
                work_mode=work_mode,
                employment_type=emp_type,
                posted_at=posted_at,
                discovered_at=datetime.utcnow(),
                source="arbeitnow",
                application_url=apply_url,
                description=description,
                salary="",
                job_id_external=str(item.get("slug", "")),
                tags=tags if isinstance(tags, list) else [],
            )
        except Exception as e:
            logger.debug(f"[arbeitnow] Failed to parse job: {e}")
            return None
