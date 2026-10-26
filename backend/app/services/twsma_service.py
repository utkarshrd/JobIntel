"""
JobIntel - TWSMA Analytics Service

Text/Web/Social-Media-Analytics style market analytics over job postings.

Design:
  * Every analytic is a pure function over a list of `JobRecord` (plain data), so it
    can be called from FastAPI, evaluation scripts and tests with no DB.
  * `load_records_from_db` builds `JobRecord`s from the existing Job/JobSkill tables.
  * Missing data stays missing: absent companies/cities/dates are counted separately,
    never imputed, and nothing here invents values.
"""

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations
from typing import Any, Dict, List, Optional, Sequence

from nlp.classifier import is_default_fallback
from nlp.entity_extractor import EntityExtractor
from nlp.preprocessor import TextPreprocessor

# Placeholder strings the ingestion layer / sources use when a company is not disclosed.
UNDISCLOSED_COMPANIES = {"", "confidential", "unknown", "n/a", "na", "not disclosed"}

# Boilerplate that carries no market signal in job text (added to the NLP stopword list).
JOB_TEXT_STOPWORDS = {
    "description", "strong", "skills", "company", "key", "seeking", "ideal", "join", "help",
    "including", "etc", "across", "within", "new", "ability", "location", "summary", "title",
    "also", "can", "like", "using", "based", "various", "well", "good", "great", "highly",
    "re", "us", "get", "make", "need", "needs", "may", "one", "role", "roles", "responsible",
    "required", "preferred", "looking", "hands", "ensure", "provide", "support", "working",
}

ELLIPSIS_ENDINGS = ("...", "…")


@dataclass
class JobRecord:
    """Minimal, source-agnostic view of one job posting used by all analytics."""
    title: str
    role_category: Optional[str] = None
    company: Optional[str] = None
    city: Optional[str] = None
    description: Optional[str] = None
    posted_at: Optional[datetime] = None
    skills: List[str] = field(default_factory=list)
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    # True when role_category came from the classifier's no-match fallback.
    role_is_fallback: bool = False

    def skill_set(self) -> frozenset:
        return frozenset(self.skills)


# --------------------------------------------------------------------------- helpers

def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 2) if whole else 0.0


def role_is_fallback(title: str, role_category: Optional[str]) -> bool:
    """True if `role_category` is only the classifier's default for an unmatched title."""
    return bool(role_category) and is_default_fallback(title, role_category)


def is_company_disclosed(company: Optional[str]) -> bool:
    return (company or "").strip().lower() not in UNDISCLOSED_COMPANIES


# --------------------------------------------------------------------------- loaders

def load_records_from_db(db) -> List[JobRecord]:
    """Build JobRecords from the Job / JobSkill / Skill tables."""
    from sqlalchemy.orm import joinedload
    from backend.app.models.job import Job
    from backend.app.models.skill import JobSkill

    from backend.app.services.job_service import active_filter
    jobs = (db.query(Job).filter(active_filter())
            .options(joinedload(Job.skills_rel).joinedload(JobSkill.skill_rel)).all())
    return [
        JobRecord(
            title=j.title,
            role_category=j.role_category,
            company=j.company_name,
            city=j.city,
            description=j.description_cleaned or j.description,
            posted_at=j.posted_at,
            skills=sorted({js.skill_rel.name for js in j.skills_rel}),
            salary_min=j.salary_min,
            salary_max=j.salary_max,
            role_is_fallback=role_is_fallback(j.title, j.role_category),
        )
        for j in jobs
    ]


def dedupe_content(records: Sequence[JobRecord]) -> List[JobRecord]:
    """Drop likely reposts (same title + company + city), keeping the first occurrence."""
    seen, out = set(), []
    for r in records:
        key = ((r.title or "").lower(), (r.company or "").lower(), (r.city or "").lower())
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# --------------------------------------------------------------------------- 1. top skills

def top_skills(records: Sequence[JobRecord], limit: Optional[int] = 20) -> List[Dict[str, Any]]:
    """Skills by number of jobs containing them. Percentage is of ALL jobs (n = len(records))."""
    n = len(records)
    counts = Counter(s for r in records for s in r.skill_set())
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if limit:
        ranked = ranked[:limit]
    return [{"skill": s, "job_count": c, "percentage": _pct(c, n)} for s, c in ranked]


def skill_coverage(records: Sequence[JobRecord]) -> Dict[str, Any]:
    """How much of the corpus has any extracted skill (context for every skill percentage)."""
    n = len(records)
    per_job = [len(r.skill_set()) for r in records]
    with_skills = sum(1 for k in per_job if k)
    return {
        "total_jobs": n,
        "jobs_with_skills": with_skills,
        "jobs_without_skills": n - with_skills,
        "coverage_percentage": _pct(with_skills, n),
        "mean_skills_per_job": round(statistics.mean(per_job), 2) if per_job else 0.0,
    }


# --------------------------------------------------------------------------- 2. skills by role

def skills_by_role(records: Sequence[JobRecord], top_n: int = 8) -> Dict[str, Dict[str, Any]]:
    """Per role: job count, jobs with skills, and top skills (percentage is of that role's jobs)."""
    groups: Dict[str, List[JobRecord]] = defaultdict(list)
    for r in records:
        if r.role_category:
            groups[r.role_category].append(r)
    out = {}
    for role, rs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        out[role] = {
            "job_count": len(rs),
            "jobs_with_skills": sum(1 for r in rs if r.skills),
            "top_skills": top_skills(rs, limit=top_n),
        }
    return out


# --------------------------------------------------------------------------- 3. role distribution

def role_distribution(records: Sequence[JobRecord]) -> Dict[str, Any]:
    """
    Jobs per role category. `fallback_count` is how many jobs in a category got it only
    because the classifier found no keyword match (the default), i.e. not a real classification.
    """
    n = len(records)
    counts = Counter(r.role_category or "Unclassified" for r in records)
    fallback = Counter(r.role_category or "Unclassified" for r in records if r.role_is_fallback)
    items = [
        {
            "role_category": role,
            "job_count": c,
            "percentage": _pct(c, n),
            "fallback_count": fallback.get(role, 0),
        }
        for role, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    unmatched = sum(1 for r in records if r.role_is_fallback)
    return {
        "total_jobs": n,
        "classified_by_keyword": n - unmatched,
        "unmatched_fallback": unmatched,
        "items": items,
    }


# --------------------------------------------------------------------------- 4. locations

def location_distribution(records: Sequence[JobRecord]) -> Dict[str, Any]:
    n = len(records)
    counts = Counter(r.city for r in records if r.city)
    return {
        "total_jobs": n,
        "missing_city": sum(1 for r in records if not r.city),
        "items": [
            {"city": c, "job_count": k, "percentage": _pct(k, n)}
            for c, k in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }


def skills_by_location(records: Sequence[JobRecord], top_n: int = 8) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[JobRecord]] = defaultdict(list)
    for r in records:
        if r.city:
            groups[r.city].append(r)
    return {
        city: {
            "job_count": len(rs),
            "jobs_with_skills": sum(1 for r in rs if r.skills),
            "top_skills": top_skills(rs, limit=top_n),
        }
        for city, rs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    }


def roles_by_location(records: Sequence[JobRecord]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[JobRecord]] = defaultdict(list)
    for r in records:
        if r.city:
            groups[r.city].append(r)
    return {city: role_distribution(rs)["items"] for city, rs in groups.items()}


# --------------------------------------------------------------------------- 5. companies

def company_distribution(records: Sequence[JobRecord], limit: Optional[int] = 15) -> Dict[str, Any]:
    """Postings per disclosed company. Undisclosed/placeholder companies are counted separately."""
    n = len(records)
    disclosed = [r.company.strip() for r in records if is_company_disclosed(r.company)]
    counts = Counter(disclosed)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "total_jobs": n,
        "undisclosed_count": n - len(disclosed),
        "distinct_companies": len(counts),
        "items": [{"company": c, "job_count": k} for c, k in (ranked[:limit] if limit else ranked)],
    }


# --------------------------------------------------------------------------- 6. co-occurrence

def skill_cooccurrence(records: Sequence[JobRecord], min_count: int = 2,
                       limit: Optional[int] = 20) -> List[Dict[str, Any]]:
    """
    Skill pairs that appear together in the same job. Only real co-presence is counted.
    `lift` > 1 means the pair co-occurs more than expected if the skills were independent.
    """
    n = len(records)
    single = Counter(s for r in records for s in r.skill_set())
    pairs = Counter()
    for r in records:
        for a, b in combinations(sorted(r.skill_set()), 2):
            pairs[(a, b)] += 1
    items = []
    for (a, b), c in pairs.items():
        if c < min_count:
            continue
        lift = (c * n) / (single[a] * single[b]) if single[a] and single[b] else 0.0
        items.append({
            "skill_a": a, "skill_b": b, "job_count": c,
            "percentage": _pct(c, n), "lift": round(lift, 2),
        })
    items.sort(key=lambda d: (-d["job_count"], d["skill_a"], d["skill_b"]))
    return items[:limit] if limit else items


# --------------------------------------------------------------------------- 7. text analysis

def _term_tokens(text: str) -> List[str]:
    return re.findall(r"[a-z][a-z0-9+#.]*[a-z0-9+#]|[a-z]", TextPreprocessor.preprocess(text))


def _is_content_word(tok: str) -> bool:
    return (len(tok) > 2 and tok not in TextPreprocessor.STOPWORDS and tok not in JOB_TEXT_STOPWORDS)


def description_statistics(records: Sequence[JobRecord]) -> Dict[str, Any]:
    """Length statistics (characters) and truncation. Missing descriptions are counted, not zero-filled."""
    n = len(records)
    texts = [(r.description or "").strip() for r in records]
    lens = [len(t) for t in texts if t]
    stats: Dict[str, Any] = {
        "total_jobs": n,
        "missing_description": n - len(lens),
        "truncated_with_ellipsis": sum(1 for t in texts if t.endswith(ELLIPSIS_ENDINGS)),
    }
    if lens:
        stats.update({
            "mean_length": round(statistics.mean(lens), 1),
            "median_length": statistics.median(lens),
            "min_length": min(lens),
            "max_length": max(lens),
        })
    else:
        stats.update({"mean_length": None, "median_length": None, "min_length": None, "max_length": None})
    return stats


def common_terms(records: Sequence[JobRecord], limit: int = 20, min_docs: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    """Most common unigrams and bigrams by document frequency (number of jobs containing them)."""
    n = len(records)
    uni, bi = Counter(), Counter()
    for r in records:
        toks = _term_tokens(r.description or "")
        uni.update({t for t in toks if _is_content_word(t)})
        bi.update({f"{a} {b}" for a, b in zip(toks, toks[1:]) if _is_content_word(a) and _is_content_word(b)})

    def rank(c):
        return [
            {"term": t, "job_count": k, "percentage": _pct(k, n)}
            for t, k in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])) if k >= min_docs
        ][:limit]

    return {"unigrams": rank(uni), "bigrams": rank(bi)}


def qualification_mentions(records: Sequence[JobRecord]) -> Dict[str, Any]:
    n = len(records)
    counts = Counter()
    any_mention = 0
    for r in records:
        quals = EntityExtractor.extract_qualifications(r.description or "")
        any_mention += bool(quals)
        counts.update(quals)
    return {
        "total_jobs": n,
        "jobs_with_any_qualification": any_mention,
        "items": [{"qualification": q, "job_count": c, "percentage": _pct(c, n)}
                  for q, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))],
    }


def experience_mentions(records: Sequence[JobRecord]) -> Dict[str, Any]:
    """
    Experience requirements found in the description TEXT (the source API supplies none).
    These are inferred from text, available only where the posting states them, and a
    stated minimum alone ("3+ years") is not given an invented maximum.
    """
    n = len(records)
    mins, ranges = [], 0
    for r in records:
        lo, hi = EntityExtractor.extract_experience_years(r.description or "")
        if lo is not None:
            mins.append(lo)
            ranges += hi is not None
    out: Dict[str, Any] = {
        "total_jobs": n,
        "jobs_with_stated_experience": len(mins),
        "coverage_percentage": _pct(len(mins), n),
        "with_upper_bound": ranges,
        "source": "inferred from description text",
    }
    out["median_min_years"] = statistics.median(mins) if mins else None
    return out


def text_analysis(records: Sequence[JobRecord]) -> Dict[str, Any]:
    return {
        "description": description_statistics(records),
        "common_terms": common_terms(records),
        "qualifications": qualification_mentions(records),
        "experience": experience_mentions(records),
    }


# --------------------------------------------------------------------------- 8. dates / trend

def posting_date_analysis(
    records: Sequence[JobRecord],
    reference_date: Optional[datetime] = None,
    min_months: int = 6,
    min_jobs_per_month: int = 30,
) -> Dict[str, Any]:
    """
    Posting-date coverage, freshness buckets and monthly counts.

    A *trend* is only reported as supported when the data spans at least `min_months`
    calendar months and every counted month has at least `min_jobs_per_month` jobs.
    Even then, posting dates of currently-live adverts from one collection are a
    snapshot (older postings that were already filled are missing), so monthly
    counts are NOT a demand time series; this is stated in `caveat`.
    """
    n = len(records)
    dated = [r.posted_at for r in records if r.posted_at]
    out: Dict[str, Any] = {
        "total_jobs": n,
        "with_date": len(dated),
        "missing_date": n - len(dated),
        "earliest": min(dated).date().isoformat() if dated else None,
        "latest": max(dated).date().isoformat() if dated else None,
    }
    monthly = Counter(d.strftime("%Y-%m") for d in dated)
    out["monthly_counts"] = [{"month": m, "job_count": c} for m, c in sorted(monthly.items())]

    ref = reference_date or (max(dated) if dated else None)
    if ref:
        buckets = Counter()
        for d in dated:
            age = (ref - d).days
            buckets["0-7 days" if age <= 7 else "8-30 days" if age <= 30 else
                    "31-90 days" if age <= 90 else "over 90 days"] += 1
        out["freshness_reference"] = ref.date().isoformat()
        out["freshness"] = {k: buckets.get(k, 0)
                            for k in ("0-7 days", "8-30 days", "31-90 days", "over 90 days")}

    dense_months = [m for m, c in monthly.items() if c >= min_jobs_per_month]
    supported = len(monthly) >= min_months and len(dense_months) == len(monthly)
    out["trend_supported"] = supported
    if not supported:
        out["trend_reason"] = (
            f"Not enough data: {len(monthly)} distinct month(s) with dates; need >= {min_months} "
            f"months each with >= {min_jobs_per_month} jobs."
        )
    out["caveat"] = ("Posting dates of currently-live adverts from a single collection are a snapshot, "
                     "not a demand time series; expired postings are absent.")
    return out


# --------------------------------------------------------------------------- composition

def build_twsma_report(records: Sequence[JobRecord], reference_date: Optional[datetime] = None) -> Dict[str, Any]:
    """All TWSMA analytics in one JSON-serialisable dict (for API / dashboard / reports)."""
    return {
        "total_jobs": len(records),
        "skill_coverage": skill_coverage(records),
        "top_skills": top_skills(records),
        "skills_by_role": skills_by_role(records),
        "role_distribution": role_distribution(records),
        "location_distribution": location_distribution(records),
        "skills_by_location": skills_by_location(records),
        "roles_by_location": roles_by_location(records),
        "company_distribution": company_distribution(records),
        "skill_cooccurrence": skill_cooccurrence(records),
        "text_analysis": text_analysis(records),
        "posting_dates": posting_date_analysis(records, reference_date=reference_date),
    }
