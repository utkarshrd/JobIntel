"""
JobIntel - Job Postings API Endpoints
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
import math

from backend.app.api.deps import get_db
from backend.app.schemas.job import (
    JobResponse,
    JobListResponse,
    JobCreate,
    JobFilterParams,
)
from backend.app.schemas.skill import JobSkillResponse
from backend.app.services.job_service import JobService

router = APIRouter()


def _format_job_response(job) -> JobResponse:
    """Helper to convert ORM Job to JobResponse with formatted extracted_skills."""
    skills = []
    if job.skills_rel:
        for js in job.skills_rel:
            skills.append(
                JobSkillResponse(
                    id=js.id,
                    skill_id=js.skill_id,
                    name=js.skill_rel.name if js.skill_rel else None,
                    display_name=js.skill_rel.display_name if js.skill_rel else None,
                    category=js.skill_rel.category if js.skill_rel else None,
                    skill_type=js.skill_type,
                    confidence=js.confidence,
                    extraction_method=js.extraction_method,
                )
            )

    return JobResponse(
        id=job.id,
        job_id=job.job_id,
        source=job.source,
        source_url=job.source_url,
        title=job.title,
        normalized_title=job.normalized_title,
        role_category=job.role_category,
        company_name=job.company_name,
        location_raw=job.location_raw,
        city=job.city,
        state=job.state,
        country=job.country,
        description=job.description,
        description_cleaned=job.description_cleaned,
        employment_type=job.employment_type,
        work_model=job.work_model,
        experience_level=job.experience_level,
        min_experience_years=job.min_experience_years,
        max_experience_years=job.max_experience_years,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        salary_period=job.salary_period,
        is_salary_predicted=job.is_salary_predicted,
        posted_at=job.posted_at,
        last_seen_at=job.last_seen_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
        extracted_skills=skills,
    )


@router.get("/", response_model=JobListResponse)
def list_jobs(
    query: Optional[str] = Query(None, description="Search keyword in title, description, company"),
    role_category: Optional[str] = Query(None, description="Role domain filter"),
    city: Optional[str] = Query(None, description="City location filter"),
    work_model: Optional[str] = Query(None, description="Work model (Onsite, Remote, Hybrid)"),
    employment_type: Optional[str] = Query(None, description="Employment type (Full-time, Internship)"),
    experience_level: Optional[str] = Query(None, description="Experience level (Entry-level, Mid-level, Senior)"),
    skill: Optional[str] = Query(None, description="Specific skill filter"),
    has_salary: Optional[bool] = Query(None, description="Filter for listings with disclosed salary"),
    source: Optional[str] = Query(None, description="Data source (adzuna, greenhouse, lever)"),
    include_stale: bool = Query(False, description="Also return jobs not re-sighted within STALE_AFTER_DAYS"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
):
    """
    Explore, search, and filter job postings with pagination.
    """
    filter_params = JobFilterParams(
        query=query,
        role_category=role_category,
        city=city,
        work_model=work_model,
        employment_type=employment_type,
        experience_level=experience_level,
        skill=skill,
        has_salary=has_salary,
        source=source,
        include_stale=include_stale,
        page=page,
        page_size=page_size,
    )

    items, total = JobService.list_jobs(db, filter_params)
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    formatted_items = [_format_job_response(j) for j in items]

    return JobListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=formatted_items,
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    """
    Retrieve single job posting by ID with full details, company, and extracted skills.
    """
    job = JobService.get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job listing with ID {job_id} not found."
        )
    return _format_job_response(job)


@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(job_in: JobCreate, db: Session = Depends(get_db)):
    """
    Create or deduplicate a job posting record.
    """
    job, _ = JobService.create_or_update_job(db, job_in)
    return _format_job_response(job)
