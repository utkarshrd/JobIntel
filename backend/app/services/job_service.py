"""
JobIntel - Job Service
Handles database queries, filtering, creation, and pagination of job postings.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, desc
from backend.app.core.config import settings
from backend.app.models.job import Job
from backend.app.models.skill import JobSkill, Skill
from backend.app.models.company import Company
from backend.app.schemas.job import JobCreate, JobFilterParams


def stale_cutoff() -> Optional[datetime]:
    """Naive-UTC time before which an un-re-sighted job counts as stale; None when the filter is disabled."""
    days = settings.STALE_AFTER_DAYS
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=None) if days and days > 0 else None


def active_filter():
    """SQLAlchemy criterion for jobs that are not stale (always-true when disabled)."""
    cutoff = stale_cutoff()
    return Job.last_seen_at >= cutoff if cutoff else (Job.id > 0)


class JobService:
    @staticmethod
    def get_job_by_id(db: Session, job_id: int) -> Optional[Job]:
        """Fetch a job posting by internal integer primary key with skills loaded."""
        return (
            db.query(Job)
            .options(
                joinedload(Job.skills_rel).joinedload(JobSkill.skill_rel),
                joinedload(Job.company_rel),
            )
            .filter(Job.id == job_id)
            .first()
        )

    @staticmethod
    def get_job_by_external_id(db: Session, external_job_id: str) -> Optional[Job]:
        """Fetch a job posting by its external identifier (e.g. Jobvetta ID)."""
        return db.query(Job).filter(Job.job_id == external_job_id).first()

    @staticmethod
    def list_jobs(
        db: Session,
        params: JobFilterParams
    ) -> Tuple[List[Job], int]:
        """
        List jobs with dynamic filtering, text search, and pagination.
        """
        query = db.query(Job).options(
            joinedload(Job.skills_rel).joinedload(JobSkill.skill_rel),
            joinedload(Job.company_rel)
        )

        filters = [] if params.include_stale else [active_filter()]
        if params.source:
            filters.append(Job.source == params.source)

        if params.query:
            search_pattern = f"%{params.query}%"
            filters.append(
                or_(
                    Job.title.ilike(search_pattern),
                    Job.description.ilike(search_pattern),
                    Job.company_name.ilike(search_pattern),
                )
            )

        if params.role_category:
            filters.append(Job.role_category == params.role_category)

        if params.city:
            filters.append(Job.city.ilike(f"%{params.city}%"))

        if params.work_model:
            filters.append(Job.work_model.ilike(f"%{params.work_model}%"))

        if params.employment_type:
            filters.append(Job.employment_type.ilike(f"%{params.employment_type}%"))

        if params.experience_level:
            filters.append(Job.experience_level.ilike(f"%{params.experience_level}%"))

        if params.has_salary:
            filters.append(Job.salary_min.isnot(None))

        if params.skill:
            query = query.join(Job.skills_rel).join(JobSkill.skill_rel).filter(
                Skill.name.ilike(f"%{params.skill}%")
            )

        if filters:
            query = query.filter(and_(*filters))

        total = query.distinct(Job.id).count()
        offset = (params.page - 1) * params.page_size
        items = (
            query.order_by(desc(Job.posted_at), desc(Job.id))
            .offset(offset)
            .limit(params.page_size)
            .all()
        )

        return items, total

    @staticmethod
    def create_or_update_job(db: Session, job_in: JobCreate) -> Tuple[Job, bool]:
        """
        Create a new job posting or update an existing one based on job_id (deduplication).
        Returns (job, created_flag).
        """
        existing = JobService.get_job_by_external_id(db, job_in.job_id)
        if existing:
            # Re-sighted: refresh content and last_seen_at (used to detect stale / closed postings)
            for field, value in job_in.model_dump(exclude_unset=True).items():
                if field not in ("id", "job_id", "created_at") and value is not None:
                    setattr(existing, field, value)
            existing.last_seen_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing)
            return existing, False

        # Create new Company record if not existing
        company = None
        if job_in.company_name:
            norm_comp = job_in.company_name.strip().lower()
            company = db.query(Company).filter(Company.normalized_name == norm_comp).first()
            if not company:
                company = Company(
                    name=job_in.company_name.strip(),
                    normalized_name=norm_comp,
                )
                db.add(company)
                db.flush()

        job_data = job_in.model_dump()
        if company:
            job_data["company_id"] = company.id

        new_job = Job(**job_data)
        db.add(new_job)
        db.commit()
        db.refresh(new_job)
        return new_job, True
