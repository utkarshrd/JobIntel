"""
JobIntel - Recommendation Explainability Generator

Every sentence is produced from a signal that was actually available AND contributed to the
ranking strategy in use. A reason is never emitted for a missing or zero signal.
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional

from backend.app.schemas.recommendation import RecommendationExplanation
from recommender.behavior import ACTION_LABEL, BehaviorEvidence

# A content similarity below this is too weak to cite as a reason (raw TF-IDF cosine).
CONTENT_REASON_MIN = 0.10


@dataclass
class SignalEvidence:
    active: FrozenSet[str] = frozenset()          # signals with weight > 0 and user-side data
    matched_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    job_skill_count: int = 0
    skill_display: Dict[str, str] = field(default_factory=dict)
    skill_score: Optional[float] = None
    content_score: Optional[float] = None
    role_score: Optional[float] = None
    matched_role: Optional[str] = None
    role_category: Optional[str] = None
    location_score: Optional[float] = None
    city: Optional[str] = None
    recency_score: Optional[float] = None
    behavior: Optional[BehaviorEvidence] = None    # set only when the behavior signal is active


class ExplainabilityGenerator:
    @staticmethod
    def build_reasons(ev: SignalEvidence) -> List[str]:
        reasons: List[str] = []
        if "skill" in ev.active and ev.matched_skills:
            names = ", ".join(ev.skill_display.get(s, s) for s in ev.matched_skills[:4])
            reasons.append(
                f"You have {len(ev.matched_skills)} of the {ev.job_skill_count} skills extracted "
                f"from this posting ({names})"
            )
        if "role" in ev.active and ev.role_score == 1.0:
            target = f" ({ev.role_category})" if ev.role_category else ""
            reasons.append(f"Matches your preferred role '{ev.matched_role}'{target}")
        if "location" in ev.active and ev.location_score == 1.0:
            reasons.append(f"Located in your preferred location ({ev.city or 'Remote'})")
        if "content" in ev.active and ev.content_score is not None and ev.content_score >= CONTENT_REASON_MIN:
            reasons.append(f"Posting text is similar to your profile (TF-IDF similarity {ev.content_score:.2f})")
        b = ev.behavior
        if "behavior" in ev.active and b is not None:
            if b.similar_to_title and (b.similarity or 0) >= CONTENT_REASON_MIN:
                reasons.append(f"Similar to a job you {ACTION_LABEL.get(b.similar_to_action, 'engaged with')} "
                               f"('{b.similar_to_title}', TF-IDF similarity {b.similarity:.2f})")
            if b.shared_skills:
                names = ", ".join(ev.skill_display.get(s, s) for s in b.shared_skills[:4])
                reasons.append(f"Shares skills with jobs you engaged with ({names})")
            if b.role_category:
                reasons.append(f"In a role category you engaged with ({b.role_category})")
            if b.skipped_similar_title:
                reasons.append(f"Ranked lower: similar to a job you skipped ('{b.skipped_similar_title}')")
        if not reasons and "popularity" in ev.active and ev.recency_score is not None:
            reasons.append(f"Ranked by recency: newer than {round(ev.recency_score * 100)}% of dated listings")
        return reasons

    @staticmethod
    def generate_explanation(ev: SignalEvidence, experience_fit: Optional[str] = None) -> RecommendationExplanation:
        reasons = ExplainabilityGenerator.build_reasons(ev)
        primary = ". ".join(reasons) + "." if reasons else \
            "No profile signal matched this job; it is listed only because it is in the candidate pool."
        return RecommendationExplanation(
            matched_skills=ev.matched_skills,
            missing_skills=ev.missing_skills[:5],
            skill_match_score=round(ev.skill_score or 0.0, 2),
            semantic_similarity_score=round(ev.content_score or 0.0, 2),
            role_match=ev.role_score == 1.0,
            location_match=ev.location_score == 1.0,
            work_model_match=False,  # work model is not scored (source does not supply it)
            experience_fit=experience_fit,
            reasons=reasons,
            primary_reason=primary,
        )
