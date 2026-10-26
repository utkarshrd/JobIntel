"""
JobIntel - Pydantic Schemas for Interactions
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from datetime import datetime


class InteractionCreate(BaseModel):
    user_id: int
    job_id: int
    interaction_type: str  # view, click, save, apply, skip
    duration_seconds: Optional[float] = None
    metadata_payload: Dict[str, Any] = {}


class InteractionResponse(BaseModel):
    id: int
    user_id: int
    job_id: int
    interaction_type: str
    duration_seconds: Optional[float] = None
    metadata_payload: Dict[str, Any] = {}
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
