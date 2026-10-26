> **Historical report** generated on 2026-09-30 by `scripts/run_adzuna_feasibility.py`. Findings about the normalizer's `Mid-level` placeholder describe the behaviour *at that time*; the normalizer has since been changed so that experience level, employment type and work model stay NULL when the source does not state them. Current limitations are summarised in `docs/project_report.md` section 24.

# JobIntel — Data Quality & Feasibility Report (Adzuna)

- **Generated:** `2026-10-04T18:34:35+00:00`
- **Source under test:** Adzuna Jobs API (India, `/v1/api/jobs/in/search/1`)
- **Queries this run:** 4 (results_per_page = 20, page 1 only)
- **Adzuna calls consumed today:** 2 earlier (as reported) + 4 in this run = **6 of 10** (4 remaining)
- **Database:** temporary SQLite file (`jobintel_adzuna_feasibility.db` in the OS temp dir); PostgreSQL untouched
- **Raw responses:** `data/raw/` — `adzuna_raw_20260930_190411_q1_Data_Analyst_Mumbai.json`, `adzuna_raw_20260930_190411_q2_Data_Scientist_Bengaluru.json`, `adzuna_raw_20260930_190411_q3_Data_Analyst_Pune.json`, `adzuna_raw_20260930_190411_q4_Data_Scientist_Hyderabad.json`
- **Scope of evidence:** only this run's four queries. Earlier validation (195 Mumbai hits for "data analyst", 10-record pipeline test) is not re-counted here.

## 1. Verdict

### Classification: **B** — usable with specific limitations/modifications

The class is computed by a fixed rule set from the observed metrics: **C** if any core criterion fails, **B** if all core criteria pass but any enrichment criterion fails, **A** if everything passes.

| Tier | Criterion | Observed | Result |
| :--- | :--- | :--- | :---: |
| Core | All 4 queries returned HTTP 200 with results | HTTP: 200, 200, 200, 200; results: 20, 20, 20, 20 | PASS |
| Core | Unique-ID rate >= 95% | 100.0% | PASS |
| Core | Returned location matches requested city >= 80% | 100.0% | PASS |
| Core | Company present >= 95% | 96.2% | PASS |
| Core | Title + description + date + URL present >= 95% | title 100.0%, desc 100.0%, date 100.0%, url 100.0% | PASS |
| Core | Skill-extraction coverage >= 50% (jobs with >=1 skill) | 67.5% | PASS |
| Enrichment | Full descriptions (median length > 600 chars, i.e. beyond the ~500-char snippet cap) | median 500, max 500 chars | FAIL |
| Enrichment | Salary coverage >= 50% | 15.0% | FAIL |
| Enrichment | Experience supplied by API >= 50% | 0.0% | FAIL |
| Enrichment | Work model supplied by API >= 50% | 0.0% | FAIL |

**Reasons:**

- All core criteria passed: the API authenticates, honours keyword and city filters, returns unique, well-attributed postings (title, company, location, date, URL) that flow through the pipeline, and the snippets still yield skills.
- Enrichment criterion failed: Full descriptions (median length > 600 chars, i.e. beyond the ~500-char snippet cap).
- Enrichment criterion failed: Salary coverage >= 50%.
- Enrichment criterion failed: Experience supplied by API >= 50%.
- Enrichment criterion failed: Work model supplied by API >= 50%.
- Therefore Adzuna is viable as the MVP's posting source for discovery, geography, role and skill-demand analytics, but salary, experience level and full-description features must be treated as limited (see Section 9), or supplemented by a second source.

## 2. Query audit

| # | Query | HTTP | Results returned | Adzuna total `count` | Unique IDs | Duplicate IDs | Content duplicates* |
| :-: | :--- | :-: | ---: | ---: | ---: | ---: | ---: |
| 1 | Data Analyst — Mumbai | 200 | 20 | 195 | 20 | 0 | 3 |
| 2 | Data Scientist — Bengaluru | 200 | 20 | 2762 | 20 | 0 | 1 |
| 3 | Data Analyst — Pune | 200 | 20 | 265 | 20 | 0 | 1 |
| 4 | Data Scientist — Hyderabad | 200 | 20 | 1311 | 20 | 0 | 0 |
| **All** | | | **80** | | **80** | **0** | **5** |

\*Content duplicate = same title + company + city under a different ID (likely reposts). Duplicate IDs are counted within each query; the "All" row counts repeated IDs across the combined set.

## 3. Record counts (total vs unique vs duplicates)

| Measure | Value |
| :--- | ---: |
| Total records returned | 80 |
| Unique records (by Adzuna ID) | 80 |
| Duplicate records (by Adzuna ID) | 0 |
| IDs appearing in more than one query | 0 |
| Likely reposts (same title+company+city, different ID) | 5 |
| Inserted into temp SQLite DB as new | 80 |
| Skipped as already present in DB | 0 |

## 4. Observed locations, roles and companies

### 4.1 Location (normalized city) — all queries

| City | Count | % |
| :--- | ---: | ---: |
| Mumbai | 20 | 25.0% |
| Bengaluru | 20 | 25.0% |
| Pune | 20 | 25.0% |
| Hyderabad | 20 | 25.0% |

### 4.2 Per-query location accuracy and city distribution

**Data Analyst — Mumbai**: 20/20 (100.0%) returned locations match the requested city. Observed cities: Mumbai (20)

**Data Scientist — Bengaluru**: 20/20 (100.0%) returned locations match the requested city. Observed cities: Bengaluru (20)

**Data Analyst — Pune**: 20/20 (100.0%) returned locations match the requested city. Observed cities: Pune (20)

**Data Scientist — Hyderabad**: 20/20 (100.0%) returned locations match the requested city. Observed cities: Hyderabad (20)

### 4.3 Raw location strings — all queries

| Adzuna location.display_name | Count | % |
| :--- | ---: | ---: |
| Mumbai, Maharashtra | 20 | 25.0% |
| Bangalore, Karnataka | 20 | 25.0% |
| Hyderabad, Telangana | 20 | 25.0% |
| Pune, Maharashtra | 18 | 22.5% |
| Yerwada, Pune | 1 | 1.2% |
| Nana Peth, Pune | 1 | 1.2% |

### 4.4 Observed job titles — all queries

| Title | Count | % |
| :--- | ---: | ---: |
| Data Analyst | 27 | 33.8% |
| Data Scientist | 11 | 13.8% |
| Senior Data Scientist | 6 | 7.5% |
| Senior Data Analyst | 4 | 5.0% |
| Data Science Manager | 3 | 3.8% |
| Lead Data Analyst | 2 | 2.5% |
| Data Engineer | 1 | 1.2% |
| Business Development Manager | 1 | 1.2% |
| Senior Business Development Manager | 1 | 1.2% |
| Data Analyst (SQL) | 1 | 1.2% |
| Data Analyst - SQL | 1 | 1.2% |
| Data Science Instructor | 1 | 1.2% |
| Data Science Specialist | 1 | 1.2% |
| Director - Data science (RGM) | 1 | 1.2% |
| Delivery Head - Data Science | 1 | 1.2% |
| Director - Data Science & AI | 1 | 1.2% |
| Data Science Manager - Market Mix Modeling | 1 | 1.2% |
| Data Analyst Intern | 1 | 1.2% |
| Hiring for Data Analyst | 1 | 1.2% |
| Director – Data Science & Data Engineering(AI) | 1 | 1.2% |
| Senior Data Scientist – Marketing Mix Optimization (MMO Enhancements) | 1 | 1.2% |
| Data Scientist :: 5-8 Years & 8 Years :: Multiple openings | 1 | 1.2% |
| GTM Data & AI Analyst - Night Shift | 1 | 1.2% |
| Principal Data Engineering Architect | 1 | 1.2% |
| Software Associate | 1 | 1.2% |
| Associate Accountant - Fixed Assets [T500-29597] | 1 | 1.2% |
| EdTech Business Development Manager – Programs & Partnerships | 1 | 1.2% |
| Data Analyst - Team Lead | 1 | 1.2% |
| Principal Product Manager(Clinical) | 1 | 1.2% |
| Senior Data Engineer | 1 | 1.2% |
| _(other 3 values)_ | 3 | 3.8% |

### 4.5 Normalized role category (our classifier) — all queries

| Role category | Count | % |
| :--- | ---: | ---: |
| Data & Analytics | 43 | 53.8% |
| AI & Machine Learning | 30 | 37.5% |
| Sales & Marketing | 3 | 3.8% |
| Software Engineering | 2 | 2.5% |
| Finance & Banking | 1 | 1.2% |
| Product Management | 1 | 1.2% |

### 4.6 Adzuna's own category label

| Adzuna category | Count | % |
| :--- | ---: | ---: |
| IT Jobs | 67 | 83.8% |
| Accounting & Finance Jobs | 4 | 5.0% |
| Consultancy Jobs | 3 | 3.8% |
| Admin Jobs | 2 | 2.5% |
| Logistics & Warehouse Jobs | 2 | 2.5% |
| Engineering Jobs | 1 | 1.2% |
| Sales Jobs | 1 | 1.2% |

### 4.7 Role category per query

- **Data Analyst — Mumbai**: Data & Analytics (18), Sales & Marketing (2)
- **Data Scientist — Bengaluru**: AI & Machine Learning (20)
- **Data Analyst — Pune**: Data & Analytics (20)
- **Data Scientist — Hyderabad**: AI & Machine Learning (10), Data & Analytics (5), Software Engineering (2), Finance & Banking (1), Sales & Marketing (1), Product Management (1)

### 4.8 Observed companies — all queries

69 distinct companies across 80 records.

| Company | Count | % |
| :--- | ---: | ---: |
| Tata Consultancy Services | 5 | 6.2% |
| Confidential | 3 | 3.8% |
| Wissen Technology | 2 | 2.5% |
| Collegedunia | 2 | 2.5% |
| MathCo | 2 | 2.5% |
| Tredence Inc. | 2 | 2.5% |
| Purview India Consulting And Services Llp | 2 | 2.5% |
| mCaffeine | 1 | 1.2% |
| MSMEx | 1 | 1.2% |
| Qrata | 1 | 1.2% |
| Azent Overseas | 1 | 1.2% |
| Impact Guru | 1 | 1.2% |
| Talent Pro | 1 | 1.2% |
| Pluginlive | 1 | 1.2% |
| MM Staffing & Career Consultants | 1 | 1.2% |
| Acura Solution | 1 | 1.2% |
| Merito | 1 | 1.2% |
| Unnati | 1 | 1.2% |
| Jump Trading | 1 | 1.2% |
| Priceline | 1 | 1.2% |
| Infosys Finacle | 1 | 1.2% |
| NexionPro Services | 1 | 1.2% |
| redBus | 1 | 1.2% |
| Yulu | 1 | 1.2% |
| AB InBev GCC India | 1 | 1.2% |
| _(other 44 values)_ | 44 | 55.0% |

## 5. Field availability and missing-field percentages

Availability is measured on the **raw Adzuna payload** (what the API actually supplied), not on our normalized columns, because the normalizer fills defaults (e.g. `experience_level = Mid-level`, `work_model = Onsite`) that would otherwise mask gaps.

| Field | Present | Missing | Missing % | Note |
| :--- | ---: | ---: | ---: | :--- |
| title | 80 | 0 | 0.0% |  |
| company (company.display_name) | 77 | 3 | 3.8% |  |
| location (location.display_name) | 80 | 0 | 0.0% |  |
| description | 80 | 0 | 0.0% | snippet, see Section 6 |
| posted/created date (`created`) | 80 | 0 | 0.0% |  |
| apply URL (`redirect_url`) | 80 | 0 | 0.0% |  |
| salary (min or max > 0) | 12 | 68 | 85.0% | 0 of these flagged `salary_is_predicted=1` |
| employment type (`contract_time`/`contract_type`) | 23 | 57 | 71.2% |  |
| experience level (API field) | 0 | 80 | 100.0% | Adzuna has no such field |
| work model (API field) | 0 | 80 | 100.0% | Adzuna has no such field |

Inferred-from-text signals (heuristic, not API-supplied):

- Experience/seniority cue in title or snippet (years, fresher, senior, lead, manager…): 45/80 (56.2%)
- Work model explicitly Remote/Hybrid in text: 7/80 (8.8%); the rest default to Onsite by our normalizer.

Employment-type values observed (`contract_time/contract_type`):

| contract_time/contract_type | Count | % |
| :--- | ---: | ---: |
| -/- | 57 | 71.2% |
| full_time/- | 21 | 26.2% |
| -/contract | 1 | 1.2% |
| full_time/contract | 1 | 1.2% |

## 6. Description-length statistics (characters, raw `description`)

| Scope | N | Min | Median | Mean | Max | Ends with ellipsis (truncated) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| Data Analyst — Mumbai | 20 | 203 | 500 | 479 | 500 | 18 (90.0%) |
| Data Scientist — Bengaluru | 20 | 500 | 500 | 500 | 500 | 20 (100.0%) |
| Data Analyst — Pune | 20 | 167 | 500 | 471 | 500 | 18 (90.0%) |
| Data Scientist — Hyderabad | 20 | 500 | 500 | 500 | 500 | 20 (100.0%) |
| **All** | 80 | 167 | 500 | 487 | 500 | 76 (95.0%) |

## 7. Skill-extraction coverage

Extractor: existing `SkillExtractor` (dictionary/regex taxonomy) run on title + cleaned description snippet.

| Scope | Jobs | Jobs with ≥1 skill | Coverage | Mean skills/job | Median |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Data Analyst — Mumbai | 20 | 14 | 70.0% | 1.75 | 1 |
| Data Scientist — Bengaluru | 20 | 16 | 80.0% | 1.45 | 1 |
| Data Analyst — Pune | 20 | 11 | 55.0% | 1.50 | 1 |
| Data Scientist — Hyderabad | 20 | 13 | 65.0% | 2.15 | 1 |
| **All** | 80 | 54 | 67.5% | 1.71 | 1 |

Jobs with ≥3 skills: 18/80 (22.5%); jobs with 0 skills: 26/80.

Top extracted skills (jobs mentioning):

| Skill | Count | % |
| :--- | ---: | ---: |
| sql | 16 | 20.0% |
| data science | 16 | 20.0% |
| python | 10 | 12.5% |
| machine learning | 8 | 10.0% |
| data quality | 7 | 8.8% |
| data visualization | 7 | 8.8% |
| excel | 5 | 6.2% |
| tableau | 5 | 6.2% |
| statistics | 5 | 6.2% |
| predictive modeling | 4 | 5.0% |
| data governance | 4 | 5.0% |
| spark | 4 | 5.0% |
| azure | 4 | 5.0% |
| aws | 4 | 5.0% |
| data warehousing | 3 | 3.8% |
| communication | 3 | 3.8% |
| power bi | 3 | 3.8% |
| nlp | 3 | 3.8% |
| big data | 3 | 3.8% |
| problem solving | 2 | 2.5% |
| _(other 13 values)_ | 21 | 26.2% |

## 8. Salary and experience coverage

| Scope | Salary present | Salary % | Predicted (of present) | Experience (API) % | Experience cue in text % |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Data Analyst — Mumbai | 8/20 | 40.0% | 0 | 0.0% | 45.0% |
| Data Scientist — Bengaluru | 0/20 | 0.0% | 0 | 0.0% | 60.0% |
| Data Analyst — Pune | 4/20 | 20.0% | 0 | 0.0% | 40.0% |
| Data Scientist — Hyderabad | 0/20 | 0.0% | 0 | 0.0% | 80.0% |
| **All** | 12/80 | 15.0% | 0 | 0.0% | 56.2% |

## 9. Known limitations (documented, not fixed in this phase)

1. **Descriptions are short snippets.** Median observed length 500 chars; 76/80 end in an ellipsis. Full responsibilities/qualification sections are not available, which caps NLP richness and skill recall.
2. **Salary is frequently missing.** Present on 12/80 records (15.0%); 0 of those are Adzuna-predicted values rather than employer-stated, so they must not be treated as ground truth.
3. **Experience level is not supplied.** API coverage 0.0%. The normalizer's `Mid-level` is a placeholder default, not data; any experience feature must derive from text cues and be labelled inferred.
4. **Skill extraction can be sparse.** Coverage 67.5%, mean 1.71 skills/job, because the input is a snippet.
5. **"Data Science Manager" classification (resolved).** Earlier runs mapped these titles to Software Engineering; in this run all 4 such records map to: AI & Machine Learning. Guarded by a regression test.
6. **Other observations:** work model is keyword-inferred (default Onsite); employment type depends on Adzuna's `contract_time` which is often absent; relevance ranking and ~20-record pages mean one call yields a small slice of a much larger result set (see `count` in Section 2).

## 10. Limits of this test

- 80 records from 4 queries (page 1, 20 per query) is a feasibility sample, not a market census.
- Only two role families and four cities were tested; other roles (e.g. software, finance) were not evaluated today.
- Skill coverage reflects our current taxonomy and extractor; it is a joint measure of source and extractor.
