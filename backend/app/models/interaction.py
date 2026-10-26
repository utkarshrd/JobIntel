"""
JobIntel - User Interaction Model
Records behavioral interactions (view, save, click, apply, skip) to power personalized recommendations.
"""

from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class InteractionType(str, enum.Enum):
    VIEW = "view"
    CLICK = "click"
    SAVE = "save"
    APPLY = "apply"
    SKIP = "skip"


class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    interaction_type = Column(String(20), nullable=False, index=True)
    duration_seconds = Column(Float, nullable=True)  # Time spent viewing
    metadata_payload = Column(JSON, default=dict, nullable=False) # e.g. source_page, rank_position
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Relationships
    user_rel = relationship("User", back_populates="interactions")
    job_rel = relationship("Job", back_populates="interactions")

    __table_args__ = (
        Index("ix_interactions_user_type", "user_id", "interaction_type"),
        Index("ix_interactions_user_job", "user_id", "job_id"),
    )

    def __repr__(self) -> str:
        return f"<Interaction(user_id={self.user_id}, job_id={self.job_id}, type='{self.interaction_type}')>"
