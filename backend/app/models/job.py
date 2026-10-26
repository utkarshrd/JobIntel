"""
JobIntel - Job Posting Model
Represents ingested and normalized job records from Jobvetta and other API sources.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Index,
)
from sqlalchemy.orm import relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    
    # External identity and source tracking
    job_id = Column(String(255), unique=True, nullable=False, index=True)  # Provider-specific ID or composite hash
    source = Column(String(50), default="jobvetta", nullable=False, index=True)
    source_url = Column(String(1000), nullable=True)

    # Core Job Information
    title = Column(String(255), nullable=False, index=True)
    normalized_title = Column(String(255), nullable=True, index=True)
    role_category = Column(String(100), nullable=True, index=True)  # e.g., 'Data & Analytics', 'Software Engineering'

    # Company Reference
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    company_name = Column(String(255), nullable=False, index=True)

    # Location Information
    location_raw = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True, index=True)
    state = Column(String(100), nullable=True, index=True)
    country = Column(String(100), default="India", nullable=False, index=True)

    # Content
    description = Column(Text, nullable=False)
    description_cleaned = Column(Text, nullable=True)

    # Role Characteristics
    employment_type = Column(String(50), nullable=True, index=True)  # Full-time, Internship, Contract
    work_model = Column(String(50), nullable=True, index=True)       # Onsite, Remote, Hybrid
    experience_level = Column(String(50), nullable=True, index=True) # Entry-level, Mid-level, Senior
    min_experience_years = Column(Float, nullable=True)
    max_experience_years = Column(Float, nullable=True)

    # Compensation (No imputation of missing values - preserved as null)
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    salary_currency = Column(String(10), default="INR", nullable=True)
    salary_period = Column(String(20), default="yearly", nullable=True)  # yearly, monthly
    is_salary_predicted = Column(Boolean, default=False, nullable=False)

    # Timestamps & Tracking
    posted_at = Column(DateTime, nullable=True, index=True)
    last_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    raw_payload = Column(JSON, nullable=True)  # Captured raw API JSON for reproducibility

    # Relationships
    company_rel = relationship("Company", back_populates="jobs")
    skills_rel = relationship("JobSkill", back_populates="job_rel", cascade="all, delete-orphan")
    interactions = relationship("Interaction", back_populates="job_rel", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_jobs_city_role", "city", "role_category"),
        Index("ix_jobs_posted_source", "posted_at", "source"),
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, job_id='{self.job_id}', title='{self.title}', company='{self.company_name}', city='{self.city}')>"
