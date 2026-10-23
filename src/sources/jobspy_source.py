"""JobSpy source adapter — searches LinkedIn, Indeed, Glassdoor, Google Jobs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from src.models import Job, CandidateProfile, WorkMode, EmploymentType
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)

# Country code mappings for JobSpy
COUNTRY_CODES = {
    "united states": "USA",
    "united kingdom": "UK",
    "germany": "Germany",
    "canada": "Canada",
    "france": "France",
    "netherlands": "Netherlands",
    "australia": "Australia",
    "india": "India",
    "spain": "Spain",
    "italy": "Italy",
    "switzerland": "Switzerland",
    "austria": "Austria",
    "sweden": "Sweden",
    "norway": "Norway",
    "denmark": "Denmark",
    "finland": "Finland",
    "ireland": "Ireland",
    "belgium": "Belgium",
    "poland": "Poland",
    "portugal": "Portugal",
    "singapore": "Singapore",
    "japan": "Japan",
    "south korea": "South Korea",
    "brazil": "Brazil",
    "mexico": "Mexico",
    "argentina": "Argentina",
    "new zealand": "New Zealand",
    "israel": "Israel",
    "uae": "UAE",
    "united arab emirates": "UAE",
}


class JobSpySource(BaseSource):
    """
    Searches LinkedIn, Indeed, Glassdoor, and Google Jobs via the
    python-jobspy library (open-source scraper).
    """

    name = "jobspy"

    def __init__(self, sites: Optional[list[str]] = None):
        self.sites = sites or ["indeed", "linkedin", "glassdoor", "google"]

    def search(
        self,
        profile: CandidateProfile,
        max_results: int = 50,
        hours_old: int = 24,
    ) -> list[Job]:
        try:
            from jobspy import scrape_jobs
        except ImportError:
            logger.error("python-jobspy not installed. Run: pip install python-jobspy")
            return []

        all_jobs: list[Job] = []

        # Determine search locations
        search_locations = self._build_locations(profile)
        search_terms = self._build_search_terms(profile)

        for term in search_terms[:5]:  # Limit to top 5 variations
            for location, country_code in search_locations[:3]:  # Limit locations
                try:
                    logger.info(
                        f"[jobspy] Searching '{term}' in {location} "
                        f"({', '.join(self.sites)})"
                    )

                    kwargs = {
                        "site_name": self.sites,
                        "search_term": term,
                        "location": location,
                        "results_wanted": min(max_results, 25),
                        "hours_old": hours_old,
                    }

                    if country_code:
                        kwargs["country_indeed"] = country_code

                    df = scrape_jobs(**kwargs)

                    if df is None or df.empty:
                        continue

                    for _, row in df.iterrows():
                        job = self._row_to_job(row)
                        if job:
                            all_jobs.append(job)

                except Exception as e:
                    logger.warning(f"[jobspy] Error searching '{term}' in {location}: {e}")
                    continue

        # Build accepted-location filter set for post-search filtering
        accepted: set[str] = set()
        for c in profile.preferred_countries:
            accepted.add(c.lower())
        for c in profile.preferred_cities:
            accepted.add(c.lower())
        # Remote/worldwide jobs are acceptable even when country is specified
        if profile.preferred_countries:
            accepted.update({"remote", "worldwide", "anywhere"})

        # Filter results to preferred countries/cities
        if accepted:
            all_jobs = [
                j for j in all_jobs
                if not j.country
                or any(token in (j.country + " " + j.location).lower() for token in accepted)
            ]

        return all_jobs

    def _build_locations(
        self, profile: CandidateProfile
    ) -> list[tuple[str, str]]:
        """Build location + country code pairs for search."""
        locations = []

        # Prefer specific cities
        if profile.preferred_cities:
            for city in profile.preferred_cities:
                country_code = ""
                for country in profile.preferred_countries:
                    cc = COUNTRY_CODES.get(country.lower(), "")
                    if cc:
                        country_code = cc
                        break
                locations.append((city, country_code))

        # Fall back to countries
        if not locations and profile.preferred_countries:
            for country in profile.preferred_countries:
                cc = COUNTRY_CODES.get(country.lower(), country)
                locations.append((country, cc))

        # Ultimate fallback
        if not locations:
            locations = [("", "")]

        return locations

    def _build_search_terms(self, profile: CandidateProfile) -> list[str]:
        """Build search terms from target roles."""
        terms = []
        if profile.target_roles:
            terms.extend(profile.target_roles)
        elif profile.current_role:
            terms.append(profile.current_role)
        else:
            terms.append("data analyst")  # Sensible generic fallback
        return terms

    def _row_to_job(self, row) -> Optional[Job]:
        """Convert a JobSpy DataFrame row to a Job model."""
        try:
            title = str(row.get("title", "")).strip()
            company = str(row.get("company_name", row.get("company", ""))).strip()

            if not title or not company:
                return None

            # Parse work mode
            work_mode = WorkMode.UNKNOWN
            is_remote = row.get("is_remote", False)
            if is_remote:
                work_mode = WorkMode.REMOTE

            # Parse location
            location = str(row.get("location", "")).strip()
            city = str(row.get("city", "")).strip() if "city" in row.index else ""
            country = str(row.get("country", "")).strip() if "country" in row.index else ""

            # Parse posted date
            posted_at = None
            date_posted = row.get("date_posted")
            if date_posted is not None:
                try:
                    if hasattr(date_posted, 'to_pydatetime'):
                        posted_at = date_posted.to_pydatetime()
                    elif isinstance(date_posted, str):
                        posted_at = datetime.fromisoformat(date_posted.replace("Z", "+00:00")).replace(tzinfo=None)
                    elif isinstance(date_posted, datetime):
                        posted_at = date_posted.replace(tzinfo=None)
                except Exception:
                    pass

            # Parse job URL
            apply_url = str(row.get("job_url", row.get("link", ""))).strip()

            # Parse description
            description = str(row.get("description", "")).strip()

            # Parse salary
            salary = ""
            min_amount = row.get("min_amount")
            max_amount = row.get("max_amount")
            currency = row.get("currency", "")
            if min_amount and max_amount:
                salary = f"{currency}{min_amount:,.0f} - {currency}{max_amount:,.0f}"
            elif min_amount:
                salary = f"{currency}{min_amount:,.0f}+"

            # Determine source site
            source = str(row.get("site", "jobspy")).strip()

            return Job(
                company=company,
                title=title,
                location=location,
                country=country,
                city=city,
                work_mode=work_mode,
                employment_type=EmploymentType.FULL_TIME,
                posted_at=posted_at,
                discovered_at=datetime.utcnow(),
                source=f"jobspy/{source}",
                application_url=apply_url,
                description=description,
                salary=salary,
                job_id_external=str(row.get("id", "")),
            )
        except Exception as e:
            logger.debug(f"[jobspy] Failed to parse row: {e}")
            return None
