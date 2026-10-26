"""
JobIntel - Greenhouse and Lever public job-board clients (keyless, one board per company).

Both APIs are public and unauthenticated; they return a company's COMPLETE current listing with the full
description, so (unlike Adzuna snippets) skills and experience can be extracted from the whole posting.
Verified endpoints:
  Greenhouse  GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
  Lever       GET https://api.lever.co/v0/postings/{token}?mode=json
No published rate limits exist, so the clients are polite: one request per board, a descriptive User-Agent,
and a pause between boards in the runner.
"""

import re
from typing import Any, Dict, List

import httpx

from ingestion.base import BaseJobSource

USER_AGENT = "JobIntel/0.1 (academic project; public job-board reader)"
INDIA_MARKERS = ("india", "bengaluru", "bangalore", "mumbai", "pune", "hyderabad", "delhi", "gurgaon", "gurugram",
                 "noida", "chennai", "kolkata", "ahmedabad", "kochi", "jaipur", "indore", "chandigarh", "coimbatore")


def is_india_location(*locations: str) -> bool:
    text = " ".join(l for l in locations if l).lower()
    return any(re.search(r"(?<![a-z])" + m + r"(?![a-z])", text) for m in INDIA_MARKERS)


class _BoardClient(BaseJobSource):
    timeout = 60.0

    def validate_record(self, raw_record: Dict[str, Any]) -> bool:
        return isinstance(raw_record, dict) and bool(raw_record.get("id"))

    def _get(self, url: str, params: Dict[str, Any] = None):
        with httpx.Client(timeout=self.timeout, headers={"User-Agent": USER_AGENT}) as client:
            return client.get(url, params=params)

    def fetch_jobs(self, query: str, location: str = "", limit: int = 0, page: int = 1, **kw) -> List[Dict[str, Any]]:
        """`query` is the company board token. Returns ALL postings of the board (no paging exists)."""
        return self.fetch_board(query)

    def fetch_board(self, token: str) -> List[Dict[str, Any]]:
        raise NotImplementedError


class GreenhouseClient(_BoardClient):
    def fetch_board(self, token: str) -> List[Dict[str, Any]]:
        res = self._get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", {"content": "true"})
        res.raise_for_status()
        return [j for j in res.json().get("jobs", []) if self.validate_record(j)]


class LeverClient(_BoardClient):
    def fetch_board(self, token: str) -> List[Dict[str, Any]]:
        res = self._get(f"https://api.lever.co/v0/postings/{token}", {"mode": "json"})
        res.raise_for_status()
        data = res.json()
        return [j for j in data if self.validate_record(j)] if isinstance(data, list) else []
