"""
JobIntel - Recommendation ranking core (pure Python, no DB).

Score = sum(w_i * s_i) / sum(w_i over signals the USER provided data for).

Missing-data rules:
  * user-side: a signal the user gave no data for (no skills / roles / locations / profile text /
    no real interactions) is dropped and the remaining weights are renormalised. It affects every job equally, so it
    cannot favour any job.
  * job-side: a signal that cannot be assessed for a job (no extracted skills, no city, no date,
    unreliable role) contributes 0 for that job. Missing information is never rewarded.
Ties are broken by job id (ascending) so rankings are deterministic.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from recommender import signals as sg
from recommender.behavior import BehaviorEvidence, BehaviorProfile, behavior_scores
from recommender.config import HybridWeights, SIGNALS
from recommender.explainability import SignalEvidence


@dataclass
class ScoredJob:
    job: sg.JobFeatures
    rank: int
    score: float
    components: Dict[str, Optional[float]]   # None = not assessable (or user gave no data)
    evidence: SignalEvidence


@dataclass
class RankingResult:
    items: List[ScoredJob]
    weights_used: Dict[str, float]      # normalised over available signals; 0 for dropped ones
    available_signals: List[str]        # signals with weight > 0 and user data
    cold_start: bool                    # no personal (profile or behavior) signal available
    personalization_mode: str = "cold_start"   # cold_start | profile_based | interaction_informed


PROFILE_SIGNALS = ("skill", "content", "role", "location")
PERSONAL = PROFILE_SIGNALS + ("behavior",)


def user_signal_availability(profile: sg.UserProfile, behavior: Optional[BehaviorProfile] = None) -> Dict[str, bool]:
    return {
        "skill": bool(profile.skills),
        "content": bool((profile.text or "").strip()),
        "role": any(r.strip() for r in profile.roles),
        "location": any(l.strip() for l in profile.locations),
        "popularity": True,
        "behavior": bool(behavior and behavior.active),
    }


def rank_jobs(profile: sg.UserProfile, jobs: Sequence[sg.JobFeatures], weights: HybridWeights,
              limit: Optional[int] = None, behavior: Optional[BehaviorProfile] = None) -> RankingResult:
    """`behavior` (optional) is learned from the user's real interactions. It is used only when active
    and only where the weights give it a share; jobs the user skipped are then hidden."""
    raw = weights.as_dict()
    avail = user_signal_availability(profile, behavior)
    active = [s for s in SIGNALS if raw[s] > 0 and avail[s]]
    denom = sum(raw[s] for s in active)
    weights_used = {s: (raw[s] / denom if s in active and denom else 0.0) for s in SIGNALS}
    cold_start = not any(s in active for s in PERSONAL)
    mode = ("interaction_informed" if "behavior" in active
            else "cold_start" if cold_start else "profile_based")

    content = sg.content_scores(profile.text, [j.text for j in jobs]) if "content" in active else [None] * len(jobs)
    recency = sg.recency_scores([j.posted_at for j in jobs]) if "popularity" in active else [None] * len(jobs)
    behav = behavior_scores(behavior, jobs) if "behavior" in active else [BehaviorEvidence() for _ in jobs]
    hidden = set(behavior.skipped_ids) if "behavior" in active else set()

    scored = []
    for i, job in enumerate(jobs):
        if job.id in hidden:
            continue
        comp: Dict[str, Optional[float]] = {s: None for s in SIGNALS}
        skill, matched, missing = sg.skill_overlap(profile, job) if avail["skill"] else (None, [], [])
        role, matched_role = sg.role_match(profile, job) if avail["role"] else (None, None)
        comp["skill"] = skill
        comp["content"] = content[i]
        comp["role"] = role
        comp["location"] = sg.location_match(profile, job) if avail["location"] else None
        comp["popularity"] = recency[i]
        comp["behavior"] = behav[i].score

        score = sum(weights_used[s] * (comp[s] or 0.0) for s in active)
        ev = SignalEvidence(
            active=frozenset(active), matched_skills=matched, missing_skills=missing,
            job_skill_count=len(set(job.skills)), skill_display=job.skill_display,
            skill_score=comp["skill"], content_score=comp["content"], role_score=comp["role"],
            matched_role=matched_role, role_category=job.role_category,
            location_score=comp["location"], city=job.city, recency_score=comp["popularity"],
            behavior=behav[i] if "behavior" in active else None,
        )
        scored.append((round(score, 6), job, comp, ev))

    scored.sort(key=lambda t: (-t[0], t[1].id))
    if limit:
        scored = scored[:limit]
    items = [ScoredJob(job=j, rank=r, score=s, components=c, evidence=e)
             for r, (s, j, c, e) in enumerate(scored, start=1)]
    return RankingResult(items=items, weights_used=weights_used, available_signals=active, cold_start=cold_start,
                         personalization_mode=mode)
