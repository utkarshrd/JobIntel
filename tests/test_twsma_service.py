"""
JobIntel - TWSMA analytics tests (small deterministic fixtures, not real-world results).
"""

from datetime import datetime

import pytest

from backend.app.services import twsma_service as tw
from backend.app.services.twsma_service import JobRecord


def J(title, role, company, city, skills, desc="", posted=None, fallback=False):
    return JobRecord(title=title, role_category=role, company=company, city=city,
                     skills=list(skills), description=desc, posted_at=posted, role_is_fallback=fallback)


@pytest.fixture
def records():
    return [
        J("Data Analyst", "Data & Analytics", "Acme", "Mumbai", ["sql", "excel", "python"], "Requires B.Tech and 2-4 years of SQL."),
        J("Data Analyst", "Data & Analytics", "Acme", "Pune", ["sql", "power bi"], "SQL and dashboards. Minimum 3 years."),
        J("Data Scientist", "AI & Machine Learning", "Beta", "Mumbai", ["python", "sql", "machine learning"], "MBA preferred... ", ),
        J("Zebra Wrangler", "Software Engineering", "Confidential", None, [], "", fallback=True),
    ]


def test_top_skills_counts_and_percentages(records):
    top = tw.top_skills(records)
    assert top[0] == {"skill": "sql", "job_count": 3, "percentage": 75.0}
    assert {"skill": "python", "job_count": 2, "percentage": 50.0} in top
    assert tw.top_skills(records, limit=1) == [top[0]]


def test_skill_coverage(records):
    cov = tw.skill_coverage(records)
    assert cov["jobs_with_skills"] == 3 and cov["jobs_without_skills"] == 1
    assert cov["mean_skills_per_job"] == 2.0


def test_skills_by_role_uses_role_denominator(records):
    sbr = tw.skills_by_role(records)
    da = sbr["Data & Analytics"]
    assert da["job_count"] == 2
    assert {"skill": "sql", "job_count": 2, "percentage": 100.0} in da["top_skills"]
    assert sbr["Software Engineering"]["top_skills"] == []


def test_role_distribution_separates_fallback(records):
    rd = tw.role_distribution(records)
    assert rd["total_jobs"] == 4
    assert rd["unmatched_fallback"] == 1 and rd["classified_by_keyword"] == 3
    se = next(i for i in rd["items"] if i["role_category"] == "Software Engineering")
    assert se["job_count"] == 1 and se["fallback_count"] == 1 and se["percentage"] == 25.0


def test_location_counts_and_missing(records):
    ld = tw.location_distribution(records)
    assert ld["missing_city"] == 1
    assert ld["items"][0] == {"city": "Mumbai", "job_count": 2, "percentage": 50.0}
    sbl = tw.skills_by_location(records)
    assert sbl["Pune"]["top_skills"][0]["skill"] in ("power bi", "sql")
    assert "None" not in sbl


def test_company_counts_exclude_undisclosed(records):
    cd = tw.company_distribution(records)
    assert cd["undisclosed_count"] == 1
    assert cd["items"][0] == {"company": "Acme", "job_count": 2}
    assert cd["distinct_companies"] == 2


def test_skill_cooccurrence_only_real_pairs(records):
    pairs = tw.skill_cooccurrence(records, min_count=2)
    assert {(p["skill_a"], p["skill_b"]) for p in pairs} == {("python", "sql")}
    assert pairs[0]["job_count"] == 2
    # a pair never present together must not appear, even at min_count=1
    all_pairs = {(p["skill_a"], p["skill_b"]) for p in tw.skill_cooccurrence(records, min_count=1)}
    assert ("excel", "power bi") not in all_pairs
    assert ("excel", "python") in all_pairs


def test_description_statistics(records):
    ds = tw.description_statistics(records)
    assert ds["missing_description"] == 1
    assert ds["truncated_with_ellipsis"] == 1
    assert ds["min_length"] <= ds["median_length"] <= ds["max_length"]
    assert tw.description_statistics([])["median_length"] is None


def test_qualification_and_experience_mentions(records):
    q = tw.qualification_mentions(records)
    names = {i["qualification"]: i["job_count"] for i in q["items"]}
    assert names == {"B.Tech / B.E.": 1, "MBA": 1}
    e = tw.experience_mentions(records)
    assert e["jobs_with_stated_experience"] == 2 and e["with_upper_bound"] == 1


def test_qualification_ignores_plain_word_be():
    assert tw.qualification_mentions([J("x", None, "c", "m", [], "Candidates must be able to be flexible")])["items"] == []


def test_common_terms_document_frequency(records):
    terms = tw.common_terms(records, min_docs=2)
    assert any(t["term"] == "sql" and t["job_count"] == 2 for t in terms["unigrams"])


def test_posting_dates_do_not_claim_trend_on_small_data():
    recs = [J("a", None, "c", "m", [], posted=datetime(2026, 9, d)) for d in (1, 10, 28)]
    recs.append(J("b", None, "c", "m", []))
    pd_ = tw.posting_date_analysis(recs)
    assert pd_["with_date"] == 3 and pd_["missing_date"] == 1
    assert pd_["trend_supported"] is False and "Not enough data" in pd_["trend_reason"]
    assert pd_["freshness"]["0-7 days"] == 1 and pd_["monthly_counts"] == [{"month": "2026-09", "job_count": 3}]


def test_posting_dates_support_trend_when_dense():
    recs = [J("a", None, "c", "m", [], posted=datetime(2026, mo, 1 + i % 20)) for mo in range(1, 7) for i in range(30)]
    assert tw.posting_date_analysis(recs)["trend_supported"] is True


def test_dedupe_content():
    recs = [J("A", None, "Co", "X", []), J("a", None, "co", "x", []), J("A", None, "Co", "Y", [])]
    assert len(tw.dedupe_content(recs)) == 2


def test_build_report_has_all_sections(records):
    rep = tw.build_twsma_report(records)
    assert {"top_skills", "skills_by_role", "role_distribution", "location_distribution", "company_distribution",
            "skill_cooccurrence", "text_analysis", "posting_dates"} <= set(rep)


def test_empty_input_is_safe():
    rep = tw.build_twsma_report([])
    assert rep["total_jobs"] == 0 and rep["top_skills"] == []


def test_load_records_from_db_and_service_cooccurrence(db_session):
    from backend.app.models import Job, Skill, JobSkill
    from backend.app.services.analytics_service import AnalyticsService

    py, sql = Skill(name="python", display_name="Python"), Skill(name="sql", display_name="SQL")
    db_session.add_all([py, sql])
    for i in range(2):
        j = Job(job_id=f"t{i}", source="test", title="Data Analyst", role_category="Data & Analytics",
                company_name="Acme", city="Pune", description="x")
        db_session.add(j)
        db_session.flush()
        db_session.add_all([JobSkill(job_id=j.id, skill_id=py.id), JobSkill(job_id=j.id, skill_id=sql.id)])
    db_session.flush()
    recs = tw.load_records_from_db(db_session)
    assert len(recs) == 2 and recs[0].skills == ["python", "sql"]
    pairs = AnalyticsService.get_skill_cooccurrences(db_session)
    assert pairs[0].skill_a == "python" and pairs[0].cooccurrence_count == 2
