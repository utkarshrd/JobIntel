"""
JobIntel - IndianAPI Jobs Client
Client for querying real-time Indian job postings via IndianAPI (https://jobs.indianapi.in).
"""

from typing import List, Dict, Any, Optional
import httpx
from backend.app.core.config import settings
from backend.app.core.logging import logger
from ingestion.base import BaseJobSource


class IndianAPIClient(BaseJobSource):
    """
    Client for IndianAPI Jobs (https://jobs.indianapi.in/jobs).
    Uses 'x-api-key' header for authentication.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or settings.INDIANAPI_KEY
        self.base_url = (base_url or settings.INDIANAPI_BASE_URL).rstrip("/")
        self.timeout = 25.0

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "JobIntel-TWSMA-Research/1.0",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def validate_record(self, raw_record: Dict[str, Any]) -> bool:
        """
        Validate that mandatory fields exist.
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
        experience: Optional[str] = None,
        job_type: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Query IndianAPI Jobs endpoint for matching postings.
        """
        if not self.api_key or self.api_key == "your_indianapi_key_here":
            logger.warning("INDIANAPI_KEY is not set in environment or .env file.")
            return []

        endpoint = f"{self.base_url}/jobs"
        params: Dict[str, Any] = {
            "title": query,
            "location": location,
            "limit": limit,
            **kwargs,
        }
        if experience:
            params["experience"] = experience
        if job_type:
            params["job_type"] = job_type

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    endpoint,
                    headers=self._get_headers(),
                    params=params,
                )

                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict):
                        return data.get("jobs") or data.get("data") or data.get("results") or []
                    return []
                elif response.status_code == 401 or response.status_code == 403:
                    logger.error(f"IndianAPI 401/403 Unauthorized: Invalid API key ({response.text})")
                    return []
                elif response.status_code == 429:
                    logger.error(f"IndianAPI 429 Rate Limit Reached: {response.text}")
                    return []
                else:
                    logger.error(f"IndianAPI Error (Status {response.status_code}): {response.text}")
                    return []

        except httpx.RequestError as e:
            logger.error(f"Network error querying IndianAPI: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in IndianAPIClient: {e}")
            return []
