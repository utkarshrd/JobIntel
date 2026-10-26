"""
JobIntel - Baseline Popularity Recommender
Ranks by posting recency (percentile of posting date). No interaction data exists yet, so this
is a recency proxy for popularity; undated jobs score 0.
"""

from typing import List
from backend.app.schemas.recommendation import RecommendedJobResponse
from recommender.base import BaseRecommender
from recommender.pipeline import recommend_for_user


class PopularityRecommender(BaseRecommender):
    def recommend(self, db, user, limit: int = 20, **kwargs) -> List[RecommendedJobResponse]:
        return recommend_for_user(db, user, "popularity", limit)[0]
