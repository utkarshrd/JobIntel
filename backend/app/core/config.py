"""
JobIntel - Application Configuration & Settings
Loads and validates settings from environment variables or .env file.
"""

from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Core application settings for JobIntel.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application Info
    APP_NAME: str = "JobIntel"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "jobintel-secret-key-change-in-prod-2025"

    # Database Settings
    # Primary: PostgreSQL. Fallback for testing: SQLite
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/jobintel"
    DATABASE_URL_TEST: str = "sqlite:///./test_jobintel.db"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Backend API Server
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    API_V1_STR: str = "/api/v1"
    CORS_ORIGINS: List[str] = [
        "http://localhost:8501",
        "http://localhost:3000",
        "http://127.0.0.1:8501",
    ]

    # Job Ingestion - Primary Source: Jobvetta API
    JOBVETTA_API_KEY: Optional[str] = None
    JOBVETTA_BASE_URL: str = "https://api.jobvetta.com/v1"
    JOBVETTA_DAILY_REQUEST_LIMIT: int = 50
    JOBVETTA_PAGE_SIZE: int = 10

    # Job Ingestion - IndianAPI Jobs
    INDIANAPI_KEY: Optional[str] = None
    INDIANAPI_BASE_URL: str = "https://jobs.indianapi.in"

    # Secondary Source (Future): Adzuna API
    ADZUNA_APP_ID: Optional[str] = None
    ADZUNA_APP_KEY: Optional[str] = None
    ADZUNA_COUNTRY: str = "in"

    # NLP Settings
    SKILLS_TAXONOMY_PATH: str = "nlp/dictionaries/skills_taxonomy.json"

    # Live ingestion: jobs not re-sighted for this many days are treated as stale (0 disables the filter)
    STALE_AFTER_DAYS: int = 30
    ADZUNA_DAILY_CALL_BUDGET: int = 200   # stays under Adzuna's published 250 calls/day

    # Access control: when true, endpoints acting for a user need that user's bearer token
    REQUIRE_USER_TOKEN: bool = True
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7   # sign-in sessions last 7 days

    # Recommendation Weights (Hybrid Engine)
    WEIGHT_CONTENT: float = 0.30
    WEIGHT_SKILL: float = 0.35
    WEIGHT_PREFERENCE: float = 0.20
    WEIGHT_BEHAVIOR: float = 0.10
    WEIGHT_POPULARITY: float = 0.05

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        return ["*"]


settings = Settings()

if settings.SECRET_KEY.startswith(("jobintel-secret-key", "change-this")) and settings.ENVIRONMENT.lower() != "development":
    raise RuntimeError("SECRET_KEY is still the placeholder value: set a long random SECRET_KEY before running outside development.")
