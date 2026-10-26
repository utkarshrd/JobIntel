"""
JobIntel - User Profile Model
Represents job seekers, candidates, students, and their preferences and skills.
"""

from sqlalchemy import Column, Integer, String, Text, Float, JSON
from sqlalchemy.orm import relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=True)   # scrypt hash; NULL for records created without a password
    headline = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)

    # Experience and Education
    education_level = Column(String(100), nullable=True)  # e.g., "Bachelor's", "Master's", "B.Tech", "MBA"
    field_of_study = Column(String(150), nullable=True)
    experience_years = Column(Float, default=0.0, nullable=False)
    current_location = Column(String(100), nullable=True)

    # Job Preferences for Recommendation System
    target_role = Column(String(100), nullable=True, index=True) # e.g. "Data Analyst"
    preferred_roles = Column(JSON, default=list, nullable=False)  # e.g. ["Data Analyst", "Data Scientist"]
    preferred_locations = Column(JSON, default=list, nullable=False)  # e.g. ["Mumbai", "Bengaluru", "Remote"]
    preferred_work_models = Column(JSON, default=list, nullable=False)  # e.g. ["Remote", "Hybrid"]
    preferred_employment_types = Column(JSON, default=list, nullable=False) # e.g. ["Full-time", "Internship"]
    min_salary_preference = Column(Float, nullable=True)

    # Relationships
    skills_rel = relationship("UserSkill", back_populates="user_rel", cascade="all, delete-orphan")
    interactions = relationship("Interaction", back_populates="user_rel", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', name='{self.full_name}', target_role='{self.target_role}')>"
