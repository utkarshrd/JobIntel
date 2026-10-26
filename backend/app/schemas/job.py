"""
JobIntel - Pydantic Schemas for Job Postings
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from backend.app.schemas.skill import JobSkillResponse


class JobBase(BaseModel):
    job_id: str
    source: str = "jobvetta"
    source_url: Optional[str] = None
    title: str
    normalized_title: Optional[str] = None
    role_category: Optional[str] = None
    company_name: str
    location_raw: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "India"
    description: str
    description_cleaned: Optional[str] = None
    employment_type: Optional[str] = None
    work_model: Optional[str] = None
    experience_level: Optional[str] = None
    min_experience_years: Optional[float] = None
    max_experience_years: Optional[float] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = "INR"
    salary_period: Optional[str] = "yearly"
    posted_at: Optional[datetime] = None


class JobCreate(JobBase):
    raw_payload: Optional[Dict[str, Any]] = None


class JobUpdate(BaseModel):
    title: Optional[str] = None
    normalized_title: Optional[str] = None
    role_category: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    description_cleaned: Optional[str] = None
    employment_type: Optional[str] = None
    work_model: Optional[str] = None
    experience_level: Optional[str] = None


class JobResponse(JobBase):
    id: int
    is_salary_predicted: bool
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime
    extracted_skills: List[JobSkillResponse] = []

    model_config = ConfigDict(from_attributes=True)


class JobListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[JobResponse]


class JobFilterParams(BaseModel):
    query: Optional[str] = None
    role_category: Optional[str] = None
    city: Optional[str] = None
    work_model: Optional[str] = None
    employment_type: Optional[str] = None
    experience_level: Optional[str] = None
    skill: Optional[str] = None
    has_salary: Optional[bool] = None
    source: Optional[str] = None
    include_stale: bool = False
    page: int = 1
    page_size: int = 20
