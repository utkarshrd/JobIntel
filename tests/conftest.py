"""
JobIntel - Pytest Fixtures and Test Configuration
Configures in-memory SQLite database and FastAPI TestClient for integration testing.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# The suite must never touch the real (PostgreSQL) database: the app engine is pointed at in-memory SQLite
# BEFORE the app is imported. PostgreSQL behaviour is covered separately by tests/test_postgres.py.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REQUIRE_USER_TOKEN"] = "false"   # access control is covered by tests/test_access_control.py

from backend.app.core.database import Base, get_db  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.models import Job, Skill, JobSkill, User, UserSkill, Company

# In-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Provides a fresh transactional session for each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
