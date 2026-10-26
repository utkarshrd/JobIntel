"""
JobIntel - Job Role Classification Engine (single source of truth)

Maps a job to one of the 10 role domains. Used by ingestion (title only) and
available to any other component. Keyword matching is whole-word/phrase based
so short tokens such as "ml" never match inside words like "HTML".
"""

import re
from functools import lru_cache
from typing import Dict, List, Tuple

# (keyword, weight). Specific role phrases weigh 3; generic words ("engineer",
# "developer") weigh 1 so they only decide the outcome when nothing specific matches.
ROLE_KEYWORDS: Dict[str, List[Tuple[str, int]]] = {
    "AI & Machine Learning": [
        ("data scientist", 3), ("data science", 3), ("machine learning", 3), ("ml", 3),
        ("ai engineer", 3), ("ai", 2), ("deep learning", 3), ("nlp", 3), ("computer vision", 3),
        ("llm", 3), ("neural networks", 3), ("pytorch", 3), ("tensorflow", 3), ("generative ai", 3), ("genai", 3),
        ("data scientists", 3), ("ml engineer", 3), ("ai/ml", 3), ("applied scientist", 3), ("research scientist", 3),
    ],
    "Data & Analytics": [
        ("data analyst", 3), ("data engineer", 3), ("data engineering", 3), ("bi analyst", 3), ("bi developer", 3), ("analytics", 3),
        ("analytics engineer", 3), ("business intelligence", 3), ("business analyst", 3),
        ("data analysts", 3), ("data quality", 3), ("data governance", 3), ("data management", 3), ("data analysis", 3),
        ("reporting analyst", 3), ("data product", 3), ("data architect", 3), ("master data", 3), ("product analyst", 3),
        ("data", 1), ("analyst", 1),
        ("sql developer", 3), ("sql analyst", 3), ("power bi", 3), ("tableau", 3),
        ("data visualization", 3), ("data warehousing", 3), ("etl", 3),
    ],
    "Finance & Banking": [
        ("finance", 3), ("accountant", 3), ("accounting", 3), ("financial", 3), ("risk analyst", 3), ("credit", 3), ("equity", 3),
        ("investment", 3), ("portfolio", 3), ("chartered accountant", 3), ("wealth management", 3),
        ("equities", 3), ("quantitative", 3), ("quant", 3), ("controller", 3), ("tax", 3), ("accounts payable", 3),
        ("accounts receivable", 3), ("ar analyst", 3), ("audit", 3), ("treasury", 3), ("lending", 3), ("collections", 3),
        ("insurance", 3), ("mutual funds", 3), ("trader", 3), ("trading", 3), ("banking", 3),
    ],
    "Software Engineering": [
        ("software", 3), ("backend", 3), ("frontend", 3), ("full stack", 3), ("fullstack", 3),
        ("react", 3), ("python developer", 3), ("java", 3), ("javascript", 3), ("node.js", 3),
        ("c++", 3), ("golang", 3), (".net", 3), ("developer", 1), ("engineer", 1),
        ("solutions architect", 3), ("architect", 2), ("engineering manager", 3), ("director of engineering", 3),
        ("programmer", 3), ("sdet", 3), ("test engineer", 3), ("android", 3), ("ios", 3), ("platform engineer", 3),
    ],
    "Cloud & DevOps": [
        ("devops", 3), ("cloud", 3), ("aws", 3), ("azure", 3), ("sre", 3), ("site reliability", 3),
        ("infrastructure", 3), ("kubernetes", 3), ("docker", 3), ("terraform", 3), ("ci/cd", 3),
    ],
    "Product Management": [
        ("product manager", 3), ("product owner", 3), ("associate product", 3),
        ("scrum master", 3), ("product strategy", 3), ("product management", 3),
    ],
    "Design & UX": [
        ("ui/ux", 3), ("ux", 3), ("designer", 3), ("graphic", 3), ("product design", 3), ("figma", 3),
    ],
    "Cybersecurity": [
        ("security", 3), ("cyber", 3), ("cyber security", 3), ("infosec", 3), ("soc analyst", 3),
        ("penetration testing", 3),
    ],
    "Sales & Marketing": [
        ("marketing", 3), ("seo", 3), ("content", 3), ("growth", 3), ("sales", 3),
        ("account executive", 3), ("account development", 3), ("kam", 3), ("key account", 3), ("customer success", 3),
        ("account manager", 3), ("sdr", 3), ("campaign", 3), ("advertising", 3),
        ("business development", 3),
    ],
    "Operations & HR": [
        ("hr", 3), ("human resources", 3), ("talent", 3), ("recruiter", 3), ("operations", 3),
        ("hrbp", 3), ("people ops", 3), ("people support", 3), ("customer support", 3), ("cst", 3), ("customer service", 3),
        ("executive assistant", 3), ("project manager", 3), ("investigations", 3), ("payroll", 3), ("compliance", 3),
        ("people operations", 3),
    ],
}

DEFAULT_CATEGORY = "Software Engineering"
DEFAULT_CONFIDENCE = 0.5


def _compile(keyword: str) -> "re.Pattern[str]":
    # Lookarounds instead of \b so tokens like "c++", ".net", "ui/ux" work.
    return re.compile(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])")


_PATTERNS: Dict[str, List[Tuple["re.Pattern[str]", int]]] = {
    cat: [(_compile(kw), w) for kw, w in kws] for cat, kws in ROLE_KEYWORDS.items()
}


class JobRoleClassifier:
    """Classifies a job into one of the 10 role domains (see ROLE_KEYWORDS)."""

    ROLE_KEYWORDS = ROLE_KEYWORDS

    @classmethod
    def classify(cls, title: str, description: str = "") -> Tuple[str, float]:
        """
        Return (category, confidence). Title matches count fully; description
        matches only count (at 1 point) for specific keywords (weight >= 3), since
        descriptions are noisy. With no match, falls back to DEFAULT_CATEGORY at
        confidence 0.5 (callers can detect this fallback via the confidence value).
        """
        return _classify(title or "", description or "")


@lru_cache(maxsize=16384)
def _classify(title: str, description: str) -> Tuple[str, float]:
    """Pure function of its arguments, hence cacheable (the recommender classifies the same strings repeatedly)."""
    title_l, desc_l = title.lower(), description.lower()
    scores: Dict[str, float] = {}
    for category, patterns in _PATTERNS.items():
        score = 0.0
        for pat, weight in patterns:
            if pat.search(title_l):
                score += weight
            elif weight >= 3 and desc_l and pat.search(desc_l):
                score += 1.0
        scores[category] = score

    best = max(scores, key=scores.get)  # ties resolved by ROLE_KEYWORDS order
    top = scores[best]
    if top == 0:
        return DEFAULT_CATEGORY, DEFAULT_CONFIDENCE
    return best, round(min(0.99, max(0.60, top / (top + 2.0))), 2)


def is_default_fallback(title: str, category: str) -> bool:
    """True if `category` is only the classifier's no-match default for this title (not real evidence)."""
    cat, conf = JobRoleClassifier.classify(title or "")
    return cat == category == DEFAULT_CATEGORY and conf <= DEFAULT_CONFIDENCE
