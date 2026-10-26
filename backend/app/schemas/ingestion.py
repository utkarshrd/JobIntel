"""
JobIntel - Pydantic Schemas for Ingestion Monitoring & Triggers
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from datetime import datetime


class IngestionTriggerRequest(BaseModel):
    source: str = "jobvetta"
    query_roles: List[str] = [
        "Data Analyst",
        "Data Scientist",
        "Financial Analyst",
        "Software Engineer",
        "Machine Learning Engineer"
    ]
    locations: List[str] = [
        "Mumbai",
        "Bengaluru",
        "Pune",
        "Hyderabad",
        "Delhi NCR"
    ]
    max_requests_per_query: int = 2


class IngestionRunResponse(BaseModel):
    id: int
    source: str
    status: str
    query_parameters: Dict[str, Any] = {}
    total_fetched: int
    new_inserted: int
    duplicates_skipped: int
    errors_count: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_log: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
