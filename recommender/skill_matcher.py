"""
JobIntel - Skill Matching Recommendation Signal (ORM wrapper over recommender.signals).
"""

from typing import List, Tuple
from backend.app.models.user import User
from backend.app.models.job import Job
from recommender.pipeline import profile_from_user, features_from_job
from recommender.signals import skill_overlap


class SkillMatcher:
    @staticmethod
    def match_skills(user: User, job: Job) -> Tuple[float, List[str], List[str]]:
        """
        (score, matched, missing). Score = matched / job skills. A job with no extracted skills
        scores 0.0 with empty lists: absent skills are not a match. (The ranker itself treats
        this case as 'not assessable'; this helper reports it as 0.0.)
        """
        score, matched, missing = skill_overlap(profile_from_user(user), features_from_job(job))
        return round(score or 0.0, 3), matched, missing
