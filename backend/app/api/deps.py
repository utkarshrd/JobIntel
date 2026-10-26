"""
JobIntel - API Dependencies
Reusable dependency injectors for FastAPI route handlers.
"""

from backend.app.core.database import get_db

# Re-export get_db for convenient dependency injection
__all__ = ["get_db"]
