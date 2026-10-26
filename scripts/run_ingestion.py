"""
Live ingestion CLI (Adzuna search + Greenhouse/Lever company boards). Run it by hand or on a schedule.

  python scripts/run_ingestion.py --ats                         # public company boards, no key, no quota
  python scripts/run_ingestion.py --adzuna --dry-run            # print the request plan, call nothing
  python scripts/run_ingestion.py --adzuna --budget 48          # at most 48 Adzuna HTTP calls (50 jobs each)
  python scripts/run_ingestion.py --adzuna --ats --every-hours 24   # repeat daily until stopped (Ctrl+C)
  python scripts/run_ingestion.py --stale-report                # jobs not re-sighted within STALE_AFTER_DAYS
  python scripts/run_ingestion.py --reextract-skills            # re-run skill extraction (after a taxonomy change)

Adzuna's published limits: 25 calls/minute, 250/day. The default budget is settings.ADZUNA_DAILY_CALL_BUDGET (200).
Windows Task Scheduler alternative to --every-hours:
  schtasks /Create /SC DAILY /ST 03:00 /TN JobIntelIngest /TR "<project>\\.venv\\Scripts\\python.exe <project>\\scripts\\run_ingestion.py --adzuna --ats"
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.app.core.config import settings  # noqa: E402
from backend.app.core.database import SessionLocal, init_db  # noqa: E402
from ingestion import live_runner as lr  # noqa: E402

RAW_DIR = os.path.join(ROOT, "data", "raw")


def reextract_skills(db):
    from backend.app.models.job import Job
    from backend.app.models.skill import JobSkill
    from ingestion.saved_adzuna import attach_skills
    from nlp.skill_extractor import SkillExtractor
    ex = SkillExtractor()
    db.query(JobSkill).delete()
    db.commit()
    added = sum(attach_skills(db, j, ex) for j in db.query(Job).all())
    print(f"re-extracted skills for all jobs: {added} job-skill links")


def once(args, db):
    if args.adzuna:
        plan = lr.build_adzuna_plan(args.roles or lr.DEFAULT_ROLES, args.cities or lr.DEFAULT_CITIES, args.pages)
        budget = args.budget if args.budget is not None else settings.ADZUNA_DAILY_CALL_BUDGET
        if args.dry_run:
            print(f"Adzuna plan: {len(plan)} requests (budget {budget}); first 10: {plan[:10]}")
        else:
            run = lr.run_adzuna(db, plan, budget, raw_dir=RAW_DIR)
            qp = run.query_parameters
            print(f"adzuna run #{run.id} {run.status}: calls={qp.get('calls_made')} fetched={run.total_fetched} "
                  f"new={run.new_inserted} already_present={run.duplicates_skipped} errors={run.errors_count}")
            if run.error_log:
                print(run.error_log[:800])
    if args.ats:
        if args.dry_run:
            print("ATS boards:", lr.load_ats_config())
        else:
            run = lr.run_ats(db)
            print(f"ats run #{run.id} {run.status}: fetched(India)={run.total_fetched} new={run.new_inserted} "
                  f"already_present={run.duplicates_skipped} errors={run.errors_count}")
            if run.query_parameters.get("possibly_closed_by_board"):
                print("possibly closed (stored but missing from the live board):", run.query_parameters["possibly_closed_by_board"])
            if run.error_log:
                print(run.error_log[:800])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adzuna", action="store_true")
    ap.add_argument("--ats", action="store_true")
    ap.add_argument("--budget", type=int, help="max Adzuna HTTP calls this run")
    ap.add_argument("--pages", type=int, default=1, help="pages (50 jobs each) per role/city")
    ap.add_argument("--roles", nargs="*")
    ap.add_argument("--cities", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--every-hours", type=float, help="repeat forever with this pause between runs")
    ap.add_argument("--stale-report", action="store_true")
    ap.add_argument("--reextract-skills", action="store_true")
    args = ap.parse_args()
    init_db()
    while True:
        db = SessionLocal()
        try:
            if args.stale_report:
                print(f"stale (> {settings.STALE_AFTER_DAYS} days unseen):", lr.stale_report(db) or "none")
            if args.reextract_skills:
                reextract_skills(db)
            once(args, db)
        finally:
            db.close()
        if not args.every_hours:
            break
        time.sleep(args.every_hours * 3600)


if __name__ == "__main__":
    main()
