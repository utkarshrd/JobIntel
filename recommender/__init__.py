"""
JobIntel - Recommendation Systems Package
"""

from recommender.base import BaseRecommender
from recommender.popularity import PopularityRecommender
from recommender.skill_matcher import SkillMatcher
from recommender.content_based import ContentBasedRecommender
from recommender.hybrid import HybridRecommender
from recommender.explainability import ExplainabilityGenerator
from recommender.config import HybridWeights

__all__ = [
    "BaseRecommender",
    "PopularityRecommender",
    "SkillMatcher",
    "ContentBasedRecommender",
    "HybridRecommender",
    "ExplainabilityGenerator",
    "HybridWeights",
]
