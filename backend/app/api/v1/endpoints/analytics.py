"""
JobIntel - Market Analytics API Endpoints
"""

from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.schemas.analytics import (
    MarketSummaryResponse,
    SkillDemandItem,
    RoleDistributionItem,
    LocationDemandItem,
    SalaryAnalyticsItem,
)
from backend.app.services.analytics_service import AnalyticsService

router = APIRouter()


@router.get("/summary", response_model=MarketSummaryResponse)
def get_market_summary(db: Session = Depends(get_db)):
    """
    Get full market intelligence overview across jobs, skills, locations, and salaries.
    """
    return AnalyticsService.get_market_summary(db)


_TWSMA_CACHE: dict = {}


def _twsma_fingerprint(db: Session, dedupe: bool):
    """Changes whenever the set of active jobs (or any of their rows) changes, and once per day (staleness cutoff)."""
    from datetime import date
    from sqlalchemy import func
    from backend.app.models.job import Job
    from backend.app.services.job_service import active_filter
    n, newest, seen = db.query(func.count(Job.id), func.max(Job.updated_at), func.max(Job.last_seen_at)).filter(active_filter()).one()
    return (dedupe, n, str(newest), str(seen), date.today().isoformat())


@router.get("/twsma")
def get_twsma_report(dedupe: bool = Query(False, description="Drop likely reposts (same title+company+city) first"),
                     db: Session = Depends(get_db)):
    """
    Full TWSMA report over the stored jobs: top skills, skills by role/location, role/location/company
    distributions, skill co-occurrence, text statistics and posting-date coverage. Describes the stored
    SAMPLE only, not the job market. `posting_dates.trend_supported` states whether trends can be claimed.
    The (2 s) computation is cached in-process and recomputed only when the job data changes.
    """
    from backend.app.services import twsma_service as tw
    key = _twsma_fingerprint(db, dedupe)
    cached = _TWSMA_CACHE.get(dedupe)
    if cached and cached[0] == key:
        return cached[1]
    records = tw.load_records_from_db(db)
    if dedupe:
        records = tw.dedupe_content(records)
    report = tw.build_twsma_report(records)
    report["scope_note"] = ("Analytics describe the collected job sample, not the entire job market. "
                            "Adzuna descriptions are short snippets, so skill coverage is partial.")
    _TWSMA_CACHE[dedupe] = (key, report)
    return report


def warm_twsma_cache() -> None:
    """Best-effort start-up warm-up (never raises: the endpoint recomputes on demand anyway)."""
    from backend.app.core.database import SessionLocal
    db = SessionLocal()
    try:
        get_twsma_report(dedupe=False, db=db)
    except Exception:
        pass
    finally:
        db.close()


@router.get("/skills/top", response_model=List[SkillDemandItem])
def get_top_skills(
    limit: int = Query(20, ge=5, le=100, description="Number of top skills to return"),
    db: Session = Depends(get_db),
):
    """
    Get most demanded skills in current Indian job listings.
    """
    return AnalyticsService.get_top_skills(db, limit=limit)


@router.get("/roles/distribution", response_model=List[RoleDistributionItem])
def get_role_distribution(db: Session = Depends(get_db)):
    """
    Get distribution and average salary across role domains.
    """
    return AnalyticsService.get_role_distribution(db)


@router.get("/locations", response_model=List[LocationDemandItem])
def get_location_demand(
    limit: int = Query(10, ge=3, le=50),
    db: Session = Depends(get_db),
):
    """
    Get job volume across Indian tech hubs and cities.
    """
    return AnalyticsService.get_location_demand(db, limit=limit)


@router.get("/salaries", response_model=List[SalaryAnalyticsItem])
def get_salary_analytics(db: Session = Depends(get_db)):
    """
    Get strictly verified salary distributions by role.
    """
    return AnalyticsService.get_salary_analytics(db)
