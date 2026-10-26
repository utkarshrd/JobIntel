"""
JobIntel - Pydantic Schemas for Market Intelligence & Analytics
"""

from typing import List, Optional
from pydantic import BaseModel


class SkillDemandItem(BaseModel):
    skill_name: str
    display_name: str
    category: str
    job_count: int
    demand_percentage: float


class SkillCooccurrenceItem(BaseModel):
    skill_a: str
    skill_b: str
    cooccurrence_count: int
    cooccurrence_strength: float


class LocationDemandItem(BaseModel):
    city: str
    job_count: int
    top_roles: List[str] = []
    top_skills: List[str] = []


class RoleDistributionItem(BaseModel):
    role_category: str
    job_count: int
    percentage: float
    avg_min_salary: Optional[float] = None
    avg_max_salary: Optional[float] = None


class SalaryAnalyticsItem(BaseModel):
    role_category: str
    sample_size: int
    min_salary: Optional[float] = None
    median_salary: Optional[float] = None
    max_salary: Optional[float] = None
    currency: str = "INR"


class MarketSummaryResponse(BaseModel):
    total_jobs: int
    total_companies: int
    total_cities: int
    total_skills_tracked: int
    top_skills: List[SkillDemandItem]
    role_distribution: List[RoleDistributionItem]
    location_demand: List[LocationDemandItem]
    skill_cooccurrences: List[SkillCooccurrenceItem]
    salary_analytics: List[SalaryAnalyticsItem]
