"""
JobIntel - Load the Adzuna responses ALREADY SAVED in data/raw/ into the configured database.

No API calls. Pipeline: raw JSON -> JobNormalizer -> JobService (dedupe on Adzuna ID) -> SkillExtractor
-> Skill / JobSkill rows, with an IngestionRun audit row. Re-running is idempotent: existing jobs are
not duplicated and jobs that already have skills are not re-extracted.
"""

import glob
import json
import os
import re
from datetime import datetime, timezone
from typing import List

from sqlalchemy.orm import Session

from backend.app.models.ingestion_run import IngestionRun, IngestionStatus
from backend.app.models.skill import JobSkill, Skill
from backend.app.services.job_service import JobService
from ingestion.normalizer import JobNormalizer
from nlp.skill_extractor import SkillExtractor


def latest_adzuna_files(raw_dir: str) -> List[str]:
    files = sorted(glob.glob(os.path.join(raw_dir, "adzuna_raw_*_q*.json")))
    if not files:
        raise FileNotFoundError(f"no adzuna_raw_*_q*.json files in {raw_dir}")
    ts = max(re.search(r"adzuna_raw_(\d{8}_\d{6})_", os.path.basename(f)).group(1) for f in files)
    return [f for f in files if f"adzuna_raw_{ts}_" in os.path.basename(f)]


def attach_skills(db: Session, job, extractor: SkillExtractor) -> int:
    """Extract skills from the job text and persist Skill/JobSkill rows. Returns links added."""
    if db.query(JobSkill.id).filter(JobSkill.job_id == job.id).first():
        return 0
    text = f"{job.title} {job.description_cleaned or job.description}"
    added = 0
    for es in extractor.extract_skills(text, exclude_company=job.company_name or ""):
        skill = db.query(Skill).filter(Skill.name == es.name).first()
        if not skill:
            skill = Skill(name=es.name, display_name=es.display_name, category=es.category)
            db.add(skill)
            db.flush()
        db.add(JobSkill(job_id=job.id, skill_id=skill.id, skill_type=es.skill_type,
                        confidence=es.confidence, extraction_method=es.extraction_method))
        added += 1
    db.commit()
    return added


def load_saved_adzuna(db: Session, raw_dir: str) -> IngestionRun:
    files = latest_adzuna_files(raw_dir)
    run = IngestionRun(source="adzuna_saved_files", status=IngestionStatus.RUNNING.value,
                       query_parameters={"files": [os.path.basename(f) for f in files], "api_calls": 0},
                       started_at=datetime.now(timezone.utc))
    db.add(run)
    db.commit()
    db.refresh(run)
    extractor = SkillExtractor()
    fetched = inserted = dupes = errors = 0
    for path in files:
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        for raw in (rec.get("response") or {}).get("results", []):
            fetched += 1
            try:
                norm = JobNormalizer.normalize_adzuna_record(raw)
                if norm is None:
                    continue
                job, created = JobService.create_or_update_job(db, norm)
                inserted, dupes = (inserted + 1, dupes) if created else (inserted, dupes + 1)
                attach_skills(db, job, extractor)
            except Exception as e:  # keep going; the audit row records the count
                db.rollback()
                errors += 1
                run.error_log = f"{run.error_log or ''}{type(e).__name__}: {e}\n"[:2000]
    run.total_fetched, run.new_inserted, run.duplicates_skipped, run.errors_count = fetched, inserted, dupes, errors
    run.status = IngestionStatus.COMPLETED.value if not errors else IngestionStatus.PARTIAL.value
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run
