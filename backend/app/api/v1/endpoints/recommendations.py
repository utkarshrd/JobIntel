"""
JobIntel - Recommendation Engine API Endpoints
Personalized, explainable job recommendations. All ranking logic lives in the `recommender` package.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.core.security import user_access
from backend.app.schemas.recommendation import RecommendationListResponse
from backend.app.services.user_service import UserService
from recommender.config import HybridWeights
from recommender.pipeline import recommendation_list

router = APIRouter()


@router.get("/{user_id}", response_model=RecommendationListResponse, dependencies=[Depends(user_access)])
def get_recommendations(
    user_id: int,
    limit: int = Query(20, ge=1, le=50, description="Max recommendations to return"),
    ranking_strategy: str = Query("hybrid", pattern="^(hybrid|skills|content|popularity)$",
                                  description="Strategy: hybrid, skills, content, popularity"),
    w_skill: Optional[float] = Query(None, ge=0, description="Hybrid only: override skill weight"),
    w_content: Optional[float] = Query(None, ge=0, description="Hybrid only: override content weight"),
    w_role: Optional[float] = Query(None, ge=0, description="Hybrid only: override role weight"),
    w_location: Optional[float] = Query(None, ge=0, description="Hybrid only: override location weight"),
    w_popularity: Optional[float] = Query(None, ge=0, description="Hybrid only: override popularity weight"),
    w_behavior: Optional[float] = Query(None, ge=0, description="Hybrid only: override behavior weight (used only once the user has real interactions)"),
    db: Session = Depends(get_db),
):
    """
    Rank all stored jobs for a user. Weights are raw and get normalised; unspecified ones keep their
    configured defaults. Signals the user gave no data for are dropped (see recommender.ranking).
    """
    user = UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID {user_id} not found.")

    overrides = {k: v for k, v in {
        "skill": w_skill, "content": w_content, "role": w_role,
        "location": w_location, "popularity": w_popularity, "behavior": w_behavior}.items() if v is not None}
    weights = None
    if overrides:
        if ranking_strategy != "hybrid":
            raise HTTPException(status_code=400, detail="Weight overrides apply only to ranking_strategy=hybrid.")
        try:
            weights = HybridWeights(**{**HybridWeights.from_settings().as_dict(), **overrides})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return recommendation_list(db, user, ranking_strategy, limit, weights)
