"""
JobIntel - Offline recommender evaluation (pure Python + sklearn; no DB, no API calls).

WHY A PROXY: the project has 0 users and 0 interactions, so there is NO real user feedback to
evaluate against. This module therefore evaluates against a clearly-labelled PROXY built only from
a real, source-supplied signal: the search query (role, city) Adzuna answered when each saved job
was collected (stored in data/raw/*.json). Nothing here is real user feedback.

PROTOCOL ("held-out relevant jobs"), per persona and per random seed:
  persona   = one collection query, e.g. ("Data Analyst", "Mumbai"). Its RELEVANT set is the jobs
              Adzuna returned for it (scenario "query") or for every query with the same search
              role (scenario "role").
  split     = relevant jobs are split in half at random: SEED jobs (pretend history) and HELD-OUT
              jobs (the labels). Seed jobs are removed from the candidate pool.
  profile   = built from the seed jobs only, by a fixed rule (no tuning): skills present in >= 2
              seed jobs; target role = the search role; location = the search city (scenario "query"
              only); profile text = role + skill names (mirrors recommender.pipeline.profile_from_user).
  rank      = each strategy ranks the candidate pool; metrics are computed against HELD-OUT jobs.
Known circularity (reported, not hidden): relevance is derived from the query that also defines the
persona's role/location, so role/location-aware strategies are advantaged in scenario "query".
"""

import glob
import json
import os
import random
import re
from dataclasses import dataclass
from math import log2
from typing import Dict, List, Optional, Sequence, Tuple

from recommender import signals as sg
from recommender.config import STRATEGIES, weights_for_strategy
from recommender.ranking import rank_jobs

MIN_RELEVANT = 10         # personas with fewer relevant jobs are skipped (a split of <10 gives meaningless metrics)
SKILL_MIN_SEED_JOBS = 2   # a skill enters the persona profile if it appears in >= this many seed jobs
KS = (5, 10)
RANDOM_REFERENCE = "random"


# ------------------------------------------------------------------ metrics (binary relevance)

def precision_at_k(ranked: Sequence[int], relevant: set, k: int) -> float:
    """Share of the top-k slots that hold a relevant item (denominator is k, even if fewer ranked)."""
    if k <= 0:
        raise ValueError("k must be positive")
    return sum(1 for x in list(ranked)[:k] if x in relevant) / k


def recall_at_k(ranked: Sequence[int], relevant: set, k: int) -> float:
    """Share of all relevant items found in the top-k. Undefined (0.0) when nothing is relevant."""
    if k <= 0:
        raise ValueError("k must be positive")
    if not relevant:
        return 0.0
    return sum(1 for x in list(ranked)[:k] if x in relevant) / len(relevant)


def ndcg_at_k(ranked: Sequence[int], relevant: set, k: int) -> float:
    """Binary-gain NDCG: DCG = sum rel_i / log2(i+1); IDCG places min(k, |relevant|) hits first."""
    if k <= 0:
        raise ValueError("k must be positive")
    if not relevant:
        return 0.0
    dcg = sum(1.0 / log2(i + 2) for i, x in enumerate(list(ranked)[:k]) if x in relevant)
    ideal = sum(1.0 / log2(i + 2) for i in range(min(k, len(relevant))))
    return dcg / ideal


def intra_list_diversity(ranked: Sequence[int], similarity: Dict[Tuple[int, int], float], k: int) -> Optional[float]:
    """1 - mean pairwise similarity of the top-k items. None if fewer than 2 items."""
    top = list(ranked)[:k]
    if len(top) < 2:
        return None
    sims = [similarity[(min(a, b), max(a, b))] for i, a in enumerate(top) for b in top[i + 1:]]
    return 1.0 - sum(sims) / len(sims)


class LazySimilarity:
    """Dict-like pairwise TF-IDF cosine similarity of job texts, keyed by (id_a, id_b) with a < b.
    Computed on demand from the normalised TF-IDF rows, so memory stays O(N) instead of O(N^2)."""

    def __init__(self, jobs: Sequence[sg.JobFeatures]):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self._m = TfidfVectorizer(stop_words="english").fit_transform([j.text for j in jobs]).tocsr()  # L2-normalised rows
        self._row = {j.id: i for i, j in enumerate(jobs)}

    def __getitem__(self, pair: Tuple[int, int]) -> float:
        a, b = pair
        return float(self._m[self._row[a]].multiply(self._m[self._row[b]]).sum())


def similarity_table(jobs: Sequence[sg.JobFeatures]) -> LazySimilarity:
    """TF-IDF cosine similarity of job texts for every id pair (a<b); used only for diversity."""
    return LazySimilarity(jobs)


# ------------------------------------------------------------------ data

@dataclass
class EvalJob:
    features: sg.JobFeatures
    query_role: str
    query_city: str


def load_saved_adzuna(raw_dir: str, taxonomy_path: Optional[str] = None, run_ts: Optional[str] = None) -> List[EvalJob]:
    """
    Load one saved Adzuna collection (`run_ts`, default: the latest) from `raw_dir` (NO API calls), normalise it with the
    production normalizer, extract skills with the production extractor, and drop content reposts
    (same title+company+city; first seen kept) so a repost of a seed job cannot count as a hit.
    """
    from ingestion.normalizer import JobNormalizer
    from nlp.skill_extractor import SkillExtractor

    files = sorted(glob.glob(os.path.join(raw_dir, "adzuna_raw_*_q*.json")))
    if not files:
        raise FileNotFoundError(f"no adzuna_raw_*_q*.json files in {raw_dir}")
    ts = run_ts or max(re.search(r"adzuna_raw_(\d{8}_\d{6})_", os.path.basename(f)).group(1) for f in files)
    extractor = SkillExtractor(taxonomy_path) if taxonomy_path else SkillExtractor()
    seen_ids, seen_content, out = set(), set(), []
    for path in [f for f in files if f"adzuna_raw_{ts}_" in os.path.basename(f)]:
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        q = rec.get("query") or {}
        for raw in (rec.get("response") or {}).get("results", []):
            norm = JobNormalizer.normalize_adzuna_record(raw)
            if norm is None or norm.job_id in seen_ids:
                continue
            seen_ids.add(norm.job_id)
            key = tuple((x or "").strip().lower() for x in (norm.title, norm.company_name, norm.city))
            if key in seen_content:
                continue
            seen_content.add(key)
            description = norm.description_cleaned or norm.description or ""
            found = extractor.extract_skills(f"{norm.title} {description}", exclude_company=norm.company_name or "")
            names = sorted({s.name.lower() for s in found})
            display = {s.name.lower(): s.display_name for s in found}
            out.append(EvalJob(
                features=sg.JobFeatures(
                    id=len(out) + 1, title=norm.title, role_category=norm.role_category, city=norm.city,
                    skills=tuple(names), skill_display=display,
                    text=f"{norm.title} {norm.role_category or ''} {description}".strip(),
                    posted_at=norm.posted_at, description=description),
                query_role=q.get("what", ""), query_city=q.get("where", "")))
    return out


# ------------------------------------------------------------------ personas / protocol

def build_profile(seed_jobs: Sequence[sg.JobFeatures], role: str, city: Optional[str]) -> sg.UserProfile:
    counts: Dict[str, int] = {}
    display: Dict[str, str] = {}
    for j in seed_jobs:
        for s in set(j.skills):
            counts[s] = counts.get(s, 0) + 1
            display[s] = j.skill_display.get(s, s)
    skills = frozenset(s for s, c in counts.items() if c >= SKILL_MIN_SEED_JOBS)
    shown = {s: display[s] for s in skills}
    text = " ".join([role] + sorted(shown.values())).strip()
    return sg.UserProfile(skills=skills, skill_display=shown, roles=[role],
                          locations=[city] if city else [], text=text)


def personas(jobs: Sequence[EvalJob], scenario: str) -> List[dict]:
    """scenario 'query': one persona per (role, city) query. 'role': one per search role, no location."""
    if scenario == "query":
        keys = sorted({(j.query_role, j.query_city) for j in jobs})
        out = [{"name": f"{r} / {c}", "role": r, "city": c,
                "relevant": [j.features.id for j in jobs if (j.query_role, j.query_city) == (r, c)]} for r, c in keys]
        return [p for p in out if len(p["relevant"]) >= MIN_RELEVANT]
    if scenario == "role":
        out = [{"name": r, "role": r, "city": None,
                "relevant": [j.features.id for j in jobs if j.query_role == r]} for r in sorted({j.query_role for j in jobs})]
        return [p for p in out if len(p["relevant"]) >= MIN_RELEVANT]
    raise ValueError(f"unknown scenario {scenario!r}")


def split_relevant(relevant_ids: Sequence[int], seed: int) -> Tuple[List[int], List[int]]:
    ids = sorted(relevant_ids)
    random.Random(seed).shuffle(ids)
    n_seed = len(ids) // 2
    return ids[:n_seed], ids[n_seed:]


def run_trial(jobs_by_id: Dict[int, sg.JobFeatures], persona: dict, seed: int, sim: dict,
              strategies: Sequence[str] = STRATEGIES, ks: Sequence[int] = KS) -> Dict[str, dict]:
    seed_ids, held_ids = split_relevant(persona["relevant"], seed)
    held = set(held_ids)
    profile = build_profile([jobs_by_id[i] for i in seed_ids], persona["role"], persona["city"])
    pool = [j for i, j in sorted(jobs_by_id.items()) if i not in set(seed_ids)]
    rankings = {}
    for s in strategies:
        res = rank_jobs(profile, pool, weights_for_strategy(s))
        rankings[s] = [it.job.id for it in res.items]
    shuffled = [j.id for j in pool]
    random.Random(f"{seed}-{persona['name']}").shuffle(shuffled)
    rankings[RANDOM_REFERENCE] = shuffled
    out = {}
    for name, ranked in rankings.items():
        m = {}
        for k in ks:
            m[f"precision@{k}"] = precision_at_k(ranked, held, k)
            m[f"recall@{k}"] = recall_at_k(ranked, held, k)
            m[f"ndcg@{k}"] = ndcg_at_k(ranked, held, k)
            m[f"diversity@{k}"] = intra_list_diversity(ranked, sim, k)
        m["_top"] = ranked[:max(ks)]
        out[name] = m
    out["_meta"] = {"n_seed": len(seed_ids), "n_heldout": len(held_ids), "n_profile_skills": len(profile.skills)}
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _std(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def paired_bootstrap_ci(diffs: Sequence[float], n_boot: int = 2000, seed: int = 0) -> Tuple[float, float]:
    """95% percentile CI of the mean of paired differences (resampling trials; deterministic)."""
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]


def evaluate(jobs: Sequence[EvalJob], n_seeds: int = 50, scenarios=("query", "role")) -> dict:
    jobs_by_id = {j.features.id: j.features for j in jobs}
    sim = similarity_table([j.features for j in jobs])
    results = {"n_jobs": len(jobs), "n_seeds": n_seeds, "scenarios": {}}
    for sc in scenarios:
        per_persona, trials = {}, []
        for p in personas(jobs, sc):
            runs = [run_trial(jobs_by_id, p, s, sim) for s in range(n_seeds)]
            per_persona[p["name"]] = {"n_relevant": len(p["relevant"]), "runs": runs}
            trials.extend((p["name"], r) for r in runs)
        names = list(STRATEGIES) + [RANDOM_REFERENCE]
        metrics = [f"{m}@{k}" for k in KS for m in ("precision", "recall", "ndcg", "diversity")]
        summary = {n: {m: {"mean": _mean([r[n][m] for _, r in trials]),
                           "std": _std([r[n][m] for _, r in trials])} for m in metrics} for n in names}
        coverage = {n: len({i for _, r in trials for i in r[n]["_top"]}) / len(jobs) for n in names}
        persona_means = {pn: {n: _mean([r[n]["ndcg@10"] for r in d["runs"]]) for n in names}
                         for pn, d in per_persona.items()}
        results["scenarios"][sc] = {
            "personas": {pn: {"n_relevant": d["n_relevant"],
                              "mean_profile_skills": _mean([r["_meta"]["n_profile_skills"] for r in d["runs"]]),
                              "trials_without_skills": sum(1 for r in d["runs"] if r["_meta"]["n_profile_skills"] == 0)}
                         for pn, d in per_persona.items()},
            "summary": summary, "catalog_coverage@10": coverage, "persona_ndcg@10": persona_means,
            "verdict": verdict(trials, persona_means),
        }
    results["overall_verdict"] = overall_verdict([results["scenarios"][s]["verdict"] for s in scenarios])
    return results


# ------------------------------------------------------------------ verdict (rule fixed in advance)

def verdict(trials: Sequence[Tuple[str, dict]], persona_means: Dict[str, Dict[str, float]]) -> dict:
    """
    A strategy is a CLEAR WINNER only if, among the four strategies (random excluded), it has the
    highest mean NDCG@10 AND is ahead of every other strategy in EVERY persona AND the 95% paired-
    bootstrap CI of its trial-level NDCG@10 advantage over the runner-up excludes 0.
    Otherwise there is no clear winner. (The CI only reflects seed variation within these personas.)
    """
    overall = {s: _mean([r[s]["ndcg@10"] for _, r in trials]) for s in STRATEGIES}
    ranked = sorted(STRATEGIES, key=lambda s: -overall[s])
    best, second = ranked[0], ranked[1]
    in_every_persona = all(all(pm[best] > pm[o] for o in STRATEGIES if o != best) for pm in persona_means.values())
    diffs = [r[best]["ndcg@10"] - r[second]["ndcg@10"] for _, r in trials]
    lo, hi = paired_bootstrap_ci(diffs)
    clear = in_every_persona and lo > 0
    return {"leader": best, "runner_up": second, "leader_mean_ndcg@10": overall[best],
            "runner_up_mean_ndcg@10": overall[second], "ahead_in_every_persona": in_every_persona,
            "ci95_vs_runner_up": [lo, hi], "clear_winner": best if clear else None,
            "ranking": ranked}


def overall_verdict(verdicts: Sequence[dict]) -> dict:
    winners = {v["clear_winner"] for v in verdicts}
    if len(winners) == 1 and None not in winners:
        return {"clear_winner": winners.pop(), "note": "Same clear winner in every scenario (proxy labels only)."}
    return {"clear_winner": None,
            "note": "No strategy is a clear winner across all scenarios under the pre-declared rule."}
