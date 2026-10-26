"""
JobIntel - API v1 Master Router
Aggregates all API endpoints for jobs, users, recommendations, analytics, skill gap, and health.
"""

from fastapi import APIRouter
from backend.app.api.v1.endpoints import (
    health,
    jobs,
    users,
    recommendations,
    analytics,
    skill_gap,
    ingestion,
    auth,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="", tags=["System"])
api_router.include_router(auth.router, prefix="/auth", tags=["Accounts"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
api_router.include_router(users.router, prefix="/users", tags=["Users & Profiles"])
api_router.include_router(recommendations.router, prefix="/recommendations", tags=["Recommendations"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Market Intelligence"])
api_router.include_router(skill_gap.router, prefix="/skill-gap", tags=["Skill Gap Analysis"])
api_router.include_router(ingestion.router, prefix="/ingestion", tags=["Ingestion"])
