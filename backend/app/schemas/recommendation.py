"""
JobIntel - Pydantic Schemas for Recommendations & Explainability
"""

from typing import List, Optional, Dict
from pydantic import BaseModel
from backend.app.schemas.job import JobResponse


class RecommendationExplanation(BaseModel):
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    skill_match_score: float = 0.0
    semantic_similarity_score: float = 0.0
    role_match: bool = False
    location_match: bool = False
    work_model_match: bool = False
    experience_fit: Optional[str] = None  # None = posting states no requirement
    reasons: List[str] = []  # each backed by a signal that was present and used
    primary_reason: str = "Strong match with your profile skills and preferences."


class RecommendedJobResponse(BaseModel):
    job: JobResponse
    match_score: float  # Hybrid overall score between 0.0 and 1.0 (or percentage 0-100)
    explanation: RecommendationExplanation
    ranking_strategy: str = "hybrid"
    rank: int = 0  # 1-based position in this response
    interaction_state: Optional[str] = None  # strongest prior action by this user on the job: applied/saved/clicked/viewed
    # Per-signal scores in [0,1]; null = signal not assessable (missing data) or no user data for it.
    component_scores: Dict[str, Optional[float]] = {}


class RecommendationListResponse(BaseModel):
    user_id: int
    count: int
    items: List[RecommendedJobResponse]
    ranking_strategy: str = "hybrid"
    cold_start: bool = False  # True when there is no profile or interaction signal; ranking is recency only
    weights_used: Dict[str, float] = {}  # normalised over signals available for this user
    # cold_start | profile_based | interaction_informed (interaction_informed only if real interactions were used)
    personalization_mode: str = "cold_start"
    interactions_used: int = 0


class SkillGapItem(BaseModel):
    skill_name: str
    display_name: str
    category: str
    frequency_in_target_role: float  # Percentage of jobs requiring this skill
    user_has_skill: bool
    importance_rank: int


class SkillGapAnalysisResponse(BaseModel):
    target_role: str
    total_jobs_analyzed: int
    matching_skills_count: int
    missing_skills_count: int
    skill_gap_percentage: float
    skills: List[SkillGapItem]
    recommendation_summary: str
