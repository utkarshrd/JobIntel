# JobIntel - Viva guide

A study sheet for presenting and defending the project. Every number below comes from this repository's own reports and tests; re-check them against `docs/project_report.md` if the data is refreshed.

## 1. The 60-second pitch
> JobIntel turns real job postings into structured market intelligence and uses the same structure to recommend jobs *with reasons*. It collects postings from Adzuna and public Greenhouse/Lever company boards into PostgreSQL, extracts skills and roles with simple auditable NLP, computes text-analytics over the sample (TWSMA), and ranks jobs for a user with four strategies (popularity, skills, TF-IDF content, hybrid). Every recommendation explains itself, learns only from the user's real activity, and is honest about missing data. The recommenders were compared with a clearly-labelled offline proxy evaluation, and I report exactly what that does and does not prove.

## 2. How the two course topics map to the project
| Topic | Where it lives |
|---|---|
| **Text / Web / Social-Media Analytics (TWSMA)** | Web data collection (APIs, public job boards) -> text cleaning -> skill / entity / role extraction -> descriptive analytics: top skills, skills by role and city, skill co-occurrence with lift, common terms/bigrams, description statistics (`backend/app/services/twsma_service.py`, Market page) |
| **Recommendation systems** | Popularity baseline, skill-overlap, TF-IDF content-based, weighted hybrid, cold-start handling, behavioural (implicit-feedback) personalization, explainability, offline evaluation with Precision/Recall/NDCG@K and diversity (`recommender/`) |

## 3. Numbers to know (current data)
- **3,079 jobs** from **1,355 companies**: Adzuna 2,433 (short ~500-character snippets), Greenhouse 393 and Lever 253 (full descriptions, ~5,000 characters). 13 cities; Bengaluru is largest (981).
- **108 skills** in the taxonomy; 67.5% of jobs have at least one extracted skill (mean 2.7).
- Role classifier: 10 categories; 138 of 3,079 titles fall back to the default category and are flagged and ignored by the role signal.
- Collection: 48 Adzuna calls (12 roles x 4 cities, 50 results per call) + 14 company boards (no quota). Adzuna's published limit is 250 calls/day.
- Hybrid default weights: skill 0.35, content 0.30, role 0.10, behaviour 0.10, location 0.06, popularity 0.05 - renormalised over the signals a user actually has. Untuned starting values.
- Recommendation latency ~0.6 s at 3,079 jobs. Tests: 170+ automated, smoke test 46/46 on the live stack, real-browser UI test 30/30.

## 4. Five-minute demo script
1. **Dashboard** (signed out): live counts, top skills, role/city mix. Point out the honest banner: "describes the sample, not the market".
2. **How it works**: pipeline, live source counts, signal weights, evaluation table and limitations - the one-page summary of the project.
3. **Create account** (email + password, no IDs/tokens) -> **Profile**: add skills with the tag input ("SQL, Python, ml" - note "ml" is resolved to Machine Learning), pick roles/locations. Show the completeness meter.
4. **My feed**: cold-start vs profile-based banner; open "Why this job" on rank 1 - every reason is backed by a real signal. Switch strategy to *Skills only* / *Popularity* to show the difference.
5. **Save** a job -> banner becomes *Interaction-informed*; "Similar to a job you saved..." appears in the reasons. Open **Profile** -> "Learned from your activity".
6. **Skill gap**: role-level and single-job comparison.
7. **Market**: tabs; open *Dates & trends* and show the app **refuses** to claim a trend (explain why).
8. (Optional) terminal: `python scripts/run_ingestion.py --adzuna --budget 48 --dry-run` to show the budget/throttle design; `python scripts/run_evaluation.py` to show reproducibility.

## 5. Key design decisions and why
- **Database over live fetching.** Calling Adzuna on every page view would burn a 250/day quota, add latency and conflict with the provider's terms. A scheduled, budgeted ingestion job fills PostgreSQL; the UI only reads. Raw responses are saved so every result is reproducible.
- **Second source (Greenhouse/Lever).** Adzuna gives only ~500-character snippets, so skill extraction was starved. Company boards expose complete postings without keys. Trade-off: coverage is per company (14 here), not per market.
- **Simple, explainable NLP.** Dictionary skill matching and keyword role rules are auditable, deterministic and fast; every extracted skill can be traced to text. No neural model was needed to answer the project's questions, and an examiner can inspect every rule.
- **Missing data is never rewarded.** If a job has no skills, no city or no date, that signal contributes 0 for the job; if a *user* has no skills/roles/locations, the signal is dropped and the remaining weights are renormalised. This prevents "unknown" from looking like "perfect".
- **Cold start.** A new user is ranked by recency and told so (`cold_start`); profile data upgrades them to `profile_based`; real activity upgrades them to `interaction_informed`. The UI states which one applies, so it never claims personalization it has not done.
- **Behavioural layer, deliberately simple.** Weighted view/click/save/apply/skip -> preference tables (skills, role, city) + similarity to liked jobs, minus a penalty for similarity to skipped jobs; active only after enough positive evidence. No collaborative filtering because there is no interaction volume to justify it.
- **Authentication.** Email + password, scrypt-hashed with a per-user salt; stateless HMAC-signed sessions with expiry; generic sign-in errors (no account enumeration); throttling after 5 failures; per-user authorisation on every private endpoint; account deletion cascades all data. One schema change was needed (`users.password_hash`) and it was done with a reviewed Alembic migration.
- **UI.** A small single-page app served by the API: one process, one origin, no build step. Job text is rendered as text nodes only, because it comes from external sources (XSS-safe by construction, and tested).

## 6. Evaluation - say exactly this
- **Why a proxy:** there are zero real users and zero interactions, so there is no ground truth. I did not invent any.
- **Method:** each collection query is a "persona"; jobs Adzuna returned for it are "relevant"; half are hidden as held-out labels and the other half build the persona's profile; strategies rank the rest; Precision/Recall/NDCG@K and diversity are computed over 10-50 random splits. A random ranking is the floor.
- **Winner rule fixed before running:** highest mean NDCG@10, ahead in *every* persona, and a 95% bootstrap interval of the lead excluding zero.
- **Results (mean NDCG@10):** original data (role-only scenario) Hybrid 0.831 vs Content 0.700, Skills 0.652, Popularity 0.350, Random 0.310 -> **Hybrid is a clear winner there**. Live data (48 role+city personas): Hybrid 0.483 vs Content 0.142, Skills 0.064, Popularity 0.010 (Random 0.012). Hybrid is best on average and in 46/48 personas, but not in *all*, so the rule is **not met** and **no overall winner is claimed**.
- **What it supports:** Hybrid, Content and (on the first run) Skills beat random; Popularity does not (it is only a recency proxy).
- **What it does not support:** claims about real users, production accuracy, or the behavioural layer. Say so before you are asked.

## 7. Questions you may be asked (and honest answers)
**Q: Is Hybrid the best recommender?** On this proxy it has the highest mean accuracy in every run, and clearly wins the role-only scenario; but under my pre-declared strict rule there is no overall winner, and a proxy cannot show real-user preference. I would need real feedback to decide.

**Q: Isn't the evaluation circular?** Partly, yes - the query defines both the persona's role/location and the label, which favours location/role-aware methods. I report that as a limitation, ran a role-only scenario with no location to reduce it, and did not tune weights on the results.

**Q: Why not collaborative filtering / deep learning / embeddings?** There are no user-item interactions to learn from, and the questions asked (explain *why*, handle cold start, respect missing data) are better served by transparent methods. Adding a model would add complexity without evidence of benefit; it is listed as future work once interaction volume exists.

**Q: How do you know skill extraction is accurate?** I haven't measured precision/recall against hand-labelled data, and I do not claim an accuracy figure. I report coverage (67.5% of jobs have at least one skill), known weaknesses ("Data Science" is a field not a tool; company boilerplate partly filtered; short snippets) and added an employer-name filter for the clearest false positives.

**Q: Why do the analytics say "no trends"?** Trend claims need repeated collection over time. I have two snapshots; showing a trend would be fabricating one. The scheduler now makes daily collection possible, after which the same code will report trends once the data supports them.

**Q: Is the data representative of the Indian job market?** No. It is two snapshots, Adzuna search for 12 roles in 4 cities, plus 14 mostly large tech/fintech employers' boards. The dashboard and report say "this sample".

**Q: What about salary and experience?** The sources almost never supply them, so they are stored as missing and never imputed; experience in years is *inferred from text* for ~24% of jobs and shown only as information, not scored. An earlier version stored "Mid-level" as a placeholder; I removed it because it presented a guess as data.

**Q: How is personalization different from the profile match?** The profile signals come from what the user *says*; the behaviour signal comes from what they *do* (saves/applies/views/skips) and only activates after enough evidence. The response reports which mode applied.

**Q: How do you protect user data?** Passwords are salted scrypt hashes; sessions are signed and expire; each user can reach only their own data; sign-in failures are generic and throttled; users can delete their account and all their data. Not implemented: email verification, password reset by email, session revocation, shared-store throttling for multi-server deployment.

**Q: What would you do with more time?** Collect real usage and evaluate the behavioural layer; run daily collection to unlock trends and closed-job detection; add more company boards and cities; hand-label a sample to measure skill-extraction accuracy; separate domain terms from tool skills; precompute feature vectors for much larger corpora.

**Q: What was the hardest bug / lesson?** (Pick one.) The real-browser test found that lists of job cards rendered as "[object HTMLElement]" - unit tests could not have caught it, which is why the UI is tested in a real browser. Another: broader data exposed that the role classifier missed common titles ("Data Scientists", "Account Executive"); I extended it and kept the fallback flagged rather than letting defaults pose as evidence.

## 8. Things to avoid saying
- "Hybrid is the best" (say: highest on average; rule not met overall).
- "The recommendations are accurate/validated" (say: evaluated on a proxy).
- "Users like it" (there are no users yet).
- "The market is trending toward..." (no trend claims are supported).
- Quoting any number not in this guide or the report.

## 9. If something breaks during the demo
- API/DB health: http://127.0.0.1:8000/api/v1/health. Restart PostgreSQL, then `python -m uvicorn backend.app.main:app --port 8000` (commands in the README).
- Forgotten demo password: create a new account (a fresh account also shows the cold-start -> profile-based -> interaction-informed progression nicely).
- No internet: nothing in the demo needs it (data is already in PostgreSQL); only fresh ingestion does.
