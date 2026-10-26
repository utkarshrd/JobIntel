"""
JobIntel - Skill Gap Analysis API Endpoints
Analyzes skill requirements for a target role vs a candidate's current skills.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from backend.app.api.deps import get_db
from backend.app.core.security import user_access
from backend.app.models.job import Job
from backend.app.models.skill import Skill, JobSkill
from backend.app.schemas.recommendation import SkillGapAnalysisResponse, SkillGapItem
from backend.app.services.user_service import UserService

router = APIRouter()


@router.get("/analyze", response_model=SkillGapAnalysisResponse, dependencies=[Depends(user_access)])
def analyze_skill_gap(
    user_id: int = Query(..., description="Candidate user ID"),
    target_role: str = Query(..., description="Target role category e.g. 'Data & Analytics'"),
    db: Session = Depends(get_db),
):
    """
    Compare user skills against market requirements for a target role category.
    """
    user = UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found."
        )

    user_skills_set = {
        us.skill_rel.name.lower()
        for us in (user.skills_rel or [])
        if us.skill_rel
    }

    # Find jobs in this target role
    role_pattern = f"%{target_role}%"
    target_jobs_count = (
        db.query(func.count(Job.id))
        .filter(
            (Job.role_category.ilike(role_pattern)) | (Job.title.ilike(role_pattern))
        )
        .scalar()
        or 0
    )

    if target_jobs_count == 0:
        return SkillGapAnalysisResponse(
            target_role=target_role, total_jobs_analyzed=0, matching_skills_count=0, missing_skills_count=0,
            skill_gap_percentage=0.0, skills=[],
            recommendation_summary=f"No stored jobs match '{target_role}', so no skill requirements can be derived.",
        )

    # Aggregate top skills in target role
    results = (
        db.query(
            Skill.name,
            Skill.display_name,
            Skill.category,
            func.count(JobSkill.job_id).label("skill_freq"),
        )
        .join(JobSkill, Skill.id == JobSkill.skill_id)
        .join(Job, JobSkill.job_id == Job.id)
        .filter(
            (Job.role_category.ilike(role_pattern)) | (Job.title.ilike(role_pattern))
        )
        .group_by(Skill.id, Skill.name, Skill.display_name, Skill.category)
        .order_by(desc("skill_freq"))
        .limit(20)
        .all()
    )

    skill_items: List[SkillGapItem] = []
    matched_count = 0
    missing_count = 0

    for idx, r in enumerate(results, start=1):
        has_skill = r.name.lower() in user_skills_set
        if has_skill:
            matched_count += 1
        else:
            missing_count += 1

        freq_pct = round((r.skill_freq / max(1, target_jobs_count)) * 100, 1)

        skill_items.append(
            SkillGapItem(
                skill_name=r.name,
                display_name=r.display_name,
                category=r.category or "General",
                frequency_in_target_role=freq_pct,
                user_has_skill=has_skill,
                importance_rank=idx,
            )
        )

    total_req = matched_count + missing_count
    gap_pct = round((missing_count / total_req * 100), 1) if total_req > 0 else 0.0

    summary = (
        f"You possess {matched_count} out of {total_req} key skills for '{target_role}'. "
        f"Addressing your {missing_count} missing skills can increase your market readiness by up to {gap_pct}%."
    )

    return SkillGapAnalysisResponse(
        target_role=target_role,
        total_jobs_analyzed=target_jobs_count,
        matching_skills_count=matched_count,
        missing_skills_count=missing_count,
        skill_gap_percentage=gap_pct,
        skills=skill_items,
        recommendation_summary=summary,
    )


@router.get("/job/{job_id}", dependencies=[Depends(user_access)])
def analyze_job_skill_gap(job_id: int, user_id: int = Query(..., description="Candidate user ID"),
                          db: Session = Depends(get_db)):
    """Compare one user's skills with the skills extracted from one specific job posting."""
    from backend.app.services.job_service import JobService
    from recommender import signals as sg
    from recommender.pipeline import features_from_job, profile_from_user

    user = UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID {user_id} not found.")
    job = JobService.get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job listing with ID {job_id} not found.")
    feats, profile = features_from_job(job), profile_from_user(user)
    score, matched, _ = sg.skill_overlap(profile, feats)
    names = lambda ss: [feats.skill_display.get(s, s) for s in ss]
    missing = [s for s in feats.skills if s not in profile.skills]
    return {
        "job_id": job.id, "title": job.title, "company_name": job.company_name,
        "job_skills_extracted": len(feats.skills),
        "user_has_skills": bool(profile.skills),
        "matched_skills": names(matched), "missing_skills": names(missing),
        "match_ratio": None if score is None else round(score, 4),
        "note": ("No skills could be extracted from this posting (descriptions are short snippets)."
                 if not feats.skills else None),
    }
