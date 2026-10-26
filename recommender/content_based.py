"""
JobIntel - Content-Based Recommendation Engine (ORM wrapper over recommender.signals).
TF-IDF vectors + cosine similarity between the user's profile text and each job's text.
"""

from typing import List
from backend.app.models.user import User
from backend.app.models.job import Job
from backend.app.schemas.recommendation import RecommendedJobResponse
from recommender.base import BaseRecommender
from recommender.pipeline import profile_from_user, features_from_job, recommend_for_user
from recommender.signals import content_scores


class ContentBasedRecommender(BaseRecommender):
    def calculate_similarity(self, user: User, jobs: List[Job]) -> List[float]:
        """Cosine similarity per job; 0.0 where it cannot be computed (no profile text / empty job)."""
        scores = content_scores(profile_from_user(user).text, [features_from_job(j).text for j in jobs])
        return [s or 0.0 for s in scores]

    def recommend(self, db, user, limit: int = 20, **kwargs) -> List[RecommendedJobResponse]:
        return recommend_for_user(db, user, "content", limit)[0]
