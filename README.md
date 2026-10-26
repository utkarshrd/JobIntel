# JobIntel
### Job-market intelligence (TWSMA) and explainable job recommendation
*FastAPI + PostgreSQL + a lightweight web UI. Real data only: live Adzuna + public Greenhouse/Lever boards; no fabricated users, interactions or labels.*

Full write-up (methodology, evaluation, limitations, API, setup): **[docs/project_report.md](docs/project_report.md)** · Viva preparation: **[docs/viva_guide.md](docs/viva_guide.md)**.

## What it does
- **Live ingestion**: budgeted, throttled, paginated Adzuna search (50 jobs per call) plus keyless Greenhouse/Lever company boards with **full job descriptions**; schedulable; every run audited; raw Adzuna pages saved for reproducibility; stale jobs drop out automatically.
- **NLP / TWSMA**: 108-skill dictionary extraction (employer-name filter), entity extraction, one role classifier; analytics for top skills, skills by role/city, roles, locations, companies, skill co-occurrence, text statistics. Trends are reported as *unsupported* until repeated collection provides them.
- **Recommendation**: popularity, skills, TF-IDF content and a configurable hybrid; every result has rank, score, per-signal scores, matched/missing skills and reasons. Missing data is never rewarded.
- **Personalization**: learns only from activity real users create (view/save/apply/skip). The API reports `cold_start`, `profile_based` or `interaction_informed`.
- **Accounts**: email + password (salted scrypt), signed 7-day sessions, login throttling, change password, delete account (removes all data). No user IDs or tokens are ever shown to users.
- **Evaluation**: reproducible offline *proxy* evaluation (`docs/evaluation_report.md`, `docs/evaluation_report_live.md`). Hybrid leads on mean NDCG@10 in every scenario run and wins the role-only scenario of the original run, but the pre-declared "ahead in every persona" rule is **not** met overall, so no overall winner is claimed. It is not user feedback.
- **UI**: a fast single-page web app served by the API itself at **/ui/** (no second server, no build step): Dashboard, My feed, Jobs, Market, Skill gap, Profile, Account, How it works.
- **Engineering**: Alembic migrations, Docker Compose and CI definitions (written, not run on the dev machine), 170+ automated tests, a live-stack smoke test and a real-browser UI test.

## Quick start (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # DATABASE_URL (PostgreSQL), a long random SECRET_KEY, ADZUNA_APP_ID / ADZUNA_APP_KEY (live Adzuna only)
# one-time, in PostgreSQL:  CREATE DATABASE jobintel;
alembic upgrade head                                                  # create the schema
python scripts/run_ingestion.py --ats                                 # public company boards (no key, no quota)
python scripts/run_ingestion.py --adzuna --budget 48 --dry-run        # show the Adzuna plan; drop --dry-run to run it
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000   # API + web UI
```
Open **http://127.0.0.1:8000/** (it opens the UI; API docs at /api/v1/docs), choose **Create account**, and complete your profile. Saving, applying to or skipping jobs changes later rankings. Repeat ingestion daily with `python scripts/run_ingestion.py --adzuna --ats --every-hours 24` or Task Scheduler / cron.

## Tests and checks
```powershell
python -m pytest                    # full suite (PostgreSQL tests auto-skip if no server is reachable)
python scripts/run_evaluation.py    # regenerate the offline evaluation (--run, --taxonomy, --seeds, --tag)
python scripts/smoke_test.py        # end-to-end API/DB check against the running stack (creates and deletes its own account)
node scripts/ui_e2e.js              # real-browser UI check (Node 22+, Chrome/Edge); registers and deletes its own account
```

## Layout
```
backend/app/   FastAPI app: api/v1/endpoints (incl. auth), services (incl. twsma_service), models, schemas, core (config, database, security)
recommender/   signals, ranking, config (hybrid weights), behavior, explainability, pipeline, evaluation
nlp/           skill_extractor, entity_extractor, classifier (single role-classification source), taxonomy (+ v1 copy)
ingestion/     adzuna_client, ats_clients (Greenhouse/Lever), normalizer, live_runner, saved_adzuna, ats_companies.json
web/           the web UI (index.html, app.js, style.css), served at /ui/
alembic/       migrations (0001 baseline, 0002 password hash)     scripts/   run_ingestion, run_evaluation, smoke_test, ui_e2e.js, ...
data/raw/      saved Adzuna responses (git-ignored)      docs/   reports, specifications, viva guide      tests/   unit, API, UI-serving, PostgreSQL
```

## Known limitations (details in the report)
Two collection snapshots; Adzuna descriptions are short snippets while ATS postings are full text; ATS coverage is 14 mostly large companies; salary, experience and work model are essentially unavailable (stored as missing); "Data Science" is a domain label counted as a skill; company boilerplate is only partly filtered; evaluation is an offline proxy; behavioral personalization is untested on real users; no email verification or password reset by email.
