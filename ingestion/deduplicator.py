"""
JobIntel - Job Posting Deduplication
Generates deterministic content hashes to avoid duplicate listings across sources.
"""

import hashlib
from typing import Optional


class Deduplicator:
    @staticmethod
    def generate_job_hash(
        title: str,
        company_name: str,
        location: Optional[str] = None,
        description: Optional[str] = None
    ) -> str:
        """
        Generate a unique deterministic MD5 hash for a job posting.
        Helps identify duplicate postings even if external ID changes or comes from another source.
        """
        norm_title = (title or "").strip().lower()
        norm_company = (company_name or "").strip().lower()
        norm_location = (location or "").strip().lower()
        # Take first 300 chars of description to capture role signature
        norm_desc_prefix = (description or "")[:300].strip().lower()

        composite = f"{norm_title}|{norm_company}|{norm_location}|{norm_desc_prefix}"
        return hashlib.md5(composite.encode("utf-8")).hexdigest()
