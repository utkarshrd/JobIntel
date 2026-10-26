"""
JobIntel - Location Model
Represents geographic locations, cities, states, and market tiers in India.
"""

from sqlalchemy import Column, Integer, String
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin


class Location(Base, TimestampMixin):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    raw_name = Column(String(255), nullable=False, index=True)
    city = Column(String(100), nullable=True, index=True)
    state = Column(String(100), nullable=True, index=True)
    country = Column(String(100), default="India", nullable=False, index=True)
    tier = Column(String(20), nullable=True)  # e.g., 'Tier 1', 'Tier 2', 'Tier 3'

    def __repr__(self) -> str:
        return f"<Location(id={self.id}, city='{self.city}', state='{self.state}', country='{self.country}')>"
