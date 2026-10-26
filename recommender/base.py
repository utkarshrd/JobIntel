"""
JobIntel - Abstract Base Recommender
"""

from abc import ABC, abstractmethod
from typing import List
from sqlalchemy.orm import Session
from backend.app.models.user import User
from backend.app.schemas.recommendation import RecommendedJobResponse


class BaseRecommender(ABC):
    @abstractmethod
    def recommend(
        self,
        db: Session,
        user: User,
        limit: int = 20,
        **kwargs
    ) -> List[RecommendedJobResponse]:
        """
        Generate ranked recommendations for the target user.
        """
        pass
