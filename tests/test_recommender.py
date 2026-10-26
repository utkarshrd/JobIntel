"""
JobIntel - Recommendation pipeline tests (small deterministic fixtures, not real-world results).
"""

from datetime import datetime

import pytest

from recommender import signals as sg
from recommender.config import HybridWeights, weights_for_strategy
from recommender.explainability import ExplainabilityGenerator, SignalEvidence
from recommender.ranking import rank_jobs


def job(i, title="Data Analyst", cat="Data & Analytics", city="Mumbai", skills=(), text=None, posted=None, **kw):
    return sg.JobFeatures(id=i, title=title, role_category=cat, city=city, skills=tuple(skills),
                          text=text if text is not None else title, posted_at=posted, **kw)


def user(skills=(), roles=(), locations=(), text=""):
    return sg.UserProfile(skills=frozenset(skills), roles=list(roles), locations=list(locations), text=text)


# ----------------------------------------------------------------- config

def test_weights_validated_and_normalized():
    w = HybridWeights(skill=2, content=2, role=0, location=0, popularity=0, behavior=0)
    assert w.normalized()["skill"] == 0.5
    assert pytest.approx(sum(HybridWeights.from_settings().normalized().values())) == 1.0
    for bad in (-1, float("nan"), float("inf"), "x", True):
        with pytest.raises(ValueError):
            HybridWeights(skill=bad)
    with pytest.raises(ValueError):
        HybridWeights(skill=0, content=0, role=0, location=0, popularity=0, behavior=0)


def test_strategy_presets():
    assert weights_for_strategy("skills").normalized()["skill"] == 1.0
    assert weights_for_strategy("popularity").normalized()["popularity"] == 1.0
    with pytest.raises(ValueError):
        weights_for_strategy("nonsense")


# ----------------------------------------------------------------- skill matching

def test_skill_overlap_ratio_matched_missing():
    score, matched, missing = sg.skill_overlap(user(skills=["sql", "python"]), job(1, skills=["sql", "excel", "python", "tableau"]))
    assert score == 0.5 and matched == ["python", "sql"] and missing == ["excel", "tableau"]


def test_job_without_skills_is_not_a_match():
    assert sg.skill_overlap(user(skills=["sql"]), job(1, skills=[])) == (None, [], [])


def test_missing_skills_not_reported_when_user_has_no_skills():
    score, matched, missing = sg.skill_overlap(user(), job(1, skills=["sql"]))
    assert (score, matched, missing) == (0.0, [], [])


# ----------------------------------------------------------------- content similarity

def test_content_similarity_orders_relevant_text_first():
    jobs = ["sql tableau dashboards reporting analyst", "welding fabrication metal workshop", "python sql analysis analyst"]
    s = sg.content_scores("sql analyst python", jobs)
    assert s[2] > s[0] > s[1] == 0.0


def test_content_unavailable_without_profile_text_or_job_text():
    assert sg.content_scores("", ["a b c"]) == [None]
    assert sg.content_scores("   ", ["a"]) == [None]
    assert sg.content_scores("sql", ["", "sql analyst"])[0] is None


# ----------------------------------------------------------------- role / location

def test_role_match_by_title_phrase_and_category():
    u = user(roles=["Data Analyst"])
    assert sg.role_match(u, job(1, title="Senior Data Analyst - BI"))[0] == 1.0
    assert sg.role_match(u, job(2, title="Reporting Specialist", cat="Data & Analytics"))[0] == 1.0  # via category
    assert sg.role_match(u, job(3, title="Content Writer", cat="Sales & Marketing"))[0] == 0.0
    assert sg.role_match(user(roles=["Data & Analytics"]), job(4, title="BI Lead", cat="Data & Analytics"))[0] == 1.0


def test_role_match_ignores_substring_and_fallback_category():
    # "ai" must not match inside "Retail"; a default-fallback category is not evidence
    assert sg.role_match(user(roles=["AI"]), job(1, title="Retail Manager", cat="Sales & Marketing"))[0] != 1.0
    fallback = job(2, title="Zebra Wrangler", cat="Software Engineering")
    assert sg.role_match(user(roles=["Software Engineering"]), fallback) == (None, None)


def test_location_match_and_missing_city():
    u = user(locations=["Bangalore", "Remote"])
    assert sg.location_match(u, job(1, city="Bengaluru")) == 1.0
    assert sg.location_match(u, job(2, city="Pune")) == 0.0
    assert sg.location_match(u, job(3, city=None)) is None
    assert sg.location_match(u, job(4, city=None, work_model="Remote")) == 1.0
    assert sg.location_match(user(locations=["Pune"]), job(5, city=None, work_model="Remote")) is None


def test_recency_scores():
    a, b, c = datetime(2026, 1, 1), datetime(2026, 2, 1), datetime(2026, 3, 1)
    assert sg.recency_scores([a, b, c, None]) == [0.0, 0.5, 1.0, None]
    assert sg.recency_scores([a]) == [1.0]


# ----------------------------------------------------------------- hybrid weighting

def test_hybrid_weighting_changes_ranking():
    jobs = [job(1, skills=["sql", "python"], city="Pune"), job(2, skills=["java"], city="Mumbai")]
    u = user(skills=["sql", "python"], locations=["Mumbai"])
    skill_heavy = rank_jobs(u, jobs, HybridWeights(skill=1, content=0, role=0, location=0.1, popularity=0))
    loc_heavy = rank_jobs(u, jobs, HybridWeights(skill=0.1, content=0, role=0, location=1, popularity=0))
    assert [i.job.id for i in skill_heavy.items] == [1, 2]
    assert [i.job.id for i in loc_heavy.items] == [2, 1]


def test_scores_normalised_between_zero_and_one():
    u = user(skills=["sql"], roles=["Data Analyst"], locations=["Mumbai"], text="sql data analyst")
    res = rank_jobs(u, [job(1, skills=["sql"], text="sql data analyst reporting")], HybridWeights())
    assert 0.0 <= res.items[0].score <= 1.0
    assert pytest.approx(sum(res.weights_used.values())) == 1.0


def test_user_side_missing_signal_dropped_and_renormalised():
    res = rank_jobs(user(skills=["sql"]), [job(1, skills=["sql"])], HybridWeights(skill=1, content=0, role=1, location=1, popularity=0))
    assert res.available_signals == ["skill"] and res.weights_used["skill"] == 1.0
    assert res.items[0].components["role"] is None and res.items[0].score == 1.0


# ----------------------------------------------------------------- missing data

def test_missing_job_data_is_never_rewarded():
    u = user(skills=["sql"], locations=["Mumbai"])
    full = job(1, skills=["sql"], city="Mumbai")
    no_skills = job(2, skills=[], city="Mumbai")
    no_city = job(3, skills=["sql"], city=None)
    res = rank_jobs(u, [no_skills, no_city, full], HybridWeights(skill=1, content=0, role=0, location=1, popularity=0))
    by_id = {i.job.id: i for i in res.items}
    assert by_id[1].score == 1.0
    assert by_id[2].score == 0.5 and by_id[2].components["skill"] is None   # not a perfect skill match
    assert by_id[3].score == 0.5 and by_id[3].components["location"] is None  # not a location match
    assert res.items[0].job.id == 1


def test_undated_job_gets_no_popularity():
    res = rank_jobs(user(), [job(1, posted=None), job(2, posted=datetime(2026, 1, 1))], weights_for_strategy("popularity"))
    assert [i.job.id for i in res.items] == [2, 1] and res.items[1].score == 0.0


# ----------------------------------------------------------------- cold start

def test_cold_start_falls_back_to_recency():
    jobs = [job(1, posted=datetime(2026, 1, 1)), job(2, posted=datetime(2026, 3, 1)), job(3, posted=datetime(2026, 2, 1))]
    res = rank_jobs(user(), jobs, HybridWeights())
    assert res.cold_start is True and res.available_signals == ["popularity"]
    assert [i.job.id for i in res.items] == [2, 3, 1]
    assert all(i.evidence.matched_skills == [] for i in res.items)


def test_partial_profile_uses_only_what_it_has():
    res = rank_jobs(user(locations=["Pune"]), [job(1, city="Pune"), job(2, city="Mumbai")], HybridWeights())
    assert res.cold_start is False and set(res.available_signals) == {"location", "popularity"}
    assert res.items[0].job.id == 1


# ----------------------------------------------------------------- explanations

def test_explanation_only_cites_real_signals():
    u = user(skills=["sql", "python"], roles=["Data Analyst"], locations=["Mumbai"], text="sql python analyst")
    res = rank_jobs(u, [job(1, skills=["sql", "excel", "python"], text="sql python analyst data")], HybridWeights())
    reasons = ExplainabilityGenerator.build_reasons(res.items[0].evidence)
    joined = " | ".join(reasons)
    assert "2 of the 3 skills" in joined and "preferred role 'Data Analyst'" in joined and "preferred location (Mumbai)" in joined


def test_no_reason_for_missing_or_zero_signals():
    u = user(skills=["java"], roles=["Data Analyst"], locations=["Pune"])
    res = rank_jobs(u, [job(1, title="Content Writer", cat="Sales & Marketing", city="Mumbai", skills=["sql"])], HybridWeights())
    ex = ExplainabilityGenerator.generate_explanation(res.items[0].evidence)
    assert ex.reasons == [] and ex.role_match is False and ex.location_match is False
    assert "No profile signal matched" in ex.primary_reason


def test_explanation_respects_strategy():
    u = user(skills=["sql"], locations=["Mumbai"])
    res = rank_jobs(u, [job(1, skills=["sql"], city="Mumbai")], weights_for_strategy("skills"))
    reasons = ExplainabilityGenerator.build_reasons(res.items[0].evidence)
    assert len(reasons) == 1 and "skills extracted" in reasons[0]  # location not cited under the skills strategy


def test_recency_reason_for_cold_start():
    res = rank_jobs(user(), [job(1, posted=datetime(2026, 1, 1)), job(2, posted=datetime(2026, 2, 1))], HybridWeights())
    assert "Ranked by recency" in ExplainabilityGenerator.build_reasons(res.items[0].evidence)[0]


def test_content_reason_needs_threshold():
    ev = SignalEvidence(active=frozenset({"content"}), content_score=0.05)
    assert ExplainabilityGenerator.build_reasons(ev) == []
    ev.content_score = 0.4
    assert "similar to your profile" in ExplainabilityGenerator.build_reasons(ev)[0]


# ----------------------------------------------------------------- ranking stability

def test_ranking_deterministic_and_input_order_independent():
    jobs = [job(i, skills=["sql"] if i % 2 else [], city="Pune") for i in range(1, 9)]
    u = user(skills=["sql"], locations=["Pune"])
    a = [i.job.id for i in rank_jobs(u, jobs, HybridWeights()).items]
    b = [i.job.id for i in rank_jobs(u, list(reversed(jobs)), HybridWeights()).items]
    c = [i.job.id for i in rank_jobs(u, jobs, HybridWeights()).items]
    assert a == b == c
    assert [i.rank for i in rank_jobs(u, jobs, HybridWeights()).items] == list(range(1, 9))


def test_limit():
    jobs = [job(i) for i in range(1, 6)]
    assert len(rank_jobs(user(skills=["x"]), jobs, HybridWeights(), limit=2).items) == 2


# ----------------------------------------------------------------- API + ORM integration

def _seed(client):
    for i, (title, city, desc) in enumerate([
        ("Data Analyst", "Mumbai", "Analyse data with SQL and Excel dashboards."),
        ("Backend Developer", "Pune", "Build services in Java and Spring."),
    ]):
        r = client.post("/api/v1/jobs/", json={"job_id": f"rec_{i}", "title": title, "company_name": "Acme",
                                               "city": city, "description": desc})
        assert r.status_code in (200, 201), r.text


def test_recommendation_endpoint_backward_compatible_and_explained(client):
    _seed(client)
    u = client.post("/api/v1/users/", json={
        "email": "rec1@jobintel.ai", "full_name": "R One", "target_role": "Data Analyst",
        "preferred_locations": ["Mumbai"], "skills": [{"skill_name": "sql"}]}).json()
    res = client.get(f"/api/v1/recommendations/{u['id']}")
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == len(body["items"]) >= 2 and body["cold_start"] is False
    top = body["items"][0]
    assert top["job"]["title"] == "Data Analyst" and top["rank"] == 1
    for key in ("match_score", "explanation", "ranking_strategy", "component_scores"):
        assert key in top
    assert "preferred role" in top["explanation"]["primary_reason"]
    assert top["component_scores"]["location"] == 1.0
    assert abs(sum(body["weights_used"].values()) - 1.0) < 1e-9


def test_endpoint_cold_start_user_and_strategies(client):
    _seed(client)
    u = client.post("/api/v1/users/", json={"email": "cold@jobintel.ai", "full_name": "Cold"}).json()
    body = client.get(f"/api/v1/recommendations/{u['id']}").json()
    assert body["cold_start"] is True and body["weights_used"]["popularity"] == 1.0
    for strat in ("skills", "content", "popularity"):
        assert client.get(f"/api/v1/recommendations/{u['id']}?ranking_strategy={strat}").status_code == 200
    assert client.get(f"/api/v1/recommendations/{u['id']}?ranking_strategy=bogus").status_code == 422


def test_endpoint_weight_overrides_validated(client):
    _seed(client)
    u = client.post("/api/v1/users/", json={"email": "w@jobintel.ai", "full_name": "W", "skills": [{"skill_name": "sql"}]}).json()
    ok = client.get(f"/api/v1/recommendations/{u['id']}?w_skill=1&w_content=0&w_role=0&w_location=0&w_popularity=0")
    assert ok.status_code == 200 and ok.json()["weights_used"]["skill"] == 1.0
    assert client.get(f"/api/v1/recommendations/{u['id']}?w_skill=-1").status_code == 422
    zero = "w_skill=0&w_content=0&w_role=0&w_location=0&w_popularity=0&w_behavior=0"
    assert client.get(f"/api/v1/recommendations/{u['id']}?{zero}").status_code == 400
    assert client.get(f"/api/v1/recommendations/{u['id']}?ranking_strategy=skills&w_skill=1").status_code == 400
    assert client.get("/api/v1/recommendations/99999").status_code == 404


def test_recommender_classes_return_ranked_responses(db_session):
    from backend.app.models import Job, User, Skill, UserSkill, JobSkill
    from recommender import HybridRecommender, PopularityRecommender, ContentBasedRecommender
    from recommender.skill_matcher import SkillMatcher

    sql = Skill(name="sql", display_name="SQL")
    db_session.add(sql)
    u = User(email="cls@jobintel.ai", full_name="C", target_role="Data Analyst", preferred_roles=[],
             preferred_locations=[], preferred_work_models=[], preferred_employment_types=[])
    j1 = Job(job_id="c1", source="t", title="Data Analyst", role_category="Data & Analytics", company_name="A",
             city="Pune", description="sql reporting")
    j2 = Job(job_id="c2", source="t", title="Welder", role_category="Software Engineering", company_name="B",
             city="Pune", description="metal")
    db_session.add_all([u, j1, j2])
    db_session.flush()
    db_session.add_all([UserSkill(user_id=u.id, skill_id=sql.id), JobSkill(job_id=j1.id, skill_id=sql.id)])
    db_session.flush()
    db_session.refresh(u)
    db_session.refresh(j1)
    db_session.refresh(j2)
    for rec in (HybridRecommender(), PopularityRecommender(), ContentBasedRecommender()):
        out = rec.recommend(db_session, u, limit=5)
        assert [r.rank for r in out] == list(range(1, len(out) + 1))
    assert HybridRecommender().recommend(db_session, u)[0].job.title == "Data Analyst"
    assert SkillMatcher.match_skills(u, j1) == (1.0, ["sql"], [])
    assert SkillMatcher.match_skills(u, j2) == (0.0, [], [])  # no job skills -> not a match
