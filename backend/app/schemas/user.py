"""
JobIntel - Pydantic Schemas for Users and Candidate Profiles
"""

from typing import List, Optional
from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime
from backend.app.schemas.skill import UserSkillResponse, UserSkillCreate


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    headline: Optional[str] = None
    summary: Optional[str] = None
    education_level: Optional[str] = None
    field_of_study: Optional[str] = None
    experience_years: float = 0.0
    current_location: Optional[str] = None
    target_role: Optional[str] = None
    preferred_roles: List[str] = []
    preferred_locations: List[str] = []
    preferred_work_models: List[str] = []
    preferred_employment_types: List[str] = []
    min_salary_preference: Optional[float] = None


class UserCreate(UserBase):
    skills: List[UserSkillCreate] = []


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    education_level: Optional[str] = None
    field_of_study: Optional[str] = None
    experience_years: Optional[float] = None
    current_location: Optional[str] = None
    target_role: Optional[str] = None
    preferred_roles: Optional[List[str]] = None
    preferred_locations: Optional[List[str]] = None
    preferred_work_models: Optional[List[str]] = None
    preferred_employment_types: Optional[List[str]] = None
    min_salary_preference: Optional[float] = None
    skills: Optional[List[UserSkillCreate]] = None


class UserResponse(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime
    skills: List[UserSkillResponse] = []

    model_config = ConfigDict(from_attributes=True)
