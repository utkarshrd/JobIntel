"""
JobIntel - Adzuna Jobs Client
Client for querying Indian job postings via the Adzuna API (https://developer.adzuna.com).

Adzuna's published default limits (terms of service): 25 hits/minute, 250/day, 1,000/week, 2,500/month.
The live runner enforces a per-run call budget and a per-minute throttle; this client only does one request
per call (with a small retry on 429/5xx), and never loops by itself.
"""

import time
from typing import Any, Dict, List, Optional

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from ingestion.base import BaseJobSource

MAX_PER_PAGE = 50  # verified: results_per_page=50 returns 50 results


class AdzunaClient(BaseJobSource):
    """Adzuna search client; authenticates with app_id/app_key query params."""

    def __init__(self, app_id: Optional[str] = None, app_key: Optional[str] = None, country: Optional[str] = None):
        self.app_id = app_id or settings.ADZUNA_APP_ID
        self.app_key = app_key or settings.ADZUNA_APP_KEY
        self.country = (country or settings.ADZUNA_COUNTRY or "in").lower()
        self.base_url = "https://api.adzuna.com/v1/api/jobs"
        self.timeout = 25.0
        self.calls_made = 0   # HTTP requests issued by this instance (retries included)

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.app_key)

    def validate_record(self, raw_record: Dict[str, Any]) -> bool:
        return isinstance(raw_record, dict) and bool(raw_record.get("title")) and bool(raw_record.get("id"))

    def fetch_page(self, query: str, location: str, page: int = 1, per_page: int = MAX_PER_PAGE,
                   max_retries: int = 2) -> Dict[str, Any]:
        """One search page. Returns Adzuna's JSON ({'count': total matches, 'results': [...]})."""
        params = {"app_id": self.app_id, "app_key": self.app_key, "what": query, "where": location,
                  "results_per_page": min(per_page, MAX_PER_PAGE), "content-type": "application/json"}
        url = f"{self.base_url}/{self.country}/search/{page}"
        for attempt in range(max_retries + 1):
            self.calls_made += 1
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url, params=params)
            if res.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                wait = 5 * (attempt + 1)
                logger.warning(f"Adzuna HTTP {res.status_code}; retrying in {wait}s")
                time.sleep(wait)
                continue
            res.raise_for_status()
            return res.json()
        raise RuntimeError("unreachable")

    def fetch_jobs(self, query: str, location: str, limit: int = 10, page: int = 1, **kwargs) -> List[Dict[str, Any]]:
        data = self.fetch_page(query, location, page, limit)
        results = data.get("results", [])
        logger.info(f"Adzuna returned {len(results)} records for '{query}' in '{location}'")
        return [r for r in results if self.validate_record(r)]
