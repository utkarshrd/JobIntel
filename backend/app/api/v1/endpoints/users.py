"""
JobIntel - Candidate Profile & User Management API Endpoints
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.core.config import settings
from backend.app.core.security import check_user_token, user_access
from backend.app.models.user import User
from backend.app.schemas.user import UserCreate, UserUpdate, UserResponse
from backend.app.schemas.skill import UserSkillResponse
from backend.app.schemas.interaction import InteractionCreate, InteractionResponse
from backend.app.services.user_service import UserService
from backend.app.services.interaction_service import InteractionError, InteractionService
from recommender.pipeline import personalization_summary

router = APIRouter()


def _format_user_response(user: User) -> UserResponse:
    skills = []
    if user.skills_rel:
        for us in user.skills_rel:
            skills.append(
                UserSkillResponse(
                    id=us.id,
                    skill_id=us.skill_id,
                    skill_name=us.skill_rel.name if us.skill_rel else None,
                    skill_display_name=us.skill_rel.display_name if us.skill_rel else None,
                    proficiency_level=us.proficiency_level,
                    years_of_experience=us.years_of_experience,
                )
            )

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        headline=user.headline,
        summary=user.summary,
        education_level=user.education_level,
        field_of_study=user.field_of_study,
        experience_years=user.experience_years,
        current_location=user.current_location,
        target_role=user.target_role,
        preferred_roles=user.preferred_roles or [],
        preferred_locations=user.preferred_locations or [],
        preferred_work_models=user.preferred_work_models or [],
        preferred_employment_types=user.preferred_employment_types or [],
        min_salary_preference=user.min_salary_preference,
        created_at=user.created_at,
        updated_at=user.updated_at,
        skills=skills,
    )


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """Passwordless profile creation for tests / data import. Disabled when authentication is enforced (use /auth/register)."""
    if settings.REQUIRE_USER_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accounts are created with POST /api/v1/auth/register.")
    existing = UserService.get_user_by_email(db, user_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email {user_in.email} already exists."
        )
    user = UserService.create_user(db, user_in)
    return _format_user_response(user)


@router.get("/{user_id}", response_model=UserResponse, dependencies=[Depends(user_access)])
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Fetch user profile and preferences."""
    user = UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found."
        )
    return _format_user_response(user)


@router.put("/{user_id}", response_model=UserResponse, dependencies=[Depends(user_access)])
def update_user(user_id: int, user_in: UserUpdate, db: Session = Depends(get_db)):
    """Update profile details, target role, preferences, or skills."""
    user = UserService.update_user(db, user_id, user_in)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found."
        )
    return _format_user_response(user)


@router.post("/interactions", response_model=InteractionResponse, status_code=status.HTTP_201_CREATED)
def record_interaction(interaction_in: InteractionCreate, db: Session = Depends(get_db),
                       authorization: Optional[str] = Header(None)):
    """
    Log an interaction (view, click, save, apply, skip) for personalized feedback.
    """
    check_user_token(interaction_in.user_id, authorization)
    try:
        interaction = InteractionService.record_interaction(db, interaction_in)
    except InteractionError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    return InteractionResponse.model_validate(interaction)


@router.get("/{user_id}/interactions", response_model=List[InteractionResponse], dependencies=[Depends(user_access)])
def list_interactions(user_id: int, interaction_type: Optional[str] = None,
                      limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    """A user's stored interaction history, newest first."""
    if not UserService.get_user_by_id(db, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID {user_id} not found.")
    rows = InteractionService.get_user_interactions(db, user_id, interaction_type, limit)
    return [InteractionResponse.model_validate(r) for r in rows]


@router.get("/{user_id}/personalization", dependencies=[Depends(user_access)])
def get_personalization(user_id: int, db: Session = Depends(get_db)):
    """Personalization mode (cold_start / profile_based / interaction_informed) and what was learned
    from this user's real interactions."""
    user = UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID {user_id} not found.")
    return personalization_summary(db, user)
