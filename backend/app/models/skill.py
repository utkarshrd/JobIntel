"""
JobIntel - Skill and Skill Association Models
Handles normalized skills, job-skill associations, and user-skill proficiencies.
"""

from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
import enum
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin


class SkillType(str, enum.Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    MENTIONED = "mentioned"


class ExtractionMethod(str, enum.Enum):
    DICTIONARY = "dictionary"
    NER = "ner"
    EMBEDDING = "embedding"
    HYBRID = "hybrid"


class ProficiencyLevel(str, enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=False)
    category = Column(String(100), nullable=True, index=True)  # e.g., 'Programming', 'Cloud', 'Data & AI'
    aliases = Column(JSON, default=list, nullable=False)  # Alternative phrases/synonyms

    # Relationships
    job_skills = relationship("JobSkill", back_populates="skill_rel", cascade="all, delete-orphan")
    user_skills = relationship("UserSkill", back_populates="skill_rel", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Skill(id={self.id}, name='{self.name}', category='{self.category}')>"


class JobSkill(Base, TimestampMixin):
    __tablename__ = "job_skills"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_type = Column(String(20), default=SkillType.REQUIRED.value, nullable=False)
    confidence = Column(Float, default=1.0, nullable=False)
    extraction_method = Column(String(20), default=ExtractionMethod.DICTIONARY.value, nullable=False)

    # Relationships
    job_rel = relationship("Job", back_populates="skills_rel")
    skill_rel = relationship("Skill", back_populates="job_skills")

    def __repr__(self) -> str:
        return f"<JobSkill(job_id={self.job_id}, skill_id={self.skill_id}, confidence={self.confidence})>"


class UserSkill(Base, TimestampMixin):
    __tablename__ = "user_skills"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    proficiency_level = Column(String(20), default=ProficiencyLevel.INTERMEDIATE.value, nullable=False)
    years_of_experience = Column(Float, default=1.0, nullable=True)

    # Relationships
    user_rel = relationship("User", back_populates="skills_rel")
    skill_rel = relationship("Skill", back_populates="user_skills")

    def __repr__(self) -> str:
        return f"<UserSkill(user_id={self.user_id}, skill_id={self.skill_id}, level='{self.proficiency_level}')>"
