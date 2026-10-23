"""Direct LinkedIn source adapter — searches LinkedIn's guest jobs endpoint with <24h filter and multi-page pagination."""

from __future__ import annotations

import logging
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.models import Job, CandidateProfile, WorkMode, EmploymentType
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)

BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _location_accepted(job_location: str, accepted: set[str]) -> bool:
    """Return True if job_location contains any accepted country/city substring."""
    loc_lower = job_location.lower()
    return any(token in loc_lower for token in accepted)


class LinkedInSource(BaseSource):
    """
    Direct LinkedIn job search adapter using LinkedIn's public guest endpoint.
    Filters strictly for fresh postings within the given hours window.
    Features multi-page pagination and multi-city Indian tech hub scanning.
    """

    name = "linkedin"

    def search(
        self,
        profile: CandidateProfile,
        max_results: int = 100,
        hours_old: int = 48,
    ) -> list[Job]:
        all_jobs: list[Job] = []

        # Determine target search titles
        search_terms = profile.target_roles or [profile.current_role or "Data Analyst"]
        if profile.search_title_variations:
            # Combine without duplicates
            for var in profile.search_title_variations:
                if var not in search_terms:
                    search_terms.append(var)

        # Build locations from preferred cities first, then fall back to countries.
        locations: list[str] = []
        if profile.preferred_cities:
            locations = [c for c in profile.preferred_cities if c.lower() != "remote"]
        if not locations and profile.preferred_countries:
            locations = list(profile.preferred_countries)
        if not locations:
            locations = ["India", "Bengaluru", "Hyderabad", "Pune", "Mumbai", "Gurgaon"]

        # If user wants India, ensure top hubs are included
        is_india_targeted = any("india" in c.lower() for c in profile.preferred_countries)
        if is_india_targeted:
            for top_hub in ["India", "Bengaluru", "Hyderabad", "Pune", "Mumbai", "Gurgaon", "Delhi NCR", "Chennai", "Kolkata"]:
                if top_hub not in locations:
                    locations.append(top_hub)

        # Only add a global Remote search when the user has NO country preference
        if profile.work_preference in ("remote", "any") and not profile.preferred_countries:
            locations = ["Remote"] + [l for l in locations if l.lower() != "remote"]

        # Build a set of accepted location tokens for post-search filtering
        accepted_locations: set[str] = set()
        for c in profile.preferred_countries:
            accepted_locations.add(c.lower())
        for c in profile.preferred_cities:
            accepted_locations.add(c.lower())
        # Add common Indian cities and sub-regions
        if is_india_targeted:
            accepted_locations.update({
                "india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai",
                "gurgaon", "gurugram", "noida", "delhi", "chennai", "kolkata",
                "ahmedabad", "chandigarh", "jaipur", "remote", "worldwide", "anywhere"
            })
        elif profile.preferred_countries:
            accepted_locations.update({"remote", "worldwide", "anywhere"})

        # Iterate through target titles and locations
        for term in search_terms[:6]:  # Top 6 role titles
            for loc in locations[:6]:  # Top 6 locations/hubs
                if len(all_jobs) >= max_results:
                    break

                try:
                    # Fetch up to 50 jobs per (term, loc) using pagination (pages 0 and 25)
                    jobs = self._search_linkedin_paginated(
                        keywords=term,
                        location=loc,
                        hours_old=hours_old,
                        max_pages=2,
                        page_size=25,
                    )
                    # Post-search filter: keep only India / preferred-location jobs
                    if accepted_locations:
                        jobs = [
                            j for j in jobs
                            if _location_accepted(j.location, accepted_locations)
                        ]
                    all_jobs.extend(jobs)
                except Exception as e:
                    logger.warning(f"[linkedin] Search failed for '{term}' in '{loc}': {e}")

        logger.info(f"[linkedin] Found {len(all_jobs)} raw jobs matching criteria.")

        # Deduplicate by (title, company)
        seen: set[tuple[str, str]] = set()
        unique_jobs: list[Job] = []
        for j in all_jobs:
            key = (j.title.lower().strip(), j.company.lower().strip())
            if key not in seen:
                seen.add(key)
                unique_jobs.append(j)

        return unique_jobs[:max_results]

    def _search_linkedin_paginated(
        self,
        keywords: str,
        location: str,
        hours_old: int = 48,
        max_pages: int = 2,
        page_size: int = 25,
    ) -> list[Job]:
        """Fetch multiple pages of search results from LinkedIn guest endpoint."""
        collected: list[Job] = []

        for page in range(max_pages):
            start = page * page_size
            page_jobs = self._search_linkedin_single(
                keywords=keywords,
                location=location,
                hours_old=hours_old,
                start=start,
                limit=page_size,
            )
            if not page_jobs:
                break
            collected.extend(page_jobs)
            # Brief sleep to be polite to the guest endpoint
            time.sleep(0.3)

        return collected

    def _search_linkedin_single(
        self,
        keywords: str,
        location: str,
        hours_old: int = 48,
        start: int = 0,
        limit: int = 25,
    ) -> list[Job]:
        """Query single page of LinkedIn search endpoint."""
        seconds = max(3600, hours_old * 3600)
        time_filter = f"r{seconds}"

        params = {
            "keywords": keywords,
            "location": location,
            "f_TPR": time_filter,
            "start": start,
        }

        # If location is Remote, add LinkedIn's remote filter f_WT=2
        if location.lower() == "remote":
            params["f_WT"] = "2"
            params["location"] = "Worldwide"

        url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
        logger.debug(f"[linkedin] Fetching start={start}: {keywords} in {location} (<{hours_old}h)")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                logger.debug(f"[linkedin] HTTP {resp.status_code} for {url}")
                return []
        except Exception as e:
            logger.debug(f"[linkedin] Request error: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.find_all("div", class_="base-card")
        if not cards:
            cards = soup.find_all("li")

        jobs: list[Job] = []
        now = datetime.utcnow()

        for card in cards:
            try:
                title_tag = card.find(["h3", "a"], class_=lambda c: c and "title" in c)
                company_tag = card.find(["h4", "a"], class_=lambda c: c and ("subtitle" in c or "company" in c))
                loc_tag = card.find("span", class_=lambda c: c and "location" in c)
                link_tag = card.find("a", class_=lambda c: c and ("link" in c or "title" in c))
                time_tag = card.find("time")

                title = title_tag.text.strip() if title_tag else ""
                company = company_tag.text.strip() if company_tag else ""
                job_location = loc_tag.text.strip() if loc_tag else location
                apply_url = link_tag.get("href", "") if link_tag else ""

                if not title or not company:
                    continue

                # Clean up apply URL
                if apply_url and "?" in apply_url:
                    apply_url = apply_url.split("?")[0]

                posted_at = None
                if time_tag and "datetime" in time_tag.attrs:
                    try:
                        posted_at = datetime.fromisoformat(time_tag["datetime"])
                    except Exception:
                        posted_at = now - timedelta(hours=2)
                else:
                    posted_at = now - timedelta(hours=3)

                work_mode = (
                    WorkMode.REMOTE
                    if "remote" in job_location.lower() or location.lower() == "remote"
                    else WorkMode.UNKNOWN
                )

                job = Job(
                    company=company,
                    title=title,
                    location=job_location,
                    country=location if location.lower() != "remote" else "",
                    city="",
                    work_mode=work_mode,
                    employment_type=EmploymentType.FULL_TIME,
                    posted_at=posted_at,
                    discovered_at=now,
                    source="linkedin",
                    application_url=apply_url,
                    description=f"{title} at {company} in {job_location}",
                    freshness_verified=True,
                )
                jobs.append(job)

                if len(jobs) >= limit:
                    break

            except Exception as e:
                logger.debug(f"[linkedin] Error parsing card: {e}")
                continue

        return jobs
