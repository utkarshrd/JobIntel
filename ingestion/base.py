"""
JobIntel - Abstract Job Ingestion Source Provider
Defines the standard interface for job data providers (Jobvetta, Adzuna, etc.).
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseJobSource(ABC):
    """
    Abstract base class for all job API data ingestion sources.
    Ensures modularity and extensibility for new job sources.
    """

    @abstractmethod
    def fetch_jobs(
        self,
        query: str,
        location: str,
        limit: int = 10,
        page: int = 1,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch raw job postings from external API provider.
        Returns a list of raw dictionary records.
        """
        pass

    @abstractmethod
    def validate_record(self, raw_record: Dict[str, Any]) -> bool:
        """
        Check if raw job record has mandatory fields to proceed with normalization.
        """
        pass
