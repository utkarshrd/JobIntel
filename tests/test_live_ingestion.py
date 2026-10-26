"""Live ingestion (fake clients, no network), ATS normalizers, stale filtering, employer-skill filter, caching."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.core.config import settings
from backend.app.models import Job, JobSkill
from ingestion import live_runner as lr
from ingestion.ats_clients import is_india_location
from ingestion.normalizer import JobNormalizer
from nlp.skill_extractor import SkillExtractor


# ----------------------------------------------------------------------------- fakes

class FakeAdzuna:
    configured = True

    def __init__(self, total_per_query=120):
        self.calls_made = 0
        self.total = total_per_query
        self.log = []

    def validate_record(self, r):
        return bool(r.get("title") and r.get("id"))

    def fetch_page(self, what, where, page=1, per_page=50, **kw):
        self.calls_made += 1
        self.log.append((what, where, page))
        start = (page - 1) * per_page
        n = max(0, min(per_page, self.total - start))
        return {"count": self.total, "results": [
            {"id": f"{what}-{where}-{start + i}", "title": f"{what} {start + i}", "company": {"display_name": "Acme"},
             "location": {"display_name": f"{where}, Maharashtra"}, "description": "Analyse data using SQL and Python.",
             "created": "2026-10-01T00:00:00Z", "redirect_url": "http://x"} for i in range(n)]}


GH = [{"id": 11, "title": "Data Engineer", "company_name": "Acme", "location": {"name": "Bengaluru, India"},
       "content": "&lt;p&gt;Build pipelines with Kafka and Python.&lt;/p&gt;", "absolute_url": "http://gh/11",
       "first_published": "2026-09-01T10:00:00-04:00", "updated_at": "2026-10-01T10:00:00-04:00"},
      {"id": 12, "title": "Account Executive", "company_name": "Acme", "location": {"name": "New York, NY"}, "content": "sell"}]
LV = [{"id": "abc", "text": "Backend Engineer", "categories": {"location": "Dubai", "allLocations": ["Dubai", "Pune, Maharashtra"],
       "commitment": "Full-time"}, "description": "<p>Java services</p>", "lists": [{"text": "Needs", "content": "<li>Docker</li>"}],
       "hostedUrl": "http://lv/abc", "createdAt": 1790000000000, "workplaceType": "hybrid"},
      {"id": "def", "text": "Sales Lead", "categories": {"location": "London"}, "description": "x"}]


class FakeBoard:
    def __init__(self, data, fail=()):
        self.data, self.fail = data, set(fail)

    def fetch_board(self, token):
        if token in self.fail:
            raise RuntimeError("404")
        return self.data


# ----------------------------------------------------------------------------- Adzuna runner

def test_adzuna_plan_is_page_major():
    plan = lr.build_adzuna_plan(["A", "B"], ["X", "Y"], pages=2)
    assert plan[:4] == [("A", "X", 1), ("A", "Y", 1), ("B", "X", 1), ("B", "Y", 1)] and len(plan) == 8


def test_adzuna_budget_is_never_exceeded_and_audited(db_session, tmp_path):
    fake = FakeAdzuna(total_per_query=500)
    plan = lr.build_adzuna_plan(["Data Analyst", "Data Scientist"], ["Mumbai", "Pune"], pages=3)
    run = lr.run_adzuna(db_session, plan, budget=5, client=fake, raw_dir=str(tmp_path), sleep=lambda s: None)
    assert fake.calls_made == 5 and run.query_parameters["budget_exhausted"] is True
    assert run.total_fetched == 250 and run.new_inserted == 250 and run.errors_count == 0 and run.status == "completed"
    assert db_session.query(Job).filter(Job.source == "adzuna").count() == 250
    assert db_session.query(JobSkill).count() >= 250                      # skills persisted
    assert len(list(tmp_path.glob("adzuna_raw_*_q*.json"))) == 5          # raw responses kept for reproducibility
    saved = json.loads(sorted(tmp_path.glob("adzuna_raw_*"))[0].read_text())
    assert saved["query"] == {"what": "Data Analyst", "where": "Mumbai"} and len(saved["response"]["results"]) == 50


def test_adzuna_stops_paging_when_results_exhausted_and_is_idempotent(db_session):
    fake = FakeAdzuna(total_per_query=60)
    plan = lr.build_adzuna_plan(["Data Analyst"], ["Mumbai"], pages=5)
    run = lr.run_adzuna(db_session, plan, budget=50, client=fake, sleep=lambda s: None)
    assert fake.calls_made == 2 and run.total_fetched == 60               # page 2 had only 10 -> no page 3
    again = lr.run_adzuna(db_session, plan, budget=50, client=FakeAdzuna(60), sleep=lambda s: None)
    assert again.new_inserted == 0 and again.duplicates_skipped == 60
    assert db_session.query(Job).count() == 60


def test_adzuna_throttle_spaces_calls(db_session):
    waits = []
    lr.run_adzuna(db_session, lr.build_adzuna_plan(["A", "B", "C"], ["X"]), budget=10, client=FakeAdzuna(10),
                  per_minute=20, sleep=waits.append)
    assert len(waits) == 2 and all(0 < w <= 3.0 for w in waits)


def test_adzuna_without_credentials_fails_cleanly(db_session):
    fake = FakeAdzuna()
    fake.configured = False
    run = lr.run_adzuna(db_session, [("A", "X", 1)], client=fake)
    assert run.status == "failed" and fake.calls_made == 0 and "not configured" in run.error_log


def test_adzuna_http_error_is_recorded_not_fatal(db_session):
    class Boom(FakeAdzuna):
        def fetch_page(self, what, where, page=1, per_page=50, **kw):
            if where == "Pune":
                self.calls_made += 1
                raise RuntimeError("HTTP 500")
            return super().fetch_page(what, where, page, per_page)
    run = lr.run_adzuna(db_session, lr.build_adzuna_plan(["A"], ["Pune", "Mumbai"]), client=Boom(5), sleep=lambda s: None)
    assert run.status == "partial" and run.errors_count == 1 and run.new_inserted == 5


# ----------------------------------------------------------------------------- ATS boards

def test_india_location_detection():
    assert is_india_location("Bengaluru, India") and is_india_location("Remote", "Noida, Uttar Pradesh")
    assert not is_india_location("New York, NY")
    assert not is_india_location("") and not is_india_location("Dubai")


def test_ats_run_filters_india_normalizes_and_persists_full_text(db_session):
    run = lr.run_ats(db_session, {"greenhouse": ["acme"], "lever": ["acme"]}, greenhouse=FakeBoard(GH), lever=FakeBoard(LV),
                     sleep=lambda s: None)
    assert run.status == "completed" and run.total_fetched == 2 and run.new_inserted == 2 and run.query_parameters["api_calls"] == 2
    gh = db_session.query(Job).filter(Job.source == "greenhouse").one()
    assert gh.job_id == "gh:acme:11" and gh.city == "Bengaluru" and gh.role_category == "Data & Analytics"
    assert "Build pipelines" in gh.description_cleaned and "<p>" not in gh.description_cleaned
    assert gh.experience_level is None and gh.salary_min is None and gh.employment_type is None   # missing stays missing
    assert {s.skill_rel.name for s in gh.skills_rel} >= {"kafka", "python"}
    lv = db_session.query(Job).filter(Job.source == "lever").one()
    assert lv.city == "Pune" and lv.work_model == "Hybrid" and lv.employment_type == "Full-time"
    assert "Docker" in lv.description_cleaned and lv.posted_at is not None
    assert {s.skill_rel.name for s in lv.skills_rel} >= {"java", "docker"}


def test_ats_missing_board_is_recorded_and_closed_postings_reported(db_session):
    lr.run_ats(db_session, {"greenhouse": ["acme"]}, greenhouse=FakeBoard(GH), lever=FakeBoard([]), sleep=lambda s: None)
    # the posting disappears from the live board (and a second board 404s)
    shrunk = [dict(GH[0], id=99, title="ML Engineer")]
    run = lr.run_ats(db_session, {"greenhouse": ["acme", "gone"]}, greenhouse=FakeBoard(shrunk, fail=["gone"]),
                     lever=FakeBoard([]), sleep=lambda s: None)
    assert run.status == "partial" and run.errors_count == 1 and "gone" in run.error_log
    assert run.query_parameters["possibly_closed_by_board"] == {"greenhouse/acme": 1}


# ----------------------------------------------------------------------------- normalizer fixes

@pytest.mark.parametrize("raw,city", [
    ("Bengaluru-vtp", "Bengaluru"), ("Mumbai / bangalore", "Mumbai"), ("Gurgaon, Haryana", "Gurugram"),
    ("Bangalore - dd", "Bengaluru"), ("Pune, Maharashtra", "Pune")])
def test_city_extraction_variants(raw, city):
    assert JobNormalizer.extract_city_state(raw)[0] == city


def test_country_and_remote_labels_are_not_cities():
    assert JobNormalizer.extract_city_state("India") == (None, None)
    assert JobNormalizer.extract_city_state("Remote - India") == (None, None)


# ----------------------------------------------------------------------------- stale jobs

def test_stale_jobs_drop_out_unless_requested(client, db_session, monkeypatch):
    old = datetime.now(timezone.utc) - timedelta(days=40)
    for i, seen in enumerate([datetime.now(timezone.utc), old]):
        db_session.add(Job(job_id=f"st{i}", source="t", title=f"Data Analyst {i}", role_category="Data & Analytics",
                           company_name="Acme", city="Pune", description="sql", last_seen_at=seen))
    db_session.commit()
    monkeypatch.setattr(settings, "STALE_AFTER_DAYS", 30)
    assert client.get("/api/v1/jobs/").json()["total"] == 1
    assert client.get("/api/v1/jobs/?include_stale=true").json()["total"] == 2
    assert client.get("/api/v1/analytics/twsma").json()["total_jobs"] == 1
    assert client.get("/api/v1/analytics/summary").json()["total_jobs"] == 1
    assert lr.stale_report(db_session) == {"t": 1}
    monkeypatch.setattr(settings, "STALE_AFTER_DAYS", 0)
    assert client.get("/api/v1/jobs/").json()["total"] == 2


def test_resighting_refreshes_last_seen(db_session):
    from backend.app.services.job_service import JobService
    from backend.app.schemas.job import JobCreate
    job_in = JobCreate(job_id="r1", source="t", title="T", company_name="C", description="d")
    job, created = JobService.create_or_update_job(db_session, job_in)
    job.last_seen_at = datetime.now(timezone.utc) - timedelta(days=60)
    db_session.commit()
    job, created = JobService.create_or_update_job(db_session, job_in)
    assert not created and (datetime.now(timezone.utc).replace(tzinfo=None) - job.last_seen_at).days == 0


# ----------------------------------------------------------------------------- NLP bits

def test_employer_name_is_not_a_required_skill():
    ex = SkillExtractor()
    text = "We use MongoDB, Kafka and Python."
    assert "nosql" in {s.name for s in ex.extract_skills(text)}
    names = {s.name for s in ex.extract_skills(text, exclude_company="MongoDB")}
    assert "nosql" not in names and {"kafka", "python"} <= names


def test_expanded_taxonomy_extracts_new_skills():
    names = {s.name for s in SkillExtractor().extract_skills("Terraform, Airflow, Kubernetes, CI/CD pipelines on Linux with Snowflake")}
    assert {"terraform", "airflow", "kubernetes", "ci/cd", "linux", "snowflake"} <= names


@pytest.mark.parametrize("title,cat", [
    ("Data Scientists", "AI & Machine Learning"), ("Data Quality Analyst", "Data & Analytics"),
    ("Account Executive", "Sales & Marketing"), ("Solutions Architect", "Software Engineering"),
    ("HRBP_Bangalore", "Operations & HR"), ("Legal Entity Controller", "Finance & Banking")])
def test_classifier_covers_common_titles(title, cat):
    from nlp.classifier import JobRoleClassifier, is_default_fallback
    assert JobRoleClassifier.classify(title)[0] == cat and not is_default_fallback(title, cat)


def test_corpus_cache_gives_identical_scores_and_reuses_fit():
    from recommender import signals as sg
    texts = ["sql analyst dashboards", "java backend services", "python machine learning models"]
    first = sg.content_scores("sql python", texts)
    n = len(sg._CORPUS_CACHE)
    again = sg.content_scores("sql python", texts)
    assert first == again and len(sg._CORPUS_CACHE) == n
    assert sg.corpus_tfidf(texts) is not None and sg._CORPUS_CACHE[0][0] == tuple(texts)
    other = sg.content_scores("sql python", texts + ["new job text"])      # corpus changed -> refit, not stale scores
    assert len(other) == 4
