"""Abstract base class for all job source adapters."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from src.models import Job, CandidateProfile


logger = logging.getLogger(__name__)


class BaseSource(ABC):
    """
    Abstract base class for job source adapters.

    Every source adapter must implement `search()` which returns
    a list of normalized Job objects.
    """

    name: str = "base"

    @abstractmethod
    def search(
        self,
        profile: CandidateProfile,
        max_results: int = 50,
        hours_old: int = 24,
    ) -> list[Job]:
        """
        Search for jobs matching the candidate's profile.

        Args:
            profile: The candidate's job search profile.
            max_results: Maximum number of results to return.
            hours_old: Only return jobs posted within this many hours.

        Returns:
            List of Job objects, normalized to the common schema.
        """
        ...

    def safe_search(
        self,
        profile: CandidateProfile,
        max_results: int = 50,
        hours_old: int = 24,
    ) -> list[Job]:
        """
        Wraps search() with error handling for graceful degradation.
        If the source fails, logs the error and returns an empty list.
        """
        try:
            jobs = self.search(profile, max_results, hours_old)
            logger.info(f"[{self.name}] Found {len(jobs)} jobs")
            return jobs
        except Exception as e:
            logger.error(f"[{self.name}] Search failed: {e}", exc_info=True)
            return []
