"""
JobIntel - Base Model
Provides base columns and timestamp mixins for all SQLAlchemy models.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer
from backend.app.core.database import Base


class TimestampMixin:
    """Provides created_at and updated_at datetime stamps."""
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
