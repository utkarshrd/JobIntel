"""Saved-data loader (idempotency, persisted skills, no placeholders) and TWSMA/analytics endpoints."""
import json

import pytest

from backend.app.models import Job, JobSkill
from backend.app.models.ingestion_run import IngestionRun
from ingestion.saved_adzuna import load_saved_adzuna

RAW = {
    "query": {"what": "Data Analyst", "where": "Mumbai"}, "http_status": 200,
    "response": {"results": [
        {"id": "a1", "title": "Data Analyst", "company": {"display_name": "Acme"},
         "location": {"display_name": "Mumbai, Maharashtra"}, "description": "Analyse data using SQL and Python.",
         "created": "2026-09-01T00:00:00Z", "redirect_url": "http://x/1"},
        {"id": "a2", "title": "Data Scientist", "company": {"display_name": "Beta"},
         "location": {"display_name": "Pune, Maharashtra"}, "description": "Machine learning and SQL models.",
         "created": "2026-09-02T00:00:00Z", "redirect_url": "http://x/2"},
    ]},
}


@pytest.fixture
def raw_dir(tmp_path):
    (tmp_path / "adzuna_raw_20260101_000000_q1_Data_Analyst_Mumbai.json").write_text(json.dumps(RAW), encoding="utf-8")
    return str(tmp_path)


def test_loader_persists_jobs_skills_and_audit_row_idempotently(db_session, raw_dir):
    run = load_saved_adzuna(db_session, raw_dir)
    assert (run.total_fetched, run.new_inserted, run.duplicates_skipped, run.errors_count) == (2, 2, 0, 0)
    assert run.status == "completed" and run.query_parameters["api_calls"] == 0
    assert db_session.query(Job).count() == 2
    sql_links = db_session.query(JobSkill).count()
    assert sql_links >= 3
    again = load_saved_adzuna(db_session, raw_dir)
    assert again.new_inserted == 0 and again.duplicates_skipped == 2
    assert db_session.query(Job).count() == 2 and db_session.query(JobSkill).count() == sql_links
    assert db_session.query(IngestionRun).count() == 2


def test_missing_source_fields_stay_missing(db_session, raw_dir):
    load_saved_adzuna(db_session, raw_dir)
    for j in db_session.query(Job).all():
        assert j.experience_level is None and j.employment_type is None and j.salary_min is None
        assert j.work_model is None          # no remote/hybrid wording => not guessed as "Onsite"


def test_loader_without_files_raises(db_session, tmp_path):
    with pytest.raises(FileNotFoundError):
        load_saved_adzuna(db_session, str(tmp_path))


def test_twsma_and_summary_endpoints_over_loaded_data(client, db_session, raw_dir):
    load_saved_adzuna(db_session, raw_dir)
    rep = client.get("/api/v1/analytics/twsma")
    assert rep.status_code == 200
    body = rep.json()
    assert body["total_jobs"] == 2 and "scope_note" in body
    assert {"top_skills", "role_distribution", "skills_by_role", "location_distribution",
            "company_distribution", "skill_cooccurrence", "text_analysis", "posting_dates"} <= set(body)
    assert body["posting_dates"]["trend_supported"] is False
    assert client.get("/api/v1/analytics/twsma?dedupe=true").status_code == 200
    summ = client.get("/api/v1/analytics/summary").json()
    assert summ["total_jobs"] == 2 and summ["total_cities"] == 2
    assert client.get("/api/v1/ingestion/runs").json()[0]["source"] == "adzuna_saved_files"


def test_skill_gap_endpoint_uses_user_skills(client, db_session, raw_dir):
    load_saved_adzuna(db_session, raw_dir)
    u = client.post("/api/v1/users/", json={"email": "sg@jobintel.ai", "full_name": "S",
                                            "skills": [{"skill_name": "sql"}]}).json()
    r = client.get(f"/api/v1/skill-gap/analyze?user_id={u['id']}&target_role=Data")
    assert r.status_code == 200
    items = {s["skill_name"]: s for s in r.json()["skills"]}
    assert items["sql"]["user_has_skill"] is True
    assert any(not s["user_has_skill"] for s in items.values())
    assert client.get("/api/v1/skill-gap/analyze?user_id=999999&target_role=Data").status_code == 404


def test_skill_gap_unknown_role_is_empty_not_all_jobs(client, db_session, raw_dir):
    load_saved_adzuna(db_session, raw_dir)
    u = client.post("/api/v1/users/", json={"email": "sg2@jobintel.ai", "full_name": "S"}).json()
    body = client.get(f"/api/v1/skill-gap/analyze?user_id={u['id']}&target_role=Astronaut").json()
    assert body["total_jobs_analyzed"] == 0 and body["skills"] == []


def test_job_level_skill_gap(client, db_session, raw_dir):
    load_saved_adzuna(db_session, raw_dir)
    u = client.post("/api/v1/users/", json={"email": "sg3@jobintel.ai", "full_name": "S",
                                            "skills": [{"skill_name": "sql"}]}).json()
    job = client.get("/api/v1/jobs/?query=Machine").json()["items"][0]
    r = client.get(f"/api/v1/skill-gap/job/{job['id']}?user_id={u['id']}").json()
    assert "SQL" in r["matched_skills"] and "Machine Learning" in r["missing_skills"]
    assert client.get(f"/api/v1/skill-gap/job/999999?user_id={u['id']}").status_code == 404
