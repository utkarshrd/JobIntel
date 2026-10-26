"""
JobIntel - Hybrid Recommendation Engine
Configurable weighted combination of skill, content, role, location and popularity signals
(see recommender.config.HybridWeights and recommender.ranking for the missing-data rules).
"""

from typing import List, Optional
from backend.app.schemas.recommendation import RecommendedJobResponse
from recommender.base import BaseRecommender
from recommender.config import HybridWeights
from recommender.pipeline import recommend_for_user


class HybridRecommender(BaseRecommender):
    def __init__(self, weights: Optional[HybridWeights] = None):
        self.weights = weights or HybridWeights.from_settings()

    def recommend(self, db, user, limit: int = 20, **kwargs) -> List[RecommendedJobResponse]:
        return recommend_for_user(db, user, "hybrid", limit, self.weights)[0]
