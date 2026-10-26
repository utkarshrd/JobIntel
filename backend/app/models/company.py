"""
JobIntel - Company Model
Represents employers and hiring entities normalized from job postings.
"""

from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    normalized_name = Column(String(255), nullable=False, index=True)
    industry = Column(String(100), nullable=True, index=True)
    company_size = Column(String(50), nullable=True)
    website = Column(String(500), nullable=True)
    logo_url = Column(String(500), nullable=True)

    # Relationships
    jobs = relationship("Job", back_populates="company_rel", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name='{self.name}', industry='{self.industry}')>"
