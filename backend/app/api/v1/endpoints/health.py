"""
JobIntel - Health & System Status Endpoints
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.api.deps import get_db
from backend.app.core.config import settings

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK, tags=["System"])
def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint returning system status, version, and database connectivity.
    """
    db_status = "unhealthy"
    try:
        # Perform quick ping
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "online",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
    }
