"""
JobIntel - Database Engine & Session Management
Provides SQLAlchemy 2.0 engine, declarative base, sessionmaker, and dependency injection.
"""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.core.config import settings
from backend.app.core.logging import logger

# Base class for all ORM models
Base = declarative_base()

def get_engine_args(database_url: str) -> dict:
    """Return appropriate engine kwargs based on the database dialect."""
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_pre_ping": True,
    }

# Primary engine (PostgreSQL by default). Engine creation is lazy: an unreachable server surfaces as a failing
# /health check and request errors, not as a silent switch to another database.
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    **get_engine_args(settings.DATABASE_URL)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session per request
    and ensures clean closure upon request completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Create all tables defined in Base metadata if they do not already exist.
    """
    try:
        # Import models so Base.metadata is fully populated
        from backend.app import models  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Error during database initialization: {e}")
        raise
