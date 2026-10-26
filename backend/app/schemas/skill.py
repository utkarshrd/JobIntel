"""
JobIntel - Pydantic Schemas for Skills
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime


class SkillBase(BaseModel):
    name: str
    display_name: str
    category: Optional[str] = None
    aliases: List[str] = []


class SkillCreate(SkillBase):
    pass


class SkillResponse(SkillBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobSkillResponse(BaseModel):
    id: int
    skill_id: int
    name: Optional[str] = None
    display_name: Optional[str] = None
    category: Optional[str] = None
    skill_type: str
    confidence: float
    extraction_method: str

    model_config = ConfigDict(from_attributes=True)


class UserSkillCreate(BaseModel):
    skill_id: Optional[int] = None
    skill_name: Optional[str] = None
    proficiency_level: str = "intermediate"
    years_of_experience: float = 1.0


class UserSkillResponse(BaseModel):
    id: int
    skill_id: int
    skill_name: Optional[str] = None
    skill_display_name: Optional[str] = None
    proficiency_level: str
    years_of_experience: float

    model_config = ConfigDict(from_attributes=True)
