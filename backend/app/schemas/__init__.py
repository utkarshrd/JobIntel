"""
JobIntel - Pydantic Schemas Package
"""

from backend.app.schemas.job import (
    JobBase,
    JobCreate,
    JobUpdate,
    JobResponse,
    JobListResponse,
    JobFilterParams,
)
from backend.app.schemas.skill import (
    SkillBase,
    SkillCreate,
    SkillResponse,
    JobSkillResponse,
    UserSkillCreate,
    UserSkillResponse,
)
from backend.app.schemas.user import (
    UserBase,
    UserCreate,
    UserUpdate,
    UserResponse,
)
from backend.app.schemas.interaction import (
    InteractionCreate,
    InteractionResponse,
)
from backend.app.schemas.recommendation import (
    RecommendationExplanation,
    RecommendedJobResponse,
    RecommendationListResponse,
    SkillGapItem,
    SkillGapAnalysisResponse,
)
from backend.app.schemas.analytics import (
    SkillDemandItem,
    SkillCooccurrenceItem,
    LocationDemandItem,
    RoleDistributionItem,
    SalaryAnalyticsItem,
    MarketSummaryResponse,
)
from backend.app.schemas.ingestion import (
    IngestionTriggerRequest,
    IngestionRunResponse,
)

__all__ = [
    "JobBase",
    "JobCreate",
    "JobUpdate",
    "JobResponse",
    "JobListResponse",
    "JobFilterParams",
    "SkillBase",
    "SkillCreate",
    "SkillResponse",
    "JobSkillResponse",
    "UserSkillCreate",
    "UserSkillResponse",
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "InteractionCreate",
    "InteractionResponse",
    "RecommendationExplanation",
    "RecommendedJobResponse",
    "RecommendationListResponse",
    "SkillGapItem",
    "SkillGapAnalysisResponse",
    "SkillDemandItem",
    "SkillCooccurrenceItem",
    "LocationDemandItem",
    "RoleDistributionItem",
    "SalaryAnalyticsItem",
    "MarketSummaryResponse",
    "IngestionTriggerRequest",
    "IngestionRunResponse",
]
