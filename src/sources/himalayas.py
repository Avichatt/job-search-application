"""Himalayas API source adapter — free, no API key required."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import requests

from src.models import Job, CandidateProfile, WorkMode, EmploymentType
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)

API_URL = "https://himalayas.app/jobs/api"


class HimalayasSource(BaseSource):
    """Searches Himalayas for remote and global job listings."""

    name = "himalayas"

    def search(
        self,
        profile: CandidateProfile,
        max_results: int = 50,
        hours_old: int = 24,
    ) -> list[Job]:
        all_jobs: list[Job] = []

        try:
            logger.info("[himalayas] Fetching job feed")
            params = {
                "limit": min(max_results, 100),
            }

            resp = requests.get(API_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            job_items = data.get("jobs", data) if isinstance(data, dict) else data
            if not isinstance(job_items, list):
                job_items = []

            for item in job_items:
                job = self._parse_job(item, profile)
                if job:
                    all_jobs.append(job)

        except Exception as e:
            logger.error(f"[himalayas] Failed to fetch jobs: {e}")

        return all_jobs[:max_results]

    def _parse_job(
        self, item: dict, profile: CandidateProfile
    ) -> Optional[Job]:
        """Parse a Himalayas API job item into a Job model."""
        try:
            title = item.get("title", "").strip()
            company_name = ""

            # Company can be nested or flat
            company_data = item.get("company", item.get("companyName", ""))
            if isinstance(company_data, dict):
                company_name = company_data.get("name", "").strip()
            elif isinstance(company_data, str):
                company_name = company_data.strip()

            if not title or not company_name:
                return None

            # Location
            location = item.get("location", "Remote")
            country = item.get("country", "")
            city = item.get("city", "")

            # Filter by country if needed
            if profile.preferred_countries and country:
                country_lower = country.lower()
                if not any(c.lower() == country_lower for c in profile.preferred_countries):
                    # Check if it's remote / worldwide
                    loc_lower = location.lower() if location else ""
                    if not any(w in loc_lower for w in ["remote", "worldwide", "anywhere"]):
                        return None

            # Parse date
            posted_at = None
            pub_raw = item.get("pubDate", item.get("publishedAt", item.get("created_at", "")))
            if isinstance(pub_raw, (int, float)):
                try:
                    posted_at = datetime.utcfromtimestamp(pub_raw)
                except Exception:
                    pass
            elif isinstance(pub_raw, str) and pub_raw.strip():
                for fmt in [
                    "%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d",
                ]:
                    try:
                        posted_at = datetime.strptime(pub_raw, fmt)
                        break
                    except ValueError:
                        continue

            # Work mode
            work_mode = WorkMode.REMOTE  # Himalayas is primarily remote
            location_type = str(item.get("locationType", "")).lower()
            if "hybrid" in location_type:
                work_mode = WorkMode.HYBRID
            elif "onsite" in location_type or "office" in location_type:
                work_mode = WorkMode.ONSITE

            # Employment type
            emp_str = str(item.get("employmentType", item.get("type", ""))).lower()
            emp_type = EmploymentType.FULL_TIME
            if "contract" in emp_str:
                emp_type = EmploymentType.CONTRACT
            elif "part" in emp_str:
                emp_type = EmploymentType.PART_TIME

            # URL
            apply_url = item.get("applicationLink", item.get("applicationUrl", item.get("url", "")))
            if not apply_url:
                slug = item.get("slug", "")
                if slug:
                    apply_url = f"https://himalayas.app/jobs/{slug}"

            # Description
            description = item.get("description", item.get("excerpt", ""))

            # Salary
            salary = ""
            min_sal = item.get("minSalary", item.get("salaryMin"))
            max_sal = item.get("maxSalary", item.get("salaryMax"))
            currency = item.get("salaryCurrency", "USD")
            if min_sal and max_sal:
                salary = f"{currency} {int(min_sal):,} - {int(max_sal):,}"

            # Categories/tags
            tags = item.get("categories", item.get("tags", []))
            if isinstance(tags, str):
                tags = [tags]

            # Seniority
            seniority = item.get("seniority", "")
            if seniority and isinstance(tags, list):
                tags.append(seniority)

            return Job(
                company=company_name,
                title=title,
                location=location or "Remote",
                country=country,
                city=city if isinstance(city, str) else "",
                work_mode=work_mode,
                employment_type=emp_type,
                posted_at=posted_at,
                discovered_at=datetime.utcnow(),
                source="himalayas",
                application_url=apply_url,
                description=description,
                salary=salary,
                job_id_external=str(item.get("id", "")),
                tags=tags if isinstance(tags, list) else [],
            )
        except Exception as e:
            logger.debug(f"[himalayas] Failed to parse job: {e}")
            return None
