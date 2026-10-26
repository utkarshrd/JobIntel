"""
PostgreSQL behaviour (JSON columns, case-insensitive search, cascades, the full recommend/interaction flow).
Runs only when a PostgreSQL server is reachable (TEST_POSTGRES_URL, default: local postgres/postgres on 5432);
it uses its OWN throw-away database `jobintel_test`, never the application database. Otherwise skipped.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, get_db
from backend.app.main import app
from ingestion.saved_adzuna import load_saved_adzuna

ADMIN_URL = os.getenv("TEST_POSTGRES_ADMIN_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres")
TEST_DB = "jobintel_test"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"

RAW = {"query": {"what": "Data Analyst", "where": "Mumbai"}, "response": {"results": [
    {"id": "pg1", "title": "Data Analyst", "company": {"display_name": "Acme"}, "location": {"display_name": "Mumbai, Maharashtra"},
     "description": "Analyse data with SQL and Python.", "created": "2026-09-01T00:00:00Z", "redirect_url": "http://x/1"},
    {"id": "pg2", "title": "Java Developer", "company": {"display_name": "Beta"}, "location": {"display_name": "Pune, Maharashtra"},
     "description": "Backend services in Java.", "created": "2026-09-02T00:00:00Z", "redirect_url": "http://x/2"}]}}


@pytest.fixture(scope="module")
def pg_engine():
    try:
        admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB}"))
            c.execute(text(f"CREATE DATABASE {TEST_DB}"))
    except Exception as e:  # server not reachable / no permission
        pytest.skip(f"PostgreSQL not available: {type(e).__name__}")
    engine = create_engine(TEST_URL)
    from backend.app import models  # noqa: F401
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB}"))
    admin.dispose()


@pytest.fixture
def pg_client(pg_engine, tmp_path):
    Session = sessionmaker(bind=pg_engine)
    db = Session()
    (tmp_path / "adzuna_raw_20260101_000000_q1_x.json").write_text(json.dumps(RAW), encoding="utf-8")
    load_saved_adzuna(db, str(tmp_path))
    app.dependency_overrides[get_db] = lambda: (yield db)
    with TestClient(app) as c:
        yield c, db
    app.dependency_overrides.clear()
    db.close()


def test_postgres_end_to_end_flow(pg_client):
    client, db = pg_client
    from backend.app.models import Interaction, Job, JobSkill, User, UserSkill
    assert db.bind.dialect.name == "postgresql"
    assert db.query(Job).count() == 2 and db.query(JobSkill).count() >= 2
    assert client.get("/api/v1/health").json()["database"] == "healthy"
    assert client.get("/api/v1/jobs/?query=JAVA").json()["total"] == 1          # ILIKE search
    assert client.get("/api/v1/jobs/?skill=sql").json()["total"] == 1

    u = client.post("/api/v1/users/", json={"email": "pg@example.com", "full_name": "PG", "target_role": "Data Analyst",
                                             "preferred_locations": ["Mumbai"], "skills": [{"skill_name": "SQL"}]}).json()
    assert db.query(UserSkill).filter(UserSkill.user_id == u["id"]).count() == 1
    first = client.get(f"/api/v1/recommendations/{u['id']}").json()
    assert first["personalization_mode"] == "profile_based" and first["items"][0]["job"]["title"] == "Data Analyst"

    job_id = first["items"][0]["job"]["id"]
    assert client.post("/api/v1/users/interactions", json={"user_id": u["id"], "job_id": job_id, "interaction_type": "save"}).status_code == 201
    assert db.query(Interaction).filter(Interaction.user_id == u["id"]).count() == 1
    assert client.get(f"/api/v1/recommendations/{u['id']}").json()["personalization_mode"] == "interaction_informed"
    assert client.get("/api/v1/analytics/twsma").json()["total_jobs"] == 2

    # cascade delete: removing the user removes their skills and interactions
    db.delete(db.query(User).filter(User.id == u["id"]).one())
    db.commit()
    assert db.query(Interaction).filter(Interaction.user_id == u["id"]).count() == 0
    assert db.query(UserSkill).filter(UserSkill.user_id == u["id"]).count() == 0


def test_loader_idempotent_on_postgres(pg_engine, tmp_path):
    from backend.app.models import Job
    db = sessionmaker(bind=pg_engine)()
    (tmp_path / "adzuna_raw_20260101_000000_q1_x.json").write_text(json.dumps(RAW), encoding="utf-8")
    before = db.query(Job).count()
    run = load_saved_adzuna(db, str(tmp_path))
    assert run.new_inserted == 0 and db.query(Job).count() == before
    db.close()
