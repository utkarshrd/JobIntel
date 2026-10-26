"""
JobIntel - SQLAlchemy Models Package
Exposes all ORM models for database initialization, Alembic migrations, and query operations.
"""

from backend.app.models.base import TimestampMixin
from backend.app.models.company import Company
from backend.app.models.location import Location
from backend.app.models.skill import Skill, JobSkill, UserSkill, SkillType, ExtractionMethod, ProficiencyLevel
from backend.app.models.job import Job
from backend.app.models.user import User
from backend.app.models.interaction import Interaction, InteractionType
from backend.app.models.ingestion_run import IngestionRun, IngestionStatus

__all__ = [
    "TimestampMixin",
    "Company",
    "Location",
    "Skill",
    "JobSkill",
    "UserSkill",
    "SkillType",
    "ExtractionMethod",
    "ProficiencyLevel",
    "Job",
    "User",
    "Interaction",
    "InteractionType",
    "IngestionRun",
    "IngestionStatus",
]
