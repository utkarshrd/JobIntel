"""
JobIntel - Live ingestion runner (Adzuna search + Greenhouse/Lever company boards).

Design rules:
  * A hard CALL BUDGET per Adzuna run (default settings.ADZUNA_DAILY_CALL_BUDGET = 200, under Adzuna's published
    250/day) and a per-minute throttle (published limit 25/min). The run stops cleanly when the budget is spent.
  * Raw Adzuna responses are saved to data/raw/ in the same format the feasibility run used, so every live run
    stays reproducible and can feed the evaluation / loaders without any new API call.
  * Every run writes an IngestionRun audit row (source, calls made, inserted / already-present / errors).
  * Re-sighting a job refreshes `last_seen_at`; jobs not re-sighted for STALE_AFTER_DAYS drop out of the feed,
    analytics and recommendations (see JobService.active_filter). Greenhouse/Lever boards list ALL current
    postings, so a company's postings missing from a fresh board listing are reported as likely closed.
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.models.ingestion_run import IngestionRun, IngestionStatus
from backend.app.models.job import Job
from backend.app.services.job_service import JobService
from ingestion.adzuna_client import MAX_PER_PAGE, AdzunaClient
from ingestion.ats_clients import GreenhouseClient, LeverClient, is_india_location
from ingestion.normalizer import JobNormalizer
from ingestion.saved_adzuna import attach_skills
from nlp.skill_extractor import SkillExtractor

DEFAULT_ROLES = ["Data Analyst", "Data Scientist", "Machine Learning Engineer", "Data Engineer", "Business Analyst",
                 "Software Engineer", "Backend Developer", "Frontend Developer", "DevOps Engineer",
                 "Product Manager", "Financial Analyst", "Digital Marketing"]
DEFAULT_CITIES = ["Mumbai", "Bengaluru", "Pune", "Hyderabad", "Delhi", "Chennai"]
ATS_CONFIG = os.path.join(os.path.dirname(__file__), "ats_companies.json")

Plan = List[Tuple[str, str, int]]   # (what, where, page)


def build_adzuna_plan(roles: Iterable[str] = DEFAULT_ROLES, cities: Iterable[str] = DEFAULT_CITIES, pages: int = 1) -> Plan:
    """Page-major order, so a budget that runs out covers page 1 of every (role, city) before any page 2."""
    combos = [(r, c) for r in roles for c in cities]
    return [(r, c, p) for p in range(1, pages + 1) for r, c in combos]


def _start_run(db: Session, source: str, params: dict) -> IngestionRun:
    run = IngestionRun(source=source, status=IngestionStatus.RUNNING.value, query_parameters=params,
                       started_at=datetime.now(timezone.utc))
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _finish(db: Session, run: IngestionRun, fetched: int, inserted: int, dupes: int, errors: int, error_log: List[str]):
    run.total_fetched, run.new_inserted, run.duplicates_skipped, run.errors_count = fetched, inserted, dupes, errors
    run.error_log = "\n".join(error_log)[:4000] or None
    run.status = IngestionStatus.COMPLETED.value if not errors else IngestionStatus.PARTIAL.value
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


def run_adzuna(db: Session, plan: Plan, budget: Optional[int] = None, client: Optional[AdzunaClient] = None,
               raw_dir: Optional[str] = None, per_minute: int = 20,
               sleep: Callable[[float], None] = time.sleep) -> IngestionRun:
    """Execute (part of) `plan`, never exceeding `budget` HTTP calls."""
    client = client or AdzunaClient()
    budget = settings.ADZUNA_DAILY_CALL_BUDGET if budget is None else budget
    run = _start_run(db, "adzuna_live", {"planned_requests": len(plan), "budget": budget, "per_page": MAX_PER_PAGE,
                                         "per_minute": per_minute})
    errors_log: List[str] = []
    if not client.configured:
        _finish(db, run, 0, 0, 0, 1, ["ADZUNA_APP_ID / ADZUNA_APP_KEY are not configured"])
        run.status = IngestionStatus.FAILED.value
        db.commit()
        return run
    extractor = SkillExtractor()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fetched = inserted = dupes = errors = executed = 0
    exhausted = set()
    min_gap = 60.0 / max(1, per_minute)
    last_call = 0.0
    for n, (what, where, page) in enumerate(plan, start=1):
        if client.calls_made >= budget:
            logger.info(f"Adzuna call budget {budget} reached; stopping")
            break
        if (what, where) in exhausted:
            continue
        wait = min_gap - (time.monotonic() - last_call)
        if last_call and wait > 0:
            sleep(wait)
        last_call = time.monotonic()
        try:
            data = client.fetch_page(what, where, page, MAX_PER_PAGE)
        except Exception as e:
            errors += 1
            errors_log.append(f"{what}/{where}/p{page}: {type(e).__name__}: {e}"[:300])
            continue
        executed += 1
        results = [r for r in data.get("results", []) if client.validate_record(r)]
        if raw_dir:
            os.makedirs(raw_dir, exist_ok=True)
            path = os.path.join(raw_dir, f"adzuna_raw_{stamp}_q{n}_{_slug(what)}_{_slug(where)}_p{page}.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"query": {"what": what, "where": where}, "page": page, "results_per_page": MAX_PER_PAGE,
                           "fetched_at": datetime.now(timezone.utc).isoformat(), "http_status": 200, "error": None,
                           "response": data}, fh)
        if len(results) < MAX_PER_PAGE or page * MAX_PER_PAGE >= (data.get("count") or 0):
            exhausted.add((what, where))
        for raw in results:
            fetched += 1
            try:
                norm = JobNormalizer.normalize_adzuna_record(raw)
                if norm is None:
                    continue
                job, created = JobService.create_or_update_job(db, norm)
                inserted, dupes = (inserted + 1, dupes) if created else (inserted, dupes + 1)
                attach_skills(db, job, extractor)
            except Exception as e:
                db.rollback()
                errors += 1
                errors_log.append(f"record {raw.get('id')}: {type(e).__name__}: {e}"[:300])
    run.query_parameters = {**run.query_parameters, "calls_made": client.calls_made, "requests_executed": executed,
                            "budget_exhausted": client.calls_made >= budget}
    _finish(db, run, fetched, inserted, dupes, errors, errors_log)
    return run


def load_ats_config(path: str = ATS_CONFIG) -> Dict[str, List[str]]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {k: data.get(k, []) for k in ("greenhouse", "lever")}


def run_ats(db: Session, companies: Optional[Dict[str, List[str]]] = None, greenhouse: Optional[GreenhouseClient] = None,
            lever: Optional[LeverClient] = None, sleep: Callable[[float], None] = time.sleep,
            pause: float = 1.0) -> IngestionRun:
    """Load India-located postings from public company boards. No API key and no quota."""
    companies = companies if companies is not None else load_ats_config()
    greenhouse, lever = greenhouse or GreenhouseClient(), lever or LeverClient()
    run = _start_run(db, "ats_boards", {"boards": companies, "api_calls": 0})
    extractor = SkillExtractor()
    fetched = inserted = dupes = errors = calls = 0
    errors_log: List[str] = []
    possibly_closed: Dict[str, int] = {}
    jobs = [("greenhouse", t) for t in companies.get("greenhouse", [])] + [("lever", t) for t in companies.get("lever", [])]
    for i, (platform, token) in enumerate(jobs):
        if i:
            sleep(pause)
        client, normalize = (greenhouse, JobNormalizer.normalize_greenhouse_record) if platform == "greenhouse" \
            else (lever, JobNormalizer.normalize_lever_record)
        try:
            calls += 1
            board = client.fetch_board(token)
        except Exception as e:
            errors += 1
            errors_log.append(f"{platform}/{token}: {type(e).__name__}: {e}"[:300])
            continue
        seen_ids = set()
        for raw in board:
            if platform == "greenhouse":
                if not is_india_location((raw.get("location") or {}).get("name", "")):
                    continue
            else:
                cats = raw.get("categories") or {}
                if not is_india_location(cats.get("location", ""), *(cats.get("allLocations") or [])):
                    continue
            fetched += 1
            try:
                norm = normalize(raw, token)
                if norm is None:
                    continue
                seen_ids.add(norm.job_id)
                job, created = JobService.create_or_update_job(db, norm)
                inserted, dupes = (inserted + 1, dupes) if created else (inserted, dupes + 1)
                attach_skills(db, job, extractor)
            except Exception as e:
                db.rollback()
                errors += 1
                errors_log.append(f"{platform}/{token}/{raw.get('id')}: {type(e).__name__}: {e}"[:300])
        prefix = ("gh:" if platform == "greenhouse" else "lv:") + token + ":"
        stored = {j for (j,) in db.query(Job.job_id).filter(Job.job_id.like(prefix + "%")).all()}
        if board and stored - seen_ids:
            possibly_closed[f"{platform}/{token}"] = len(stored - seen_ids)
    run.query_parameters = {**run.query_parameters, "api_calls": calls, "possibly_closed_by_board": possibly_closed}
    _finish(db, run, fetched, inserted, dupes, errors, errors_log)
    return run


def stale_report(db: Session) -> Dict[str, int]:
    """Counts of stored jobs by source that are currently stale (not re-sighted within STALE_AFTER_DAYS)."""
    from backend.app.services.job_service import stale_cutoff
    cutoff = stale_cutoff()
    out: Dict[str, int] = {}
    if cutoff:
        for job in db.query(Job.source).filter(Job.last_seen_at < cutoff).all():
            out[job.source] = out.get(job.source, 0) + 1
    return out
