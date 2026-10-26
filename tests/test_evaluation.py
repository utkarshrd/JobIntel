"""Tests for recommender.evaluation: metric maths (hand-computed), protocol integrity, determinism."""
import math

import pytest

from recommender import evaluation as ev
from recommender import signals as sg


# ---------------------------------------------------------------- metrics

def test_precision_recall_hand_computed():
    ranked, rel = [1, 2, 3, 4, 5], {2, 5, 9}
    assert ev.precision_at_k(ranked, rel, 5) == pytest.approx(2 / 5)
    assert ev.precision_at_k(ranked, rel, 2) == pytest.approx(1 / 2)
    assert ev.recall_at_k(ranked, rel, 5) == pytest.approx(2 / 3)
    assert ev.recall_at_k(ranked, rel, 1) == 0.0


def test_precision_denominator_is_k_when_list_short():
    assert ev.precision_at_k([1], {1}, 5) == pytest.approx(1 / 5)


def test_ndcg_hand_computed():
    # hits at ranks 2 and 5; 3 relevant, k=5 -> ideal hits at ranks 1,2,3
    dcg = 1 / math.log2(3) + 1 / math.log2(6)
    idcg = 1 + 1 / math.log2(3) + 1 / math.log2(4)
    assert ev.ndcg_at_k([1, 2, 3, 4, 5], {2, 5, 9}, 5) == pytest.approx(dcg / idcg)


def test_ndcg_perfect_and_zero_and_no_relevant():
    assert ev.ndcg_at_k([7, 8, 1], {7, 8}, 3) == pytest.approx(1.0)
    assert ev.ndcg_at_k([1, 2, 3], {9}, 3) == 0.0
    assert ev.ndcg_at_k([1, 2, 3], set(), 3) == 0.0
    assert ev.recall_at_k([1, 2, 3], set(), 3) == 0.0


def test_ndcg_rewards_earlier_hits():
    assert ev.ndcg_at_k([1, 2, 3], {1}, 3) > ev.ndcg_at_k([2, 3, 1], {1}, 3)


def test_invalid_k_rejected():
    for fn in (ev.precision_at_k, ev.recall_at_k, ev.ndcg_at_k):
        with pytest.raises(ValueError):
            fn([1], {1}, 0)


def test_intra_list_diversity():
    sim = {(1, 2): 1.0, (1, 3): 0.0, (2, 3): 0.5}
    assert ev.intra_list_diversity([1, 2], sim, 2) == pytest.approx(0.0)
    assert ev.intra_list_diversity([3, 1, 2], sim, 3) == pytest.approx(1 - (0.0 + 0.5 + 1.0) / 3)
    assert ev.intra_list_diversity([1], sim, 5) is None


# ---------------------------------------------------------------- protocol

def _job(i, role, city, skills):
    return ev.EvalJob(
        features=sg.JobFeatures(id=i, title=f"{role} {i}", city=city, skills=tuple(skills),
                                skill_display={s: s.title() for s in skills}, text=f"{role} {' '.join(skills)} job{i}"),
        query_role=role, query_city=city)


@pytest.fixture
def jobs():
    out, i = [], 1
    for role, city, sk in [("Data Analyst", "Mumbai", ["sql", "excel"]), ("Data Scientist", "Pune", ["python", "ml"])]:
        for _ in range(10):
            out.append(_job(i, role, city, sk))
            i += 1
    return out


def test_split_is_disjoint_complete_and_deterministic():
    ids = list(range(1, 11))
    a, b = ev.split_relevant(ids, 3)
    assert set(a).isdisjoint(b) and sorted(a + b) == ids
    assert ev.split_relevant(ids, 3) == (a, b)


def test_profile_uses_only_seed_jobs_and_min_count():
    seeds = [_job(1, "R", "C", ["sql", "excel"]).features, _job(2, "R", "C", ["sql"]).features]
    p = ev.build_profile(seeds, "R", "C")
    assert p.skills == frozenset({"sql"})          # excel appears once (< 2)
    assert p.locations == ["C"] and p.roles == ["R"]
    assert ev.build_profile(seeds, "R", None).locations == []


def test_trial_never_ranks_seed_jobs_and_scores_only_heldout(jobs):
    by_id = {j.features.id: j.features for j in jobs}
    persona = ev.personas(jobs, "query")[0]
    seed_ids, held = ev.split_relevant(persona["relevant"], 0)
    res = ev.run_trial(by_id, persona, 0, ev.similarity_table([j.features for j in jobs]))
    for name in list(ev.STRATEGIES) + [ev.RANDOM_REFERENCE]:
        assert not set(res[name]["_top"]) & set(seed_ids), f"{name} leaked a seed job"
    assert res["_meta"]["n_seed"] == len(seed_ids) and res["_meta"]["n_heldout"] == len(held)


def test_scenario_role_has_no_location(jobs):
    ps = ev.personas(jobs, "role")
    assert {p["name"] for p in ps} == {"Data Analyst", "Data Scientist"}
    assert all(p["city"] is None for p in ps)


def test_evaluate_is_reproducible_and_complete(jobs):
    a = ev.evaluate(jobs, n_seeds=3)
    b = ev.evaluate(jobs, n_seeds=3)
    assert a == b
    summ = a["scenarios"]["query"]["summary"]
    assert set(summ) == set(ev.STRATEGIES) | {ev.RANDOM_REFERENCE}
    assert "ndcg@10" in summ["hybrid"] and "diversity@5" in summ["hybrid"]


# ---------------------------------------------------------------- verdict

def _trials(adv):
    """adv: per-strategy NDCG@10 constant."""
    return [("p", {s: {"ndcg@10": v} for s, v in adv.items()}) for _ in range(5)]


def test_verdict_clear_winner():
    adv = {"hybrid": 0.9, "skills": 0.5, "content": 0.4, "popularity": 0.1}
    t = _trials(adv)
    v = ev.verdict(t, {"p": adv})
    assert v["clear_winner"] == "hybrid"


def test_verdict_no_winner_when_not_ahead_in_every_persona():
    adv = {"hybrid": 0.9, "skills": 0.5, "content": 0.4, "popularity": 0.1}
    other = {"hybrid": 0.2, "skills": 0.5, "content": 0.4, "popularity": 0.1}
    v = ev.verdict(_trials(adv), {"p": adv, "q": other})
    assert v["clear_winner"] is None and v["leader"] == "hybrid"


def test_verdict_no_winner_when_ci_includes_zero():
    t = [("p", {"hybrid": {"ndcg@10": 0.5 + d}, "skills": {"ndcg@10": 0.5 - d},
                "content": {"ndcg@10": 0.1}, "popularity": {"ndcg@10": 0.1}}) for d in (0.1, -0.1, 0.1, -0.1, 0.0)]
    pm = {"p": {"hybrid": 0.5, "skills": 0.49, "content": 0.1, "popularity": 0.1}}
    assert ev.verdict(t, pm)["clear_winner"] is None


def test_overall_verdict_requires_agreement():
    assert ev.overall_verdict([{"clear_winner": "hybrid"}, {"clear_winner": "hybrid"}])["clear_winner"] == "hybrid"
    assert ev.overall_verdict([{"clear_winner": "hybrid"}, {"clear_winner": None}])["clear_winner"] is None
