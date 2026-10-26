# JobIntel - Project Report

Job-market intelligence (Text/Web/Social-Media Analytics, "TWSMA") and explainable job recommendation, built on real job postings.

> **Honesty statement.** All job data is real: Adzuna search results plus public Greenhouse/Lever company boards, collected 2026-09-30 (80 jobs, original feasibility run) and 2026-10-25 (live runs). There are **no real users and no real interactions** in the dataset. Nothing was fabricated: no jobs, skills, salaries, experience values, interactions or relevance labels. The recommender evaluations are **offline proxies**, not user feedback, and no claim is made about user satisfaction, production accuracy, or the Indian job market as a whole.

---

## 1. Project overview
JobIntel ingests job postings from live sources, cleans and de-duplicates them, extracts skills/roles/entities with simple explainable NLP, computes market analytics over the collected sample, and ranks jobs for a user with four strategies (popularity, skills, TF-IDF content, hybrid). Recommendations carry rank, score, per-signal scores and plain-language reasons. A behavioral layer learns only from interactions that real users generate through the UI/API. Components: FastAPI backend, PostgreSQL, and a web UI served by the API.

## 2. Problem statement
Job postings are unstructured text. Job seekers cannot easily see which skills a market sample demands, and generic job lists do not say *why* a job suits them. JobIntel turns postings into structured features, summarises them (TWSMA) and uses the same features to produce transparent, personalised rankings.

## 3. Objectives
1. Real, repeatable job ingestion with cleaning, de-duplication and staleness handling.
2. Skill / qualification / experience extraction and role classification (one classifier).
3. Reusable TWSMA analytics (skills, roles, locations, companies, co-occurrence, text statistics).
4. Four recommendation strategies, a configurable hybrid, and explanations.
5. A formal, honestly-labelled offline evaluation.
6. Interaction-based personalization that never invents history; cold start still works.
7. End-to-end operation on PostgreSQL via FastAPI and a web UI, with real accounts (email + password), migrations and tests at every layer.

## 4. System architecture
```
Adzuna API (budgeted, paginated) --\
Greenhouse / Lever public boards ---+--> ingestion (normalize, clean, dedupe, skills) --> PostgreSQL
saved raw JSON (data/raw) ----------/                                                      |
   TWSMA analytics (twsma_service)  <---------------------------------------------------- +
   recommender (signals, ranking, behavior, explanations)  <------------------------------ +
   FastAPI /api/v1 (+ serves the web UI at /ui/)  --->  browser   --- interactions written back --> PostgreSQL
```
| Layer | Package | Notes |
|---|---|---|
| Ingestion | `ingestion/` | `adzuna_client`, `ats_clients` (Greenhouse/Lever), `JobNormalizer`, `live_runner`, `saved_adzuna`, `ats_companies.json` |
| NLP | `nlp/` | `SkillExtractor` (108-skill taxonomy), `EntityExtractor`, `JobRoleClassifier` (single source of truth) |
| Analytics | `backend/app/services/twsma_service.py` | Pure functions over `JobRecord`s |
| Recommender | `recommender/` | `signals`, `ranking`, `config`, `behavior`, `explainability`, `pipeline`, `evaluation` |
| API | `backend/app/` | Thin routers; logic in services / `recommender`; accounts and sessions in `core/security.py` and `endpoints/auth.py` |
| UI | `web/` | Single-page web app served by the API at `/ui/`; no business logic |
| Ops | `alembic/`, `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml` | Migrations verified; Docker and CI files written but not executed on the dev machine |

## 5. Data sources and collection
| Source | Access | What it gives | Used for |
|---|---|---|---|
| **Adzuna Jobs API (India)** | Free key; published limits 25 calls/min, 250/day, 1,000/week, 2,500/month ([terms](https://developer.adzuna.com/docs/terms_of_service)) | Search results, 50 per page (verified), ~500-character description snippets, no salary/experience for most | Broad role x city coverage |
| **Greenhouse public boards** | Keyless, no published limit, one board per company (`boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`) | Complete current listing, **full descriptions** (~5,800 chars on average), dates | India-located postings of 10 companies |
| **Lever public boards** | Keyless, no published limit (`api.lever.co/v0/postings/{token}`) | Complete listing, full descriptions, workplace type, commitment | India-located postings of 4 companies |

Greenhouse/Lever were checked against the real APIs before adoption: of 53 candidate company tokens probed, 20 returned a board; the 14 kept in `ats_companies.json` all have India-located postings (boards with none, such as Cloudflare and Dropbox, were left out) (for example Paytm 152, Okta 96, Databricks 89, MongoDB 82, Meesho 55). Many Indian companies (e.g. Razorpay, Swiggy, Postman, Flipkart) are **not** on these two platforms (HTTP 404), so coverage is by company, not by market.

**Collections.**
1. 2026-09-30: 4 Adzuna queries x 20 results (the original feasibility sample, 80 jobs). Raw files: `data/raw/adzuna_raw_20260930_190411_q*`.
2. 2026-10-25: `run_ingestion.py --ats` (646 India postings, no quota) and `--adzuna --budget 48` (12 roles x 4 cities, 48 calls, 2,400 results, 2,353 new). Raw Adzuna pages are saved as `data/raw/adzuna_raw_<timestamp>_q<n>_<role>_<city>_p1.json`, so every run is reproducible without new calls.

**Live ingestion** (`python scripts/run_ingestion.py`): hard per-run call budget (default 200, under the 250/day limit), 20 calls/min throttle, retries on 429/5xx, pagination, an `ingestion_runs` audit row per run (source, calls, inserted / already-present / errors), `--dry-run`, `--every-hours N` for a repeating schedule (or Windows Task Scheduler / cron), `--stale-report`. Real-time-per-request fetching from the UI was deliberately **not** built: it would burn the daily quota, add latency and conflict with Adzuna's terms; the standard design (scheduled ingestion into PostgreSQL, UI reads the database) is used instead.

**Terms.** Adzuna's terms ask for attribution and restrict reuse of its data; the UI links to the original source of every posting and credits Adzuna/Greenhouse/Lever in the sidebar. Suitable for an academic project; check each provider's terms before any commercial use.

## 6. Data quality / feasibility
Current database (2026-10-25): **3,079 jobs** (Adzuna 2,433; Greenhouse 393; Lever 253), 1,355 distinct disclosed companies (46 postings undisclosed), 4 main cities (Bengaluru 981, Mumbai 637, Hyderabad 631, Pune 604) plus Noida, Gurugram and a few others, 37 jobs with no usable city. 67.55% of jobs have at least one extracted skill (mean 2.72 per job; ATS postings with full text carry many more than Adzuna snippets). Description length: median 500, mean 1,490, max 12,032 characters, bimodal (Adzuna snippets vs ATS full text); 2,298 postings end in an ellipsis (snippets). Salary, experience level and work model are essentially absent (stored as NULL). Experience in years can be inferred from text for 724 jobs (23.5%; median minimum 5 years) and is informational only. The original 80-job feasibility analysis is preserved in `docs/data_quality_report.md`.

## 7. Data preprocessing
`TextCleaner` strips HTML/whitespace. `JobNormalizer` maps each source to `JobCreate`: Adzuna, Greenhouse, Lever (job IDs are source-prefixed, e.g. `gh:databricks:123`). Missing fields stay missing (no placeholder experience level, employment type or work model; work model only when text/API says remote/hybrid/onsite). City extraction finds the first known Indian city anywhere in the location string, canonicalises Bangalore/Gurgaon/New Delhi, and refuses country names or "Remote ..." labels as cities. De-duplication: by source ID at load time; likely reposts (same title + company + city) are dropped in analytics on request (`dedupe=true`) and always in the evaluation. Re-sighting a job refreshes `last_seen_at`.

**Staleness.** Jobs not re-sighted for `STALE_AFTER_DAYS` (default 30) drop out of the job list, analytics and recommendations (`include_stale=true` shows them). Greenhouse/Lever boards list *all* current postings, so stored postings missing from a fresh board listing are reported as "possibly closed" in the run's audit row. Adzuna search results are partial views, so absence there is not treated as closure. No schema change was needed (`last_seen_at` already existed). The original 80 Adzuna jobs were last seen on 2026-10-05 and will age out unless re-sighted.

## 8. NLP / TWSMA methodology
Dictionary-based, auditable methods only (no neural models): taxonomy phrase matching for skills, regex patterns for degrees and experience years, weighted keyword rules for role category. Analytics are descriptive counts/percentages over the stored sample.

## 9. Skill extraction
`nlp/skill_extractor.py` matches **108 taxonomy skills** (54 original + 54 added 2026-10-25: more languages, frameworks, databases, data-engineering, ML, DevOps, finance, marketing and soft skills; the original list is kept as `skills_taxonomy_v1.json` for reproducing Phase D). Whole-phrase matching with aliases over title + description. **Employer-name filter:** a skill that is just the employer's own name (e.g. MongoDB in every MongoDB posting) is dropped; other company boilerplate is *not* filtered. User-entered skills resolve through the same taxonomy (`ml` -> Machine Learning), so they match job skills.

## 10. Role classification
`nlp/classifier.py` (`JobRoleClassifier`) is the single source of truth; the normalizer, analytics and recommender all call it (results are cached). Keywords were extended on 2026-10-25 after the broader data exposed gaps ("Data Scientists", "Data Quality Analyst", "Account Executive", "HRBP", "Controller" etc.); fallback titles dropped from 307 to 138 of 3,079; those 138 "Software Engineering" fallbacks are flagged by `is_default_fallback`, ignored by the role signal and counted separately in analytics.

## 11. TWSMA analytics
`GET /api/v1/analytics/twsma` (service: `twsma_service.build_twsma_report`): top skills, skills by role, skills by location, role distribution, location distribution, roles by location, company distribution, skill co-occurrence with lift, description/qualification/experience statistics, posting-date coverage. Trends are **not** reported: the dates span 90 distinct months but come from two collection snapshots of live adverts; a trend needs repeated daily collection (>= 6 months each with >= 30 jobs under the project's rule), which the scheduler now makes possible but time has not yet provided.

## 12. Recommendation algorithms
Implemented once in `recommender/ranking.py` and exposed as strategies:
1. **Popularity** - recency percentile of posting date (no interaction counts exist, so this is a recency proxy).
2. **Skills** - share of the job's extracted skills the user has.
3. **Content** - TF-IDF cosine between profile text and job text (vocabulary fit on the job corpus only; the fitted corpus is cached in-process, results identical).
4. **Hybrid** - weighted combination of skill, content, role match, location match, popularity and behavior.
At 3,079 jobs a hybrid request takes about 0.5-0.6 s (was ~1.4 s before role-classification caching, deferred JSON loading and corpus caching); the database load of full descriptions now dominates. Beyond ~10k jobs, persisting feature vectors would be the next step.

## 13. Hybrid ranking
Default raw weights: skill 0.35, content 0.30, role 0.10, location 0.06, popularity 0.05, behavior 0.10 (overridable per request: `w_skill`, `w_content`, `w_role`, `w_location`, `w_popularity`, `w_behavior`). Weights are validated and **renormalised over the signals the user actually has data for**. Missing data is never rewarded. Ties break by job id, so ranking is deterministic. The default weights are starting values, **not tuned and not claimed optimal**.

## 14. Explainability
Every item returns rank, score, per-signal `component_scores` (null = not assessable), `matched_skills`, `missing_skills`, `experience_fit` (only when the posting states a requirement) and `reasons`, each generated only from a signal that was available and active.

## 15. Offline evaluation methodology
With zero users and zero interactions there is no real ground truth. `recommender/evaluation.py` implements a **held-out proxy** from the only real label available - which Adzuna search returned each job:
- A *persona* is one collection query (personas with < 10 relevant jobs are skipped). Relevant set = jobs returned for that query (Scenario A, role + city) or for all queries with the same search role (Scenario B, role only, no location).
- The relevant set is split randomly in half: *seed jobs* (stand-in history) and *held-out jobs* (labels). Seeds are removed from the candidate pool.
- The profile is built from seeds only by a fixed rule set in advance (skills in >= 2 seed jobs; role; city in A; role + skill names as text).
- All four strategies rank the pool with the production ranking code and default weights; K = 5 and 10; Precision@K, Recall@K, NDCG@K (binary), intra-list diversity (1 - mean pairwise TF-IDF similarity); a seeded random ranking is shown as a floor.
- **Winner rule (fixed before the first run and never changed):** highest mean NDCG@10, ahead in *every* persona, and a 95% paired-bootstrap CI for the lead over the runner-up that excludes 0.

Reproduce: `python scripts/run_evaluation.py` (no API, no DB). Output: `docs/evaluation_report*.md`, `docs/evaluation_results*.json`. Options: `--run <timestamp>`, `--taxonomy <json>`, `--seeds`, `--tag`.

## 16. Evaluation results
**Run 1 - original collection (Phase D; 75 de-duplicated jobs, 4 personas / 2 roles, 50 splits).** Reproduces exactly with `--run 20260930_190411 --taxonomy nlp/dictionaries/skills_taxonomy_v1.json` (verified after all later changes). Mean NDCG@10:

| Scenario | Hybrid | Skills | Content | Popularity | Random | Verdict |
|---|---:|---:|---:|---:|---:|---|
| A (role + city) | 0.451 | 0.315 | 0.319 | 0.149 | 0.160 | No clear winner (Hybrid loses to Popularity on 1 of 4 personas) |
| B (role only) | 0.831 | 0.652 | 0.700 | 0.350 | 0.310 | **Hybrid is the clear winner** |

**Run 2 - live collection (2026-10-25; 2,118 de-duplicated Adzuna jobs, 12 roles x 4 cities = 48 personas in A, 12 roles in B, 10 splits, expanded taxonomy).** Full tables in `docs/evaluation_report_live.md`. Mean over trials:

| Scenario | Strategy | P@10 | R@10 | NDCG@10 | Diversity@10 | Personas won (highest NDCG@10) |
|---|---|---:|---:|---:|---:|---:|
| A (48 personas) | Hybrid | 0.431 | 0.193 | 0.483 | 0.792 | 46 |
| | Skills | 0.067 | 0.030 | 0.064 | 0.876 | 2 |
| | Content | 0.142 | 0.064 | 0.142 | 0.704 | 0 |
| | Popularity | 0.010 | 0.005 | 0.010 | 0.961 | 0 |
| | Random (floor) | 0.011 | 0.005 | 0.012 | 0.960 | - |
| B (12 personas) | Hybrid | 0.663 | 0.075 | 0.668 | 0.738 | 8 |
| | Skills | 0.117 | 0.013 | 0.107 | 0.880 | 1 |
| | Content | 0.588 | 0.067 | 0.597 | 0.739 | 3 |
| | Popularity | 0.041 | 0.005 | 0.039 | 0.953 | 0 |
| | Random (floor) | 0.036 | 0.004 | 0.033 | 0.959 | - |

**What the evidence supports.**
- Under the pre-declared rule there is **no clear winner in Run 2 either**: Hybrid has the highest mean NDCG@10 in both scenarios (95% CI of its lead over Content: A [0.32, 0.36], B [0.04, 0.11], both above 0) but is not ahead in *every* persona (it is best in 46/48 and 8/12). The rule's "every persona" requirement becomes harder to meet as personas increase; it was not relaxed after seeing results. The per-persona win counts are shown as supplementary description only.
- **Hybrid wins the role-only Scenario B in Run 1** under the rule. Across both runs, **no clear overall winner was established** by the rule.
- **Hybrid, Content (and Skills in Run 1) perform far above random; Popularity performs at or near random** (it is only a recency proxy). In Run 2 **Skills is weak** (NDCG@10 0.06-0.11): most Adzuna snippets yield few skills, so most candidates tie at zero.
- Hybrid lists are less diverse than Skills/Popularity lists (0.74-0.79 vs 0.88-0.96): relevance and variety trade off.
- These are proxy results; they are not user feedback and say nothing about real-world accuracy.

## 17. Evaluation limitations
Relevance means "Adzuna returned this job for the persona's search", not "this person would like it". The query defines both the persona and the label (circularity); in Scenario A location nearly gives the label away, favouring location-aware strategies; job titles contain the search role, helping Content and Hybrid. Profile skills come from seed jobs of the same query. Run 1 has only 2-4 personas and 75 jobs; Run 2 has more personas but a single snapshot and only Adzuna jobs (ATS jobs have no query label and are excluded); in both, repeating random splits reduces split noise, not persona-sample noise. Popularity has no interaction counts. **Behavior is not evaluated** (no interactions exist).

## 18. Interaction-based personalization
`recommender/behavior.py`; learns **only** from rows in the `interactions` table created by real use. No history is seeded.
- Weights per type: view 0.25, click 0.5, save 1.0, apply 1.5, skip -1.0 (hand-set, untuned). Per job the weights are summed and clamped to [-1.5, 2.0], so repeated views cannot dominate and save-then-skip cancels.
- From net-positive jobs it builds preference tables (skill, role category, city); a candidate's behavior score is the mean of the assessable sub-affinities (skill, role, city, best TF-IDF similarity to *another* liked job), minus 0.5 x similarity to a skipped job. Skipped jobs are hidden from the hybrid feed.
- The signal activates only when positive evidence >= 1.0 (e.g. one save or four views).
- Behavior applies to the **hybrid** strategy only; the other three stay pure baselines.
- Explanations cite it ("Similar to a job you saved ('X', TF-IDF similarity 0.35)", "Shares skills with jobs you engaged with", "Ranked lower: similar to a job you skipped").
- Not used: collaborative filtering, learned models, time decay.

## 19. Cold-start handling
Every recommendation response states `personalization_mode`: `cold_start` (no profile data and no active behavior; ranked by recency only, flagged), `profile_based`, or `interaction_informed` (behavior signal active; `interactions_used` reports how many). A user with no profile can still become interaction-informed from real saves/applies.

## 20. Database architecture
PostgreSQL (SQLAlchemy 2.0). Tables: `jobs`, `companies`, `skills`, `job_skills`, `users`, `user_skills`, `interactions`, `ingestion_runs` (+ `locations`, unused). **Migrations:** Alembic (`alembic/`): `0001` baseline generated from the models, and `0002` adding `users.password_hash` (nullable `VARCHAR(255)`, the only schema change of the account work: it is required because passwords must be stored as hashes; existing rows are unaffected). Both are verified to build the schema from scratch with no drift (`tests/test_migrations.py`); the running database is at `0002`. Use `alembic upgrade head` on new databases and `alembic revision --autogenerate` for future changes. SQLite is used only by the automated tests; the application never silently falls back to another database. Staleness uses the existing `last_seen_at`; sources are distinguished by `jobs.source`.

## 21. FastAPI architecture
Routers under `backend/app/api/v1/endpoints/`, services under `backend/app/services/`, Pydantic schemas under `backend/app/schemas/`. CORS is limited to the configured origins (no wildcard).

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health` | status + database connectivity |
| `GET /jobs/`, `GET /jobs/{id}` | search/filter/paginate (incl. `source`, `include_stale`), detail |
| `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | create an account / sign in / restore the session |
| `PUT /auth/password`, `DELETE /auth/me` | change password; delete the account and its data |
| `GET/PUT /users/{id}`, `GET /users/{id}/interactions`, `GET /users/{id}/personalization` | profile, history, learned preferences; own data only |
| `POST /users/interactions` | record view/click/save/apply/skip (as the signed-in user; 422 bad type, 404 unknown job) |
| `GET /recommendations/{user_id}` | `ranking_strategy`, `limit`, `w_*` overrides; own data only |
| `GET /analytics/summary`, `GET /analytics/twsma` | public aggregates |
| `GET /skill-gap/analyze`, `GET /skill-gap/job/{id}` | own data only |
| `GET /ingestion/runs` | ingestion audit trail |

**Accounts and access control.** Users register with name, email and password (`POST /auth/register`, minimum 8 characters, emails case-insensitive and unique) and sign in with `POST /auth/login`. Passwords are stored only as salted **scrypt** hashes (standard library; never logged or returned). A session is a stateless HMAC-signed token with a 7-day expiry (`ACCESS_TOKEN_EXPIRE_MINUTES`), sent as `Authorization: Bearer ...`; the web UI keeps it in the browser, so users never see user IDs or tokens. Sign-in failures return one generic message (no account enumeration) and are throttled (5 failures per 15 minutes per email + client, in memory). `GET /auth/me` restores a session, `PUT /auth/password` changes the password, `DELETE /auth/me` permanently deletes the account with its skills and interaction history (password required). A user can only read or change their own profile, interactions and recommendations; anything else returns 401. `POST /users/` (passwordless creation) is disabled while authentication is enforced. The app refuses to start outside development with the placeholder `SECRET_KEY`. `REQUIRE_USER_TOKEN=false` disables the checks (used by the general test suite; `tests/test_access_control.py` covers authentication enabled). Not implemented: email verification, password reset by email, session revocation, multi-process throttling.

## 22. Web UI architecture
`web/` holds a single-page app (plain HTML/CSS/JS, no framework, no build step) that the API serves at `/ui/` (`GET /` redirects browsers there), so there is one process and one origin. Public pages: Dashboard (with a call-to-action for visitors), Jobs, Market (TWSMA tabs), How it works. Signed-in pages: My Feed, Skill Gap, Profile (onboarding with a completeness meter and a tag-style skill input with suggestions), Account settings (change password, delete account). Sign-in and Create-account are real pages with validation, password strength hint and `next` redirects; private routes redirect to sign-in; an expired session is dropped with a clear message. Feed cards show rank, a match bar, collapsible plain-language reasons and Save / Mark applied / Skip buttons that post real interactions and refresh the ranking in place. It holds no business logic: every number comes from the API, the heavy TWSMA report is cached server-side (recomputed only when the job data changes, pre-warmed at start-up) and briefly client-side. Job text is always inserted as text nodes, never HTML (checked by a test). Accessibility basics: labelled controls, keyboard-operable menu and dialogs, skip link, visible focus, light/dark mode.

**Why not Streamlit.** The earlier Streamlit UI re-ran a whole Python script and several API calls on every click and requested the 2.4 s TWSMA report on almost every page; it was removed. The web UI renders pages from one or two API calls with the report cached (2.4 s -> about 12 ms). **Verification:** `scripts/ui_e2e.js` drives headless Chrome through the DevTools protocol against the running stack like a user would (30 checks): landing page, private-route redirect, registration through the real form (weak password and mismatch rejected), onboarding, tag input, profile-based feed, Save -> interaction-informed, details with skill comparison, skill gap, learned preferences, account menu, password change, sign-out / sign-in (old password rejected), invalid-session handling, account deletion (leaves no data behind) and zero JavaScript console errors. Its first runs found and fixed real rendering bugs.

## 23. End-to-end workflow
1. `python scripts/run_ingestion.py --ats --adzuna --budget N` (or on a schedule) -> normalise -> PostgreSQL with skills, audit rows and saved raw Adzuna pages. (`scripts/load_saved_adzuna.py` loads previously saved raw files without any API call.)
2. The backend serves analytics computed from active (non-stale) rows.
3. A user registers (UI or `POST /auth/register`) and is signed in; the browser keeps the session.
4. `GET /recommendations/{id}` ranks all active jobs with explanations and mode.
5. Save / apply / skip / view are interaction rows; the next request is interaction-informed.

**Verified** by `scripts/smoke_test.py` against live PostgreSQL 17.5 + FastAPI: **46/46 checks passed** (health, jobs from all three sources with full ATS descriptions, registration / sign-in / authorization and password hashing, profile and alias resolution, cold-start -> profile-based -> interaction-informed, explanations, all four strategies, latency under 3 s at 3,079 jobs (0.6 s measured), TWSMA, skill gap, ingestion runs from live sources, the web UI served, PostgreSQL persistence, and deletion of the temporary account through the API), plus `scripts/ui_e2e.js` (30/30 in a real browser).

## 24. Limitations
- **Coverage.** Two snapshots (Sep 30 and Oct 25); 3,079 jobs; Adzuna was queried for 12 roles x 4 cities only (Delhi/Chennai and many roles are not covered); ATS coverage is 14 companies, mostly large tech/fintech employers, and many Indian companies are not on Greenhouse/Lever. The dataset is skewed toward Bengaluru (32%) and technology roles; statistics describe this sample, **not the Indian job market**.
- **Adzuna descriptions are ~500-character snippets** (2,298 postings end in an ellipsis); skill recall for those is partial. ATS postings have full text, so skill statistics mix two very different text lengths.
- **Salary, experience level and work model are essentially unavailable** and stored as NULL. Experience is inferred from text for 23.5% of jobs and shown as informational only.
- **"Data Science" is a field/domain, not a tool skill** (195 jobs); it is categorised "Domain / Field" but still counted as a skill. Likewise "communication" and "leadership" (soft skills) top the skills list for ATS postings.
- **Company boilerplate** beyond whole-employer-name matches is not filtered; ATS postings contain long generic company text.
- **Role classification** is keyword-based; 138 titles still fall back to the default category (flagged and ignored by the role signal, but they inflate the "Software Engineering" count in raw distributions).
- **Trends are not supported** yet (two snapshots; daily collection would be required).
- **Staleness** is a time heuristic; Adzuna jobs that closed are only detected by not being seen again.
- The evaluations are offline proxies (see 17); behavior weights/thresholds are hand-set; behavior is unevaluated; no time decay.
- Access control is minimal (see 21); Docker and CI files are untested here; recommendation requests still load all active jobs from the database (0.5-0.6 s at 3k jobs).

## 25. Future work
Collect real interactions from real users, then evaluate the behavioral layer and consider collaborative filtering only if volume justifies it; run daily collection for weeks to unlock trend analysis and closure detection; add more ATS company boards (the Greenhouse/Lever token list is a config file) and cities/roles; separate domain terms from tool skills and filter company boilerplate; persist feature vectors for larger corpora; tune weights on real feedback; email verification and password reset, session revocation and shared-store throttling; run and harden the Docker/CI setup.

## 26. Installation / setup
Requires Python 3.11+ (developed on 3.13) and PostgreSQL 14+.
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # DATABASE_URL (PostgreSQL), SECRET_KEY; ADZUNA_APP_ID / ADZUNA_APP_KEY for live Adzuna ingestion
```
Create the database once (`CREATE DATABASE jobintel;`), then:
```powershell
alembic upgrade head                                  # create the schema (for a database that already has tables: alembic stamp head)
python scripts/run_ingestion.py --ats                 # keyless company boards, India postings
python scripts/run_ingestion.py --adzuna --budget 48  # live Adzuna (needs keys); --dry-run prints the plan first
python scripts/load_saved_adzuna.py                   # optional: load saved raw Adzuna files (no API calls)
```
Without admin rights, the official PostgreSQL binaries zip works: `initdb -D <dir> -U postgres --pwfile=<file> -A scram-sha-256`, then `pg_ctl -D <dir> start`. Docker alternative (untested here): `docker compose up --build`.

## 27. How to run the backend
```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```
Docs: http://127.0.0.1:8000/api/v1/docs, health: http://127.0.0.1:8000/api/v1/health. Repeat ingestion daily with `python scripts/run_ingestion.py --adzuna --ats --every-hours 24` or a Task Scheduler / cron entry.

## 28. How to open the UI
Nothing extra to run: with the backend up, open **http://127.0.0.1:8000/** (redirects to `/ui/`), choose **Create account**, then complete your profile. Signing in later only needs your email and password.

## 29. How to run tests
```powershell
python -m pytest                      # full suite (SQLite in memory; PostgreSQL tests auto-skip if no server)
python scripts/run_evaluation.py      # regenerate the offline evaluation (see options above)
python scripts/smoke_test.py          # end-to-end API/DB check against the RUNNING stack (see its docstring)
node scripts/ui_e2e.js                # real-browser UI check (Node 22+, Chrome/Edge); registers and deletes its own account
```
The test suite never touches the application database and runs with authentication off except where tested explicitly. `tests/test_postgres.py` uses a throw-away `jobintel_test` database on the server given by `TEST_POSTGRES_ADMIN_URL` (default: local `postgres`/`postgres`).
