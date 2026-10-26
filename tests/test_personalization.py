"""
Behavioral personalization tests. All interactions here are created inside the tests to exercise
the mechanism; nothing is seeded into the application or used for the evaluation report.
"""

import pytest

from recommender import signals as sg
from recommender.behavior import (MIN_POSITIVE_MASS, NET_MAX, behavior_scores, build_behavior_profile,
                                  preference_summary)
from recommender.config import HybridWeights
from recommender.ranking import rank_jobs


def job(i, title, cat, city, skills, text=None):
    return sg.JobFeatures(id=i, title=title, role_category=cat, city=city, skills=tuple(skills),
                          skill_display={s: s.upper() for s in skills}, text=text or f"{title} {' '.join(skills)}")


JOBS = [
    job(1, "Data Analyst", "Data & Analytics", "Mumbai", ["sql", "excel"], "data analyst sql excel dashboards reporting"),
    job(2, "BI Analyst", "Data & Analytics", "Mumbai", ["sql", "tableau"], "bi analyst sql tableau dashboards reporting"),
    job(3, "Java Developer", "Software Engineering", "Pune", ["java", "spring"], "java developer spring microservices backend"),
    job(4, "Backend Engineer", "Software Engineering", "Pune", ["java", "docker"], "backend engineer java docker services"),
]
BY_ID = {j.id: j for j in JOBS}
EMPTY = sg.UserProfile()


def test_no_interactions_means_inactive_and_no_effect():
    bp = build_behavior_profile([], BY_ID)
    assert not bp.active and bp.interactions_used == 0
    assert all(e.score is None for e in behavior_scores(bp, JOBS))
    with_b = rank_jobs(EMPTY, JOBS, HybridWeights(), behavior=bp)
    without = rank_jobs(EMPTY, JOBS, HybridWeights())
    assert [i.job.id for i in with_b.items] == [i.job.id for i in without.items]
    assert with_b.personalization_mode == "cold_start" and with_b.cold_start


def test_weak_evidence_does_not_activate_but_enough_does():
    assert not build_behavior_profile([(1, "view")], BY_ID).active                     # 0.25 < 1.0
    assert build_behavior_profile([(1, "view")] * 4, BY_ID).positive_mass == MIN_POSITIVE_MASS
    assert build_behavior_profile([(1, "save")], BY_ID).active
    assert build_behavior_profile([(1, "apply")], BY_ID).active


def test_net_weight_is_clamped_and_unknown_events_ignored():
    bp = build_behavior_profile([(1, "view")] * 100 + [(999, "save"), (1, "bogus")], BY_ID)
    assert bp.net_weight == {1: NET_MAX} and bp.interactions_used == 100


def test_save_then_skip_cancels_out():
    bp = build_behavior_profile([(1, "save"), (1, "skip")], BY_ID)
    assert bp.net_weight[1] == 0 and not bp.liked_ids and not bp.skipped_ids


def test_saved_job_influences_similar_jobs_not_unrelated_ones():
    bp = build_behavior_profile([(1, "save")], BY_ID)
    res = rank_jobs(EMPTY, JOBS, HybridWeights(), behavior=bp)
    order = [i.job.id for i in res.items]
    assert res.personalization_mode == "interaction_informed" and not res.cold_start
    assert order.index(2) < order.index(3) and order.index(2) < order.index(4)   # similar analyst job beats Java jobs
    top = {i.job.id: i for i in res.items}[2]
    assert top.evidence.behavior.similar_to_title == "Data Analyst"
    assert "sql" in top.evidence.behavior.shared_skills


def test_job_is_not_its_own_behavior_evidence():
    bp = build_behavior_profile([(1, "save")], BY_ID)
    ev = behavior_scores(bp, JOBS)[0]
    assert ev.similar_to_id is None and ev.similarity is None


def test_skipped_jobs_hidden_and_similar_jobs_penalised():
    bp = build_behavior_profile([(1, "save"), (3, "skip")], BY_ID)
    res = rank_jobs(EMPTY, JOBS, HybridWeights(), behavior=bp)
    ids = [i.job.id for i in res.items]
    assert 3 not in ids
    ev4 = {i.job.id: i for i in res.items}[4].evidence.behavior
    assert ev4.penalty > 0 and ev4.skipped_similar_title == "Java Developer"


def test_skip_only_does_not_activate_behavior():
    bp = build_behavior_profile([(3, "skip")], BY_ID)
    res = rank_jobs(EMPTY, JOBS, HybridWeights(), behavior=bp)
    assert not bp.active and len(res.items) == 4 and res.personalization_mode == "cold_start"


def test_profile_based_vs_interaction_informed_modes():
    prof = sg.UserProfile(skills=frozenset({"sql"}), roles=["Data Analyst"], text="Data Analyst SQL")
    assert rank_jobs(prof, JOBS, HybridWeights()).personalization_mode == "profile_based"
    bp = build_behavior_profile([(2, "apply")], BY_ID)
    res = rank_jobs(prof, JOBS, HybridWeights(), behavior=bp)
    assert res.personalization_mode == "interaction_informed" and res.weights_used["behavior"] > 0
    assert sum(res.weights_used.values()) == pytest.approx(1.0)


def test_behavior_weight_zero_disables_it():
    bp = build_behavior_profile([(1, "save")], BY_ID)
    res = rank_jobs(EMPTY, JOBS, HybridWeights(behavior=0), behavior=bp)
    assert res.personalization_mode == "cold_start"


def test_preference_summary_reports_only_learned_data():
    bp = build_behavior_profile([(1, "save"), (2, "view")], BY_ID)
    s = preference_summary(bp)
    assert s["counts_by_type"] == {"save": 1, "view": 1} and s["active"]
    assert s["skills"][0]["name"] == "SQL" and s["role_categories"][0]["name"] == "Data & Analytics"
    assert preference_summary(build_behavior_profile([], BY_ID))["skills"] == []


def test_ranking_deterministic_with_behavior():
    bp = build_behavior_profile([(1, "save"), (4, "click")], BY_ID)
    a = [i.job.id for i in rank_jobs(EMPTY, JOBS, HybridWeights(), behavior=bp).items]
    b = [i.job.id for i in rank_jobs(EMPTY, list(reversed(JOBS)), HybridWeights(), behavior=bp).items]
    assert a == b


# ---------------------------------------------------------------------------- API integration

def _setup(client, email="p1@jobintel.ai", **user_kw):
    ids = []
    for i, (title, city, desc) in enumerate([
        ("Data Analyst", "Mumbai", "Analyse data with SQL and Excel dashboards for reporting."),
        ("BI Analyst", "Mumbai", "Build SQL and Tableau dashboards for reporting."),
        ("Java Developer", "Pune", "Build backend services in Java and Spring."),
    ]):
        r = client.post("/api/v1/jobs/", json={"job_id": f"pz_{email}_{i}", "title": title, "company_name": f"Co{i}",
                                               "city": city, "description": desc})
        assert r.status_code in (200, 201), r.text
        ids.append(r.json()["id"])
    u = client.post("/api/v1/users/", json={"email": email, "full_name": "P", **user_kw})
    assert u.status_code == 201, u.text
    return u.json()["id"], ids


def test_interaction_api_validates_and_persists(client):
    uid, jobs = _setup(client, "p2@jobintel.ai")
    ok = client.post("/api/v1/users/interactions", json={"user_id": uid, "job_id": jobs[0], "interaction_type": "Save"})
    assert ok.status_code == 201 and ok.json()["interaction_type"] == "save"
    assert client.post("/api/v1/users/interactions",
                       json={"user_id": uid, "job_id": jobs[0], "interaction_type": "like"}).status_code == 422
    assert client.post("/api/v1/users/interactions",
                       json={"user_id": uid, "job_id": 999999, "interaction_type": "view"}).status_code == 404
    assert client.post("/api/v1/users/interactions",
                       json={"user_id": 999999, "job_id": jobs[0], "interaction_type": "view"}).status_code == 404
    hist = client.get(f"/api/v1/users/{uid}/interactions").json()
    assert [h["interaction_type"] for h in hist] == ["save"]
    assert client.get("/api/v1/users/999999/interactions").status_code == 404


def test_cold_start_user_then_interaction_informed(client):
    uid, jobs = _setup(client, "p3@jobintel.ai")                       # no profile at all
    before = client.get(f"/api/v1/recommendations/{uid}").json()
    assert before["personalization_mode"] == "cold_start" and before["cold_start"] is True
    assert before["interactions_used"] == 0
    assert client.get(f"/api/v1/users/{uid}/personalization").json()["personalization_mode"] == "cold_start"

    client.post("/api/v1/users/interactions", json={"user_id": uid, "job_id": jobs[0], "interaction_type": "save"})
    after = client.get(f"/api/v1/recommendations/{uid}").json()
    assert after["personalization_mode"] == "interaction_informed" and after["cold_start"] is False
    assert after["interactions_used"] == 1 and after["weights_used"]["behavior"] > 0
    by_title = {i["job"]["title"]: i for i in after["items"]}
    assert by_title["Data Analyst"]["interaction_state"] == "saved"
    bi = by_title["BI Analyst"]
    assert any("you saved" in r for r in bi["explanation"]["reasons"])
    assert [i["job"]["title"] for i in after["items"]].index("BI Analyst") < \
        [i["job"]["title"] for i in after["items"]].index("Java Developer")
    summ = client.get(f"/api/v1/users/{uid}/personalization").json()
    assert summ["personalization_mode"] == "interaction_informed"
    assert summ["learned_from_interactions"]["counts_by_type"] == {"save": 1}


def test_profile_based_user_and_baseline_strategies_ignore_behavior(client):
    uid, jobs = _setup(client, "p4@jobintel.ai", target_role="Data Analyst", skills=[{"skill_name": "sql"}])
    assert client.get(f"/api/v1/recommendations/{uid}").json()["personalization_mode"] == "profile_based"
    client.post("/api/v1/users/interactions", json={"user_id": uid, "job_id": jobs[2], "interaction_type": "apply"})
    assert client.get(f"/api/v1/recommendations/{uid}").json()["personalization_mode"] == "interaction_informed"
    for strat in ("skills", "content", "popularity"):
        body = client.get(f"/api/v1/recommendations/{uid}?ranking_strategy={strat}").json()
        assert body["personalization_mode"] != "interaction_informed" and body["weights_used"]["behavior"] == 0.0


def test_skipped_job_disappears_from_hybrid_feed(client):
    uid, jobs = _setup(client, "p5@jobintel.ai", target_role="Data Analyst")
    client.post("/api/v1/users/interactions", json={"user_id": uid, "job_id": jobs[0], "interaction_type": "save"})
    client.post("/api/v1/users/interactions", json={"user_id": uid, "job_id": jobs[2], "interaction_type": "skip"})
    titles = [i["job"]["title"] for i in client.get(f"/api/v1/recommendations/{uid}").json()["items"]]
    assert "Java Developer" not in titles
