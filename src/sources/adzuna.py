"""Adzuna API source adapter — requires free API key from developer.adzuna.com."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import requests

from src.models import Job, CandidateProfile, WorkMode, EmploymentType
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)

BASE_URL = "https://api.adzuna.com/v1/api/jobs"

# Adzuna country codes
COUNTRY_CODES = {
    "united states": "us",
    "united kingdom": "gb",
    "germany": "de",
    "france": "fr",
    "netherlands": "nl",
    "canada": "ca",
    "australia": "au",
    "india": "in",
    "spain": "es",
    "italy": "it",
    "switzerland": "ch",
    "austria": "at",
    "sweden": "se",
    "poland": "pl",
    "brazil": "br",
    "singapore": "sg",
    "south africa": "za",
    "new zealand": "nz",
    "belgium": "be",
    "mexico": "mx",
    "ireland": "ie",
}


class AdzunaSource(BaseSource):
    """
    Searches Adzuna job API.
    Requires free API key from https://developer.adzuna.com/
    Free tier: 250 requests/day.
    """

    name = "adzuna"

    def __init__(self, app_id: str = "", app_key: str = ""):
        self.app_id = app_id
        self.app_key = app_key

    def search(
        self,
        profile: CandidateProfile,
        max_results: int = 50,
        hours_old: int = 24,
    ) -> list[Job]:
        if not self.app_id or not self.app_key:
            logger.warning("[adzuna] No API credentials configured. Skipping.")
            return []

        all_jobs: list[Job] = []

        # Map preferred countries to Adzuna country codes
        country_codes = self._get_country_codes(profile)
        search_terms = profile.target_roles[:3] if profile.target_roles else ["software engineer"]

        for country_code in country_codes:
            for term in search_terms:
                try:
                    url = f"{BASE_URL}/{country_code}/search/1"
                    params = {
                        "app_id": self.app_id,
                        "app_key": self.app_key,
                        "what": term,
                        "results_per_page": min(max_results, 50),
                        "max_days_old": max(1, hours_old // 24),
                        "sort_by": "date",
                        "content-type": "application/json",
                    }

                    logger.info(
                        f"[adzuna] Searching '{term}' in {country_code}"
                    )
                    resp = requests.get(url, params=params, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()

                    results = data.get("results", [])
                    for item in results:
                        job = self._parse_job(item, country_code, profile)
                        if job:
                            all_jobs.append(job)

                except requests.HTTPError as e:
                    if e.response and e.response.status_code == 429:
                        logger.warning("[adzuna] Rate limited. Stopping.")
                        return all_jobs
                    logger.warning(f"[adzuna] HTTP error: {e}")
                except Exception as e:
                    logger.warning(f"[adzuna] Error searching {country_code}/{term}: {e}")

        return all_jobs

    def _get_country_codes(self, profile: CandidateProfile) -> list[str]:
        """Map preferred countries to Adzuna country codes."""
        codes = []
        for country in profile.preferred_countries:
            code = COUNTRY_CODES.get(country.lower())
            if code:
                codes.append(code)
        return codes if codes else ["us", "gb"]

    def _parse_job(
        self, item: dict, country_code: str, profile: CandidateProfile
    ) -> Optional[Job]:
        """Parse an Adzuna API result into a Job model."""
        try:
            title = item.get("title", "").strip()

            # Company
            company_data = item.get("company", {})
            company = ""
            if isinstance(company_data, dict):
                company = company_data.get("display_name", "").strip()
            elif isinstance(company_data, str):
                company = company_data.strip()

            if not title or not company:
                return None

            # Location
            location_data = item.get("location", {})
            location_parts = []
            if isinstance(location_data, dict):
                display = location_data.get("display_name", "")
                if display:
                    location_parts.append(display)
                area = location_data.get("area", [])
                if isinstance(area, list) and area:
                    location_parts = area

            location = ", ".join(location_parts) if location_parts else ""

            # Parse city and country
            city = ""
            country = ""
            if location_parts:
                city = location_parts[-1] if len(location_parts) > 1 else ""
                # Reverse map country code
                for name, code in COUNTRY_CODES.items():
                    if code == country_code:
                        country = name.title()
                        break

            # Date
            posted_at = None
            created = item.get("created")
            if created:
                try:
                    posted_at = datetime.fromisoformat(
                        created.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except Exception:
                    pass

            # URL
            apply_url = item.get("redirect_url", item.get("url", ""))

            # Description
            description = item.get("description", "")

            # Salary
            salary = ""
            min_sal = item.get("salary_min")
            max_sal = item.get("salary_max")
            if min_sal and max_sal:
                salary = f"${int(min_sal):,} - ${int(max_sal):,}"

            # Employment type
            emp_type = EmploymentType.FULL_TIME
            contract = item.get("contract_type", "")
            if contract:
                ct = contract.lower()
                if "part" in ct:
                    emp_type = EmploymentType.PART_TIME
                elif "contract" in ct:
                    emp_type = EmploymentType.CONTRACT

            # Category tags
            category = item.get("category", {})
            tags = []
            if isinstance(category, dict):
                cat_label = category.get("label", "")
                if cat_label:
                    tags.append(cat_label)

            return Job(
                company=company,
                title=title,
                location=location,
                country=country,
                city=city,
                work_mode=WorkMode.UNKNOWN,
                employment_type=emp_type,
                posted_at=posted_at,
                discovered_at=datetime.utcnow(),
                source="adzuna",
                application_url=apply_url,
                description=description,
                salary=salary,
                job_id_external=str(item.get("id", "")),
                tags=tags,
            )
        except Exception as e:
            logger.debug(f"[adzuna] Failed to parse job: {e}")
            return None
