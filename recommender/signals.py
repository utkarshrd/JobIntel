"""
JobIntel - Recommendation signals (pure functions over plain data; no DB, no pydantic).

Convention: a signal returns None when it cannot be assessed (missing data). None is never
treated as a match. `ranking.py` decides how None is handled when combining signals.
"""

import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from nlp.classifier import JobRoleClassifier, DEFAULT_CONFIDENCE, is_default_fallback

CITY_ALIASES = {"bangalore": "bengaluru", "gurgaon": "gurugram", "bombay": "mumbai"}


@dataclass
class UserProfile:
    """Only what the user actually provided. Empty collections mean 'not provided'."""
    skills: frozenset = frozenset()             # canonical skill names (lowercase)
    skill_display: Dict[str, str] = field(default_factory=dict)
    roles: List[str] = field(default_factory=list)       # target_role + preferred_roles
    locations: List[str] = field(default_factory=list)   # preferred_locations
    text: str = ""                                       # headline/summary/roles/skills
    experience_years: Optional[float] = None


@dataclass
class JobFeatures:
    id: int
    title: str
    role_category: Optional[str] = None
    city: Optional[str] = None
    work_model: Optional[str] = None
    skills: Tuple[str, ...] = ()
    skill_display: Dict[str, str] = field(default_factory=dict)
    text: str = ""
    posted_at: Optional[datetime] = None
    description: str = ""
    min_experience_years: Optional[float] = None
    ref: object = None  # original object (ORM job) for building responses


def norm_city(city: Optional[str]) -> str:
    c = (city or "").strip().lower()
    return CITY_ALIASES.get(c, c)


# ----------------------------------------------------------------------- skill

def skill_overlap(profile: UserProfile, job: JobFeatures) -> Tuple[Optional[float], List[str], List[str]]:
    """
    (score, matched, missing). score = matched / job skills, i.e. how much of what the posting
    lists the user has. None when the job has no extracted skills (not 'perfect', not 'zero').
    `missing` is only meaningful (and only returned) when the user provided skills.
    """
    if not job.skills:
        return None, [], []
    job_skills = sorted(set(job.skills))
    matched = [s for s in job_skills if s in profile.skills]
    missing = [s for s in job_skills if s not in profile.skills] if profile.skills else []
    return len(matched) / len(job_skills), matched, missing


# ----------------------------------------------------------------------- role

def _phrase_in(phrase: str, text: str) -> bool:
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text))


def role_match(profile: UserProfile, job: JobFeatures) -> Tuple[Optional[float], Optional[str]]:
    """
    1.0 if a preferred role matches the job (whole-phrase in the title, or the role maps to the
    job's role category through the shared classifier); 0.0 if the job is assessable and nothing
    matches; None if the job's role cannot be assessed. Returns (score, the matching user role).
    A category that is only the classifier's no-match default is not evidence and is ignored.
    """
    title = (job.title or "").lower()
    category_reliable = bool(job.role_category) and not is_default_fallback(job.title, job.role_category)
    for role in profile.roles:
        r = role.strip().lower()
        if not r:
            continue
        if _phrase_in(r, title):
            return 1.0, role
        if category_reliable:
            if r == job.role_category.lower():
                return 1.0, role
            cat, conf = JobRoleClassifier.classify(role)
            if conf > DEFAULT_CONFIDENCE and cat == job.role_category:
                return 1.0, role
    if not title:
        return None, None
    # A job whose category is unreliable and whose title did not match: cannot say it mismatches.
    return (0.0, None) if category_reliable else (None, None)


# ----------------------------------------------------------------------- location

def location_match(profile: UserProfile, job: JobFeatures) -> Optional[float]:
    """1.0 city is preferred (or user wants Remote and the job text says remote), 0.0 city known and
    not preferred, None if the job has no city and is not remote."""
    prefs = {norm_city(l) for l in profile.locations}
    is_remote = (job.work_model or "").strip().lower() == "remote"
    if is_remote and "remote" in prefs:
        return 1.0
    city = norm_city(job.city)
    if not city:
        return None
    return 1.0 if city in prefs else 0.0


# ----------------------------------------------------------------------- content

_CORPUS_CACHE: list = []   # [(texts_tuple, vectorizer, matrix)], newest first, at most 2 entries


def corpus_tfidf(job_texts: Sequence[str]):
    """
    (vectorizer, matrix) fitted on the job corpus. Fitting is the expensive part and depends only on the job
    texts, so the last fits are cached in-process and reused while the corpus is unchanged. Results are identical
    to refitting. Raises ValueError on an empty vocabulary.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    texts = tuple(t or "" for t in job_texts)
    for cached, vec, mat in _CORPUS_CACHE:
        if cached == texts:
            return vec, mat
    vec = TfidfVectorizer(stop_words="english", max_features=5000)
    mat = vec.fit_transform(texts)
    _CORPUS_CACHE.insert(0, (texts, vec, mat))
    del _CORPUS_CACHE[2:]
    return vec, mat


def content_scores(profile_text: str, job_texts: Sequence[str]) -> List[Optional[float]]:
    """
    TF-IDF cosine similarity between the profile text and each job text. The vocabulary/IDF is fit
    on the job corpus only (the user text does not influence term weights). Raw cosine is returned
    (not rescaled), so a poor best match stays low. None where no score can be computed.
    """
    from sklearn.metrics.pairwise import cosine_similarity

    n = len(job_texts)
    if not (profile_text or "").strip() or n == 0:
        return [None] * n
    try:
        vec, job_m = corpus_tfidf(job_texts)
        sims = cosine_similarity(vec.transform([profile_text]), job_m)[0]
    except ValueError:  # empty vocabulary
        return [None] * n
    return [None if not (job_texts[i] or "").strip() else round(float(sims[i]), 4) for i in range(n)]


# ----------------------------------------------------------------------- popularity (recency proxy)

def recency_scores(posted: Sequence[Optional[datetime]]) -> List[Optional[float]]:
    """Percentile of posting date among dated jobs (newest -> 1.0). None for undated jobs."""
    dated = sorted(d for d in posted if d is not None)
    n = len(dated)
    out: List[Optional[float]] = []
    for d in posted:
        if d is None:
            out.append(None)
        elif n == 1:
            out.append(1.0)
        else:
            lo, hi = bisect_left(dated, d), bisect_right(dated, d)
            out.append(round((lo + (hi - lo - 1) / 2) / (n - 1), 4))
    return out
