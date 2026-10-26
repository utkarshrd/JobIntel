"""
Load the saved Adzuna jobs in data/raw/ into the database named by DATABASE_URL (PostgreSQL by default).
Makes NO API calls.

  python scripts/load_saved_adzuna.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.app.core.database import SessionLocal, engine, init_db  # noqa: E402
from ingestion.saved_adzuna import load_saved_adzuna  # noqa: E402


def main():
    print("Database:", engine.url.render_as_string(hide_password=True))
    init_db()
    db = SessionLocal()
    try:
        run = load_saved_adzuna(db, os.path.join(ROOT, "data", "raw"))
        print(f"Run #{run.id} {run.status}: fetched={run.total_fetched} inserted={run.new_inserted} "
              f"already_present={run.duplicates_skipped} errors={run.errors_count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
