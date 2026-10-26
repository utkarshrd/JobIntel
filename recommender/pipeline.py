"""
JobIntel - Recommendation pipeline (DB adapter around the pure ranking core).

USER PROFILE (+ real interactions) -> candidate jobs -> signals (skill, content, role, location,
popularity, behavior) -> weighted score over available signals -> ranked Top-N -> explanation.
"""

from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, defer, joinedload

from backend.app.models.interaction import Interaction
from backend.app.models.job import Job
from backend.app.models.skill import JobSkill
from backend.app.models.user import User
from backend.app.services.job_service import active_filter
from backend.app.schemas.recommendation import RecommendationListResponse, RecommendedJobResponse
from nlp.entity_extractor import EntityExtractor
from recommender import signals as sg
from recommender.behavior import BehaviorProfile, build_behavior_profile, preference_summary
from recommender.config import HybridWeights, weights_for_strategy
from recommender.explainability import ExplainabilityGenerator
from recommender.ranking import RankingResult, rank_jobs

_STATE = {"apply": "applied", "save": "saved", "click": "clicked", "view": "viewed"}


def profile_from_user(user: User) -> sg.UserProfile:
    skills, display = set(), {}
    for us in (user.skills_rel or []):
        if us.skill_rel:
            skills.add(us.skill_rel.name.lower())
            display[us.skill_rel.name.lower()] = us.skill_rel.display_name
    roles: List[str] = []
    for r in ([user.target_role] if user.target_role else []) + list(user.preferred_roles or []):
        if r and r.strip() and r.strip().lower() not in [x.lower() for x in roles]:
            roles.append(r.strip())
    locations = [loc.strip() for loc in (user.preferred_locations or []) if loc and loc.strip()]
    parts = [user.headline or "", user.summary or "", user.target_role or "",
             " ".join(user.preferred_roles or []), " ".join(sorted(display.values()))]
    return sg.UserProfile(
        skills=frozenset(skills), skill_display=display, roles=roles, locations=locations,
        text=" ".join(p for p in parts if p).strip(), experience_years=user.experience_years,
    )


def features_from_job(job: Job) -> sg.JobFeatures:
    names, display = [], {}
    for js in (job.skills_rel or []):
        if js.skill_rel:
            names.append(js.skill_rel.name.lower())
            display[js.skill_rel.name.lower()] = js.skill_rel.display_name
    description = job.description_cleaned or job.description or ""
    return sg.JobFeatures(
        id=job.id, title=job.title or "", role_category=job.role_category, city=job.city,
        work_model=job.work_model, skills=tuple(sorted(set(names))), skill_display=display,
        text=f"{job.title or ''} {job.role_category or ''} {description}".strip(),
        posted_at=job.posted_at, description=description,
        min_experience_years=job.min_experience_years, ref=job,
    )


def experience_fit(job: sg.JobFeatures, user_years: Optional[float]) -> Optional[str]:
    """Informational only (never scored). None when the posting states no requirement."""
    if job.min_experience_years is not None:
        minimum, origin = job.min_experience_years, "stated in the job record"
    else:
        minimum, _ = EntityExtractor.extract_experience_years(job.description)
        origin = "stated in the posting text"
        if minimum is None:
            return None
    if user_years is None:
        return f"Posting asks for {minimum:g}+ years ({origin})"
    if minimum <= user_years:
        return f"Posting asks for {minimum:g}+ years ({origin}); your profile lists {user_years:g}"
    return f"Posting asks for {minimum:g}+ years ({origin}); your profile lists {user_years:g} (a stretch)"


def _state(behavior: Optional[BehaviorProfile], job_id: int) -> Optional[str]:
    return _STATE.get(behavior.strongest_action.get(job_id, "")) if behavior else None


def to_responses(result: RankingResult, profile: sg.UserProfile, strategy: str,
                 behavior: Optional[BehaviorProfile] = None) -> List[RecommendedJobResponse]:
    from backend.app.api.v1.endpoints.jobs import _format_job_response
    out = []
    for item in result.items:
        expl = ExplainabilityGenerator.generate_explanation(
            item.evidence, experience_fit=experience_fit(item.job, profile.experience_years))
        out.append(RecommendedJobResponse(
            job=_format_job_response(item.job.ref), match_score=round(item.score, 4), explanation=expl,
            ranking_strategy=strategy, rank=item.rank, interaction_state=_state(behavior, item.job.id),
            component_scores={k: (None if v is None else round(v, 4)) for k, v in item.components.items()},
        ))
    return out


def _load_features(db: Session) -> List[sg.JobFeatures]:
    jobs = (db.query(Job).filter(active_filter())
            .options(defer(Job.raw_payload), joinedload(Job.skills_rel).joinedload(JobSkill.skill_rel)).all())
    return [features_from_job(j) for j in jobs]


def load_behavior(db: Session, user: User, features_by_id: Dict[int, sg.JobFeatures]) -> BehaviorProfile:
    """Behavior profile from the user's REAL stored interactions (inactive if there are none)."""
    rows = db.query(Interaction.job_id, Interaction.interaction_type).filter(Interaction.user_id == user.id).all()
    return build_behavior_profile(((r.job_id, r.interaction_type) for r in rows), features_by_id)


def _recommend(db: Session, user: User, strategy: str, limit: int, weights: Optional[HybridWeights]):
    w = weights_for_strategy(strategy, weights)
    features = _load_features(db)
    profile = profile_from_user(user)
    # Behavioral personalization belongs to the hybrid strategy only; the baselines stay pure single-signal rankers.
    behavior = load_behavior(db, user, {f.id: f for f in features}) if strategy == "hybrid" else None
    result = rank_jobs(profile, features, w, limit=limit, behavior=behavior)
    return to_responses(result, profile, strategy, behavior), result, behavior


def recommend_for_user(db: Session, user: User, strategy: str = "hybrid", limit: int = 20,
                       weights: Optional[HybridWeights] = None) -> Tuple[List[RecommendedJobResponse], RankingResult]:
    """Rank ALL stored jobs for the user. `weights` only applies to the hybrid strategy."""
    items, result, _ = _recommend(db, user, strategy, limit, weights)
    return items, result


def recommendation_list(db: Session, user: User, strategy: str = "hybrid", limit: int = 20,
                        weights: Optional[HybridWeights] = None) -> RecommendationListResponse:
    items, result, behavior = _recommend(db, user, strategy, limit, weights)
    used = behavior.interactions_used if behavior and "behavior" in result.available_signals else 0
    return RecommendationListResponse(
        user_id=user.id, count=len(items), items=items, ranking_strategy=strategy,
        cold_start=result.cold_start, weights_used=result.weights_used,
        personalization_mode=result.personalization_mode, interactions_used=used,
    )


def personalization_summary(db: Session, user: User) -> dict:
    """What the system has learned from this user's real interactions, plus the current mode."""
    behavior = load_behavior(db, user, {f.id: f for f in _load_features(db)})
    profile = profile_from_user(user)
    has_profile = bool(profile.skills or profile.text.strip() or profile.roles or profile.locations)
    mode = "interaction_informed" if behavior.active else ("profile_based" if has_profile else "cold_start")
    return {"user_id": user.id, "personalization_mode": mode, "has_profile": has_profile,
            "learned_from_interactions": preference_summary(behavior)}
