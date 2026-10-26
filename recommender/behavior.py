"""
JobIntel - Behavioral personalization (pure functions over plain data; no DB).

Learns ONLY from interactions users actually generated (view/click/save/apply/skip). Nothing is
seeded or simulated; with no interactions the profile is inactive and ranking is unchanged.

Method (deliberately simple and explainable):
  1. Each interaction type has a fixed weight (INTERACTION_WEIGHTS). Per job the weights are summed
     and clamped, so spamming "view" cannot dominate. Net > 0 = liked, net < 0 = disliked.
  2. From liked jobs we build preference tables (skill / role category / city), weighted and scaled
     to [0, 1], plus the list of liked jobs for text similarity.
  3. A candidate's behavior score = mean of the sub-affinities that can be assessed:
       skill  : mean preference of the job's skills        (None if the job has no skills)
       role   : preference for the job's role category     (None if the category is only the default)
       city   : preference for the job's city              (None if no city)
       content: best TF-IDF cosine to ANOTHER liked job    (the job itself is never its own evidence)
     minus a penalty = SKIP_PENALTY x best TF-IDF cosine to a skipped job. Jobs the user skipped are
     hidden from the hybrid feed.
  4. The signal is ACTIVE only once positive evidence reaches MIN_POSITIVE_MASS (e.g. one save, or
     four views). Below that the profile is "not enough evidence" and is ignored.
No time decay, no collaborative filtering, no learned model: interaction volume does not justify them.
"""

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from nlp.classifier import is_default_fallback
from recommender.signals import JobFeatures, norm_city

INTERACTION_WEIGHTS: Dict[str, float] = {"view": 0.25, "click": 0.5, "save": 1.0, "apply": 1.5, "skip": -1.0}
INTERACTION_TYPES = tuple(INTERACTION_WEIGHTS)
NET_MIN, NET_MAX = -1.5, 2.0       # per-job clamp
MIN_POSITIVE_MASS = 1.0            # total positive net weight needed to activate the behavior signal
SKIP_PENALTY = 0.5
PENALTY_REASON_MIN = 0.15          # similarity to a skipped job needed to mention it
ACTION_LABEL = {"view": "viewed", "click": "clicked", "save": "saved", "apply": "applied to", "skip": "skipped"}


@dataclass
class BehaviorProfile:
    net_weight: Dict[int, float] = field(default_factory=dict)       # job_id -> clamped net weight
    strongest_action: Dict[int, str] = field(default_factory=dict)   # job_id -> strongest positive type
    counts: Dict[str, int] = field(default_factory=dict)             # interactions used, by type
    positive_mass: float = 0.0
    skill_pref: Dict[str, float] = field(default_factory=dict)
    skill_display: Dict[str, str] = field(default_factory=dict)
    role_pref: Dict[str, float] = field(default_factory=dict)
    city_pref: Dict[str, float] = field(default_factory=dict)
    liked_ids: List[int] = field(default_factory=list)
    skipped_ids: List[int] = field(default_factory=list)
    titles: Dict[int, str] = field(default_factory=dict)

    @property
    def interactions_used(self) -> int:
        return sum(self.counts.values())

    @property
    def active(self) -> bool:
        return self.positive_mass >= MIN_POSITIVE_MASS


def _scaled(d: Dict[str, float]) -> Dict[str, float]:
    top = max(d.values(), default=0.0)
    return {k: round(v / top, 4) for k, v in d.items()} if top > 0 else {}


def build_behavior_profile(events: Iterable[Tuple[int, str]], jobs_by_id: Dict[int, JobFeatures]) -> BehaviorProfile:
    """events = (job_id, interaction_type). Events for unknown jobs / unknown types are ignored."""
    bp = BehaviorProfile()
    raw: Dict[int, float] = {}
    best: Dict[int, Tuple[float, str]] = {}
    for job_id, itype in events:
        itype = (itype or "").lower()
        if itype not in INTERACTION_WEIGHTS or job_id not in jobs_by_id:
            continue
        bp.counts[itype] = bp.counts.get(itype, 0) + 1
        w = INTERACTION_WEIGHTS[itype]
        raw[job_id] = raw.get(job_id, 0.0) + w
        if w > 0 and w > best.get(job_id, (0.0, ""))[0]:
            best[job_id] = (w, itype)
    bp.net_weight = {j: max(NET_MIN, min(NET_MAX, v)) for j, v in raw.items()}
    bp.strongest_action = {j: t for j, (_, t) in best.items()}
    bp.liked_ids = sorted(j for j, v in bp.net_weight.items() if v > 0)
    bp.skipped_ids = sorted(j for j, v in bp.net_weight.items() if v < 0)
    bp.positive_mass = round(sum(bp.net_weight[j] for j in bp.liked_ids), 4)
    bp.titles = {j: jobs_by_id[j].title for j in bp.liked_ids + bp.skipped_ids}

    skills: Dict[str, float] = {}
    roles: Dict[str, float] = {}
    cities: Dict[str, float] = {}
    for j in bp.liked_ids:
        w, job = bp.net_weight[j], jobs_by_id[j]
        for s in set(job.skills):
            skills[s] = skills.get(s, 0.0) + w
            bp.skill_display[s] = job.skill_display.get(s, s)
        if job.role_category and not is_default_fallback(job.title, job.role_category):
            roles[job.role_category] = roles.get(job.role_category, 0.0) + w
        if norm_city(job.city):
            cities[norm_city(job.city)] = cities.get(norm_city(job.city), 0.0) + w
    bp.skill_pref, bp.role_pref, bp.city_pref = _scaled(skills), _scaled(roles), _scaled(cities)
    return bp


@dataclass
class BehaviorEvidence:
    score: Optional[float] = None
    similar_to_id: Optional[int] = None
    similar_to_title: Optional[str] = None
    similar_to_action: Optional[str] = None
    similarity: Optional[float] = None
    shared_skills: List[str] = field(default_factory=list)   # canonical names, strongest preference first
    role_category: Optional[str] = None                      # set when the role preference contributed
    city: Optional[str] = None                               # set when the city preference contributed
    penalty: float = 0.0
    skipped_similar_title: Optional[str] = None


def behavior_scores(bp: BehaviorProfile, jobs: Sequence[JobFeatures]) -> List[BehaviorEvidence]:
    """One BehaviorEvidence per job (same order). All scores None when the profile is not active."""
    out = [BehaviorEvidence() for _ in jobs]
    if not bp.active:
        return out

    sims: Dict[int, List[float]] = {}
    ref_ids = [j for j in bp.liked_ids + bp.skipped_ids if any(x.id == j for x in jobs)]
    if ref_ids:
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            from recommender.signals import corpus_tfidf
            _, m = corpus_tfidf([j.text for j in jobs])
            pos = {j.id: i for i, j in enumerate(jobs)}
            for rid in ref_ids:
                sims[rid] = [float(v) for v in cosine_similarity(m[pos[rid]], m)[0]]
        except ValueError:   # empty vocabulary
            sims = {}

    for i, job in enumerate(jobs):
        ev, parts = out[i], []
        if job.skills:
            prefs = [(bp.skill_pref.get(s, 0.0), s) for s in set(job.skills)]
            parts.append(sum(p for p, _ in prefs) / len(prefs))
            ev.shared_skills = [s for p, s in sorted(prefs, key=lambda t: (-t[0], t[1])) if p > 0][:4]
        if job.role_category and not is_default_fallback(job.title, job.role_category):
            p = bp.role_pref.get(job.role_category, 0.0)
            parts.append(p)
            if p > 0:
                ev.role_category = job.role_category
        if norm_city(job.city):
            p = bp.city_pref.get(norm_city(job.city), 0.0)
            parts.append(p)
            if p > 0:
                ev.city = job.city
        liked = [(sims[j][i] * min(1.0, bp.net_weight[j]), j) for j in bp.liked_ids if j in sims and j != job.id]
        if liked:
            sim, j = max(liked)
            parts.append(sim)
            ev.similarity, ev.similar_to_id = round(sim, 4), j
            ev.similar_to_title, ev.similar_to_action = bp.titles[j], bp.strongest_action.get(j)
        skipped = [(sims[j][i], j) for j in bp.skipped_ids if j in sims and j != job.id]
        if skipped:
            sim, j = max(skipped)
            ev.penalty = round(SKIP_PENALTY * sim, 4)
            if sim >= PENALTY_REASON_MIN:
                ev.skipped_similar_title = bp.titles[j]
        if parts:
            ev.score = round(max(0.0, sum(parts) / len(parts) - ev.penalty), 4)
        elif ev.penalty:
            ev.score = 0.0
    return out


def preference_summary(bp: BehaviorProfile, top_n: int = 8) -> Dict[str, object]:
    """Human-readable view of what was learned (for the profile page / API)."""
    top = lambda d, n=top_n: [{"name": k, "preference": v} for k, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]
    return {
        "interactions_used": bp.interactions_used,
        "counts_by_type": dict(sorted(bp.counts.items())),
        "positive_evidence": bp.positive_mass,
        "evidence_needed": MIN_POSITIVE_MASS,
        "active": bp.active,
        "skipped_jobs": len(bp.skipped_ids),
        "skills": [{"name": bp.skill_display.get(k, k), "preference": v}
                   for k, v in sorted(bp.skill_pref.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]],
        "role_categories": top(bp.role_pref),
        "cities": top(bp.city_pref),
    }
