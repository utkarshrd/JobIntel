"""
JobIntel - Jobvetta API Client
Primary data acquisition client for Indian job postings via Jobvetta REST API / Official SDK.
API Reference: https://jobvetta.com/api
"""

from typing import List, Dict, Any, Optional
import os
import jobvetta
from jobvetta import Jobvetta, JobvettaError
from backend.app.core.config import settings
from backend.app.core.logging import logger
from ingestion.base import BaseJobSource


class JobvettaClient(BaseJobSource):
    """
    Client for Jobvetta REST API (https://api.jobvetta.com/v1).
    Utilizes official Jobvetta Python SDK with rate limit tracking & error handling.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or settings.JOBVETTA_API_KEY
        self.base_url = (base_url or settings.JOBVETTA_BASE_URL).rstrip("/")
        self._sdk_client: Optional[Jobvetta] = None

        if self.api_key and self.api_key != "your_jobvetta_api_key_here":
            try:
                self._sdk_client = Jobvetta(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=30.0,
                )
            except Exception as e:
                logger.warning(f"Could not initialize Jobvetta SDK client: {e}")

    def validate_record(self, raw_record: Dict[str, Any]) -> bool:
        """
        Validate that essential fields (job_id, title, company) exist.
        """
        if not isinstance(raw_record, dict):
            return False
        title = raw_record.get("title") or raw_record.get("job_title")
        company = raw_record.get("company") or raw_record.get("company_name")
        return bool(title and company)

    def fetch_jobs(
        self,
        query: str = "Data Analyst",
        location: str = "Mumbai",
        limit: int = 10,
        days: Optional[int] = None,
        fetch_details: bool = True,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Query Jobvetta API for Indian job postings matching query & location.
        Returns a list of raw job records. If fetch_details=True, fetches full description per job_id.
        """
        if not self.api_key or self.api_key == "your_jobvetta_api_key_here":
            logger.warning("JOBVETTA_API_KEY is not set in environment or .env file.")
            return []

        # Ensure SDK client is initialized
        if self._sdk_client is None:
            try:
                self._sdk_client = Jobvetta(api_key=self.api_key, base_url=self.base_url, timeout=30.0)
            except Exception as e:
                logger.error(f"Failed to initialize Jobvetta client: {e}")
                return []

        try:
            search_response = self._sdk_client.search_jobs(
                q=query,
                location=location,
                days=days,
                limit=min(limit, 10),
            )
            jobs_summary = search_response.get("jobs", []) if isinstance(search_response, dict) else []

            if not fetch_details or not jobs_summary:
                return jobs_summary

            detailed_jobs: List[Dict[str, Any]] = []
            for item in jobs_summary:
                job_id = item.get("job_id")
                if job_id:
                    try:
                        detail = self._sdk_client.get_job(job_id)
                        if isinstance(detail, dict):
                            detailed_jobs.append(detail)
                        else:
                            detailed_jobs.append(item)
                    except JobvettaError as e:
                        logger.warning(f"Could not fetch detail for job_id '{job_id}': {e}")
                        detailed_jobs.append(item)
                else:
                    detailed_jobs.append(item)

            return detailed_jobs

        except JobvettaError as e:
            if e.status == 401:
                logger.error(f"Jobvetta 401 Unauthorized: Invalid API key ({e})")
            elif e.status == 429:
                logger.error(f"Jobvetta 429 Rate limit exceeded (50 calls/day): {e}")
            else:
                logger.error(f"Jobvetta API Error (Status {e.status}): {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in JobvettaClient.fetch_jobs: {e}")
            return []

    def fetch_job_detail(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch full details for a specific job_id.
        """
        if not self._sdk_client:
            return None
        try:
            return self._sdk_client.get_job(job_id)
        except Exception as e:
            logger.warning(f"Error fetching job details for {job_id}: {e}")
            return None
