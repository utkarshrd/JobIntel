"""
JobIntel - User Interaction Service
Records user interactions (view, save, click, apply, skip) for personalization feedback loop.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from backend.app.models.interaction import Interaction
from backend.app.models.job import Job
from backend.app.models.user import User
from backend.app.schemas.interaction import InteractionCreate
from recommender.behavior import INTERACTION_TYPES


class InteractionError(ValueError):
    """Invalid interaction request. `status` is the HTTP status the API should use."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


class InteractionService:
    @staticmethod
    def record_interaction(db: Session, interaction_in: InteractionCreate) -> Interaction:
        """Record a real user interaction with a job listing (validated; never inferred or seeded)."""
        itype = (interaction_in.interaction_type or "").strip().lower()
        if itype not in INTERACTION_TYPES:
            raise InteractionError(f"interaction_type must be one of {list(INTERACTION_TYPES)}", 422)
        if interaction_in.duration_seconds is not None and interaction_in.duration_seconds < 0:
            raise InteractionError("duration_seconds must be >= 0", 422)
        if not db.query(User.id).filter(User.id == interaction_in.user_id).first():
            raise InteractionError(f"User with ID {interaction_in.user_id} not found.", 404)
        if not db.query(Job.id).filter(Job.id == interaction_in.job_id).first():
            raise InteractionError(f"Job with ID {interaction_in.job_id} not found.", 404)
        interaction = Interaction(
            user_id=interaction_in.user_id,
            job_id=interaction_in.job_id,
            interaction_type=itype,
            duration_seconds=interaction_in.duration_seconds,
            metadata_payload=interaction_in.metadata_payload,
        )
        db.add(interaction)
        db.commit()
        db.refresh(interaction)
        return interaction

    @staticmethod
    def get_user_interactions(
        db: Session,
        user_id: int,
        interaction_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Interaction]:
        """Fetch history of interactions for a user."""
        query = db.query(Interaction).filter(Interaction.user_id == user_id)
        if interaction_type:
            query = query.filter(Interaction.interaction_type == interaction_type.lower())
        return query.order_by(desc(Interaction.created_at)).limit(limit).all()
