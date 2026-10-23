"""Jobicy API source adapter — free remote jobs API with direct ATS & employer links."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import requests

from src.models import Job, CandidateProfile, WorkMode, EmploymentType
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)

API_URL = "https://jobicy.com/api/v2/remote-jobs"


class JobicySource(BaseSource):
    """Searches Jobicy for global remote tech and engineering positions."""

    name = "jobicy"

    def search(
        self,
        profile: CandidateProfile,
        max_results: int = 50,
        hours_old: int = 72,
    ) -> list[Job]:
        all_jobs: list[Job] = []
        tags = profile.primary_skills or ["python", "software"]

        for tag in tags[:3]:
            if len(all_jobs) >= max_results:
                break
            try:
                params = {"count": 25, "tag": tag.lower()}
                logger.info(f"[jobicy] Fetching tag: {tag}")
                resp = requests.get(API_URL, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                items = data.get("jobs", [])
                for item in items:
                    job = self._parse_job(item, profile)
                    if job:
                        all_jobs.append(job)

            except Exception as e:
                logger.warning(f"[jobicy] Error fetching tag '{tag}': {e}")

        logger.info(f"[jobicy] Found {len(all_jobs)} jobs.")

        # Post-search location filter
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

    def _parse_job(self, item: dict, profile: CandidateProfile) -> Optional[Job]:
        try:
            title = item.get("jobTitle", "").strip()
            company = item.get("companyName", "").strip()
            if not title or not company:
                return None

            location = item.get("jobGeo", "Remote")
            apply_url = item.get("url", "")
            salary = ""
            if item.get("annualSalaryMin") and item.get("annualSalaryMax"):
                salary = f"${item.get('annualSalaryMin'):,} - ${item.get('annualSalaryMax'):,} {item.get('salaryCurrency', 'USD')}"

            # Parse date
            posted_at = None
            pub_date = item.get("pubDate")
            if pub_date:
                try:
                    posted_at = datetime.fromisoformat(pub_date.replace("Z", "+00:00")).replace(tzinfo=None)
                except Exception:
                    try:
                        posted_at = datetime.strptime(pub_date, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        posted_at = datetime.utcnow()

            return Job(
                company=company,
                title=title,
                location=location,
                country=location if "remote" not in location.lower() else "Worldwide",
                city="",
                work_mode=WorkMode.REMOTE,
                employment_type=EmploymentType.FULL_TIME,
                posted_at=posted_at,
                discovered_at=datetime.utcnow(),
                source="jobicy",
                application_url=apply_url,
                description=item.get("jobExcerpt", ""),
                salary=salary,
                freshness_verified=True,
            )
        except Exception:
            return None
