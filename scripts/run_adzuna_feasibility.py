"""
JobIntel - Adzuna Final Data-Source Feasibility Check

Modes:
  python scripts/run_adzuna_feasibility.py fetch     -> exactly 4 Adzuna API calls, raw JSON saved to data/raw/
  python scripts/run_adzuna_feasibility.py analyze   -> NO API calls; ingests saved raw files into a temporary
                                                        SQLite DB and writes docs/data_quality_report.md

PostgreSQL is never touched: DATABASE_URL is forced to a temp SQLite file before any app import.
"""

import glob
import json
import os
import re
import statistics
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

TEMP_DB = os.path.join(tempfile.gettempdir(), "jobintel_adzuna_feasibility.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEMP_DB.replace(os.sep, '/')}"

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BASE_DIR, ".env"))

RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
REPORT_PATH = os.path.join(BASE_DIR, "docs", "data_quality_report.md")

QUERIES = [
    {"what": "Data Analyst", "where": "Mumbai"},
    {"what": "Data Scientist", "where": "Bengaluru"},
    {"what": "Data Analyst", "where": "Pune"},
    {"what": "Data Scientist", "where": "Hyderabad"},
]
RESULTS_PER_PAGE = 20
QUOTA_TOTAL = 10
QUOTA_USED_BEFORE = 2  # as stated by the user before this run


def fetch():
    import httpx
    from backend.app.core.config import settings

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    os.makedirs(RAW_DIR, exist_ok=True)
    country = (settings.ADZUNA_COUNTRY or "in").lower()
    calls = 0
    for i, q in enumerate(QUERIES, 1):
        params = {
            "app_id": settings.ADZUNA_APP_ID,
            "app_key": settings.ADZUNA_APP_KEY,
            "what": q["what"],
            "where": q["where"],
            "results_per_page": RESULTS_PER_PAGE,
            "content-type": "application/json",
        }
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        calls += 1  # counted before the request: one attempt = one call, no retries
        try:
            res = httpx.get(url, params=params, timeout=30.0)
            status, body = res.status_code, res.text
        except Exception as e:  # network failure; still counts as an attempted call
            status, body = None, str(e)
        record = {
            "query": q,
            "results_per_page": RESULTS_PER_PAGE,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "http_status": status,
            "response": None,
            "error": None,
        }
        if status == 200:
            record["response"] = json.loads(body)
        else:
            record["error"] = body[:500]
        fname = f"adzuna_raw_{ts}_q{i}_{q['what'].replace(' ', '_')}_{q['where']}.json"
        with open(os.path.join(RAW_DIR, fname), "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        n = len((record["response"] or {}).get("results", []))
        print(f"[call {calls}/4] {q['what']} / {q['where']}: HTTP {status}, {n} results -> {fname}")
    print(f"TOTAL ADZUNA CALLS MADE THIS RUN: {calls}")


def pct(n, d):
    return round(100.0 * n / d, 1) if d else 0.0


def dist_table(counter, total, label, top=15):
    rows = [f"| {label} | Count | % |", "| :--- | ---: | ---: |"]
    for k, v in counter.most_common(top):
        rows.append(f"| {k} | {v} | {pct(v, total)}% |")
    if len(counter) > top:
        rest = sum(v for _, v in counter.most_common()[top:])
        rows.append(f"| _(other {len(counter) - top} values)_ | {rest} | {pct(rest, total)}% |")
    return "\n".join(rows)


CITY_ALIASES = {"bangalore": "bengaluru"}


def city_of(query_where):
    return CITY_ALIASES.get(query_where.lower(), query_where.lower())


EXP_PATTERN = re.compile(
    r"\b(\d+\s*(?:\+|-|to)?\s*\d*\s*(?:years?|yrs?)|fresher|entry[- ]level|senior|junior|lead|principal|manager)\b", re.I
)


def analyze():
    from backend.app.core.database import SessionLocal, init_db
    from backend.app.models.skill import Skill, JobSkill
    from backend.app.services.job_service import JobService
    from ingestion.normalizer import JobNormalizer
    from nlp.skill_extractor import SkillExtractor

    files = sorted(glob.glob(os.path.join(RAW_DIR, "adzuna_raw_*_q*.json")))
    # use only the latest run (same timestamp prefix)
    if not files:
        sys.exit("No Adzuna raw files found in data/raw/")
    latest_ts = max(re.search(r"adzuna_raw_(\d{8}_\d{6})_", os.path.basename(f)).group(1) for f in files)
    files = [f for f in files if f"adzuna_raw_{latest_ts}_" in os.path.basename(f)]

    if os.path.exists(TEMP_DB):
        os.remove(TEMP_DB)
    init_db()
    db = SessionLocal()
    extractor = SkillExtractor()

    per_query = []
    all_records = []  # (query_idx, raw)
    for f in files:
        with open(f, encoding="utf-8") as fh:
            rec = json.load(fh)
        resp = rec.get("response") or {}
        results = resp.get("results", [])
        per_query.append({"file": os.path.basename(f), "q": rec["query"], "status": rec["http_status"],
                          "count_total": resp.get("count"), "results": results, "error": rec.get("error")})
    for qi, pq in enumerate(per_query):
        for r in pq["results"]:
            all_records.append((qi, r))

    seen_ids = set()
    normalized = []  # dicts with raw + norm + skills + flags
    db_inserted = 0
    db_dupes = 0
    for qi, raw in all_records:
        norm = JobNormalizer.normalize_adzuna_record(raw)
        if norm is None:
            continue
        job, created = JobService.create_or_update_job(db, norm)
        skills = []
        if created:
            db_inserted += 1
            text = f"{job.title} {job.description_cleaned or job.description}"
            for es in extractor.extract_skills(text):
                skills.append(es.name)
                sk = db.query(Skill).filter(Skill.name == es.name).first()
                if not sk:
                    sk = Skill(name=es.name, display_name=es.display_name, category=es.category)
                    db.add(sk)
                    db.flush()
                db.add(JobSkill(job_id=job.id, skill_id=sk.id, skill_type=es.skill_type,
                                confidence=es.confidence, extraction_method=es.extraction_method))
            db.commit()
        else:
            db_dupes += 1
            text = f"{norm.title} {norm.description_cleaned or norm.description}"
            skills = [es.name for es in extractor.extract_skills(text)]
        normalized.append({"qi": qi, "raw": raw, "norm": norm, "skills": skills, "dup_in_db": not created})
    db.close()

    # ---------- metrics ----------
    def metrics(items):
        n = len(items)
        ids = [i["raw"].get("id") for i in items]
        uniq_ids = set(ids)
        content_keys = Counter((i["norm"].title.lower(), i["norm"].company_name.lower(), (i["norm"].city or "").lower())
                               for i in items)
        content_dupes = sum(v - 1 for v in content_keys.values() if v > 1)
        desc_lens = [len(i["norm"].description or "") for i in items]
        m = {
            "total": n,
            "unique_ids": len(uniq_ids),
            "dup_ids": n - len(uniq_ids),
            "content_dupes": content_dupes,
            "cities": Counter(i["norm"].city or "Unspecified" for i in items),
            "locations_raw": Counter(i["norm"].location_raw for i in items),
            "titles": Counter(i["norm"].title for i in items),
            "roles": Counter(i["norm"].role_category for i in items),
            "companies": Counter(i["norm"].company_name for i in items),
            "adzuna_categories": Counter(((i["raw"].get("category") or {}).get("label")) or "Missing" for i in items),
            "desc_lens": desc_lens,
            "desc_present": sum(1 for i in items if i["raw"].get("description")),
            "company_present": sum(1 for i in items if (i["raw"].get("company") or {}).get("display_name")),
            "location_present": sum(1 for i in items if (i["raw"].get("location") or {}).get("display_name")),
            "title_present": sum(1 for i in items if i["raw"].get("title")),
            "with_skills": sum(1 for i in items if i["skills"]),
            "skill_counts": [len(i["skills"]) for i in items],
            "skill_freq": Counter(s for i in items for s in set(i["skills"])),
            "salary_present": sum(1 for i in items if i["raw"].get("salary_min") or i["raw"].get("salary_max")),
            "salary_predicted": sum(1 for i in items if (i["raw"].get("salary_min") or i["raw"].get("salary_max"))
                                    and str(i["raw"].get("salary_is_predicted")) == "1"),
            "exp_api": sum(1 for i in items if i["raw"].get("experience") or i["raw"].get("experience_level")),
            "exp_text": sum(1 for i in items if EXP_PATTERN.search(f"{i['norm'].title} {i['norm'].description_cleaned}")),
            "emp_api": sum(1 for i in items if i["raw"].get("contract_time") or i["raw"].get("contract_type")),
            "emp_values": Counter(f"{i['raw'].get('contract_time') or '-'}/{i['raw'].get('contract_type') or '-'}" for i in items),
            "wm_explicit": sum(1 for i in items if i["norm"].work_model in ("Remote", "Hybrid")),
            "wm_api": sum(1 for i in items if i["raw"].get("work_model") or i["raw"].get("workplace_type")),
            "created_present": sum(1 for i in items if i["raw"].get("created")),
            "url_present": sum(1 for i in items if i["raw"].get("redirect_url")),
            "truncated_desc": sum(1 for i in items if (i["raw"].get("description") or "").rstrip().endswith(("…", "...", "…"))),
        }
        return m

    overall = metrics(normalized)
    qm = [metrics([x for x in normalized if x["qi"] == qi]) for qi in range(len(per_query))]

    # city match per query
    for qi, pq in enumerate(per_query):
        target = city_of(pq["q"]["where"])
        items = [x for x in normalized if x["qi"] == qi]
        hit = sum(1 for x in items if (x["norm"].city or "").lower() == target
                  or target in (x["norm"].location_raw or "").lower()
                  or (target == "bengaluru" and "bangalore" in (x["norm"].location_raw or "").lower()))
        qm[qi]["city_match"] = hit

    # cross-query duplicate ids
    id_queries = {}
    for x in normalized:
        id_queries.setdefault(x["raw"].get("id"), set()).add(x["qi"])
    cross_query_dupes = sum(1 for s in id_queries.values() if len(s) > 1)

    # ---------- verdict (rule based, computed from observed data) ----------
    n = overall["total"]
    http_ok = all(pq["status"] == 200 for pq in per_query)
    all_nonempty = all(len(pq["results"]) > 0 for pq in per_query)
    uniq_rate = pct(overall["unique_ids"], n)
    city_match_rate = pct(sum(m["city_match"] for m in qm), n)
    company_cov = pct(overall["company_present"], n)
    skill_cov = pct(overall["with_skills"], n)
    sal_cov = pct(overall["salary_present"], n)
    exp_cov = pct(overall["exp_api"], n)
    desc_med = statistics.median(overall["desc_lens"]) if overall["desc_lens"] else 0

    core = [
        ("All 4 queries returned HTTP 200 with results", http_ok and all_nonempty),
        ("Unique-ID rate >= 95%", uniq_rate >= 95),
        ("Returned location matches requested city >= 80%", city_match_rate >= 80),
        ("Company present >= 95%", company_cov >= 95),
        ("Title + description + date + URL present >= 95%",
         min(pct(overall[k], n) for k in ("title_present", "desc_present", "created_present", "url_present")) >= 95),
        ("Skill-extraction coverage >= 50% (jobs with >=1 skill)", skill_cov >= 50),
    ]
    enrich = [
        ("Full descriptions (median length > 600 chars, i.e. beyond the ~500-char snippet cap)", desc_med > 600),
        ("Salary coverage >= 50%", sal_cov >= 50),
        ("Experience supplied by API >= 50%", exp_cov >= 50),
        ("Work model supplied by API >= 50%", pct(overall["wm_api"], n) >= 50),
    ]
    if not all(ok for _, ok in core):
        verdict, verdict_text = "C", "insufficient and requires another source"
    elif not all(ok for _, ok in enrich):
        verdict, verdict_text = "B", "usable with specific limitations/modifications"
    else:
        verdict, verdict_text = "A", "sufficient for our MVP"

    # ---------- report ----------
    L = []
    w = L.append
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    calls_this_run = len(per_query)
    w("# JobIntel — Data Quality & Feasibility Report (Adzuna)")
    w("")
    w(f"- **Generated:** `{now}`")
    w("- **Source under test:** Adzuna Jobs API (India, `/v1/api/jobs/in/search/1`)")
    w(f"- **Queries this run:** {calls_this_run} (results_per_page = {RESULTS_PER_PAGE}, page 1 only)")
    w(f"- **Adzuna calls consumed today:** {QUOTA_USED_BEFORE} earlier (as reported) + {calls_this_run} in this run = "
      f"**{QUOTA_USED_BEFORE + calls_this_run} of {QUOTA_TOTAL}** ({QUOTA_TOTAL - QUOTA_USED_BEFORE - calls_this_run} remaining)")
    w("- **Database:** temporary SQLite file (`jobintel_adzuna_feasibility.db` in the OS temp dir); PostgreSQL untouched")
    w("- **Raw responses:** `data/raw/` — " + ", ".join(f"`{pq['file']}`" for pq in per_query))
    w("- **Scope of evidence:** only this run's four queries. Earlier validation (195 Mumbai hits for \"data analyst\", "
      "10-record pipeline test) is not re-counted here.")
    w("")
    w("## 1. Verdict")
    w("")
    w(f"### Classification: **{verdict}** — {verdict_text}")
    w("")
    w("The class is computed by a fixed rule set from the observed metrics: **C** if any core criterion fails, "
      "**B** if all core criteria pass but any enrichment criterion fails, **A** if everything passes.")
    w("")
    w("| Tier | Criterion | Observed | Result |")
    w("| :--- | :--- | :--- | :---: |")
    obs = {
        core[0][0]: f"HTTP: {', '.join(str(pq['status']) for pq in per_query)}; results: {', '.join(str(len(pq['results'])) for pq in per_query)}",
        core[1][0]: f"{uniq_rate}%",
        core[2][0]: f"{city_match_rate}%",
        core[3][0]: f"{company_cov}%",
        core[4][0]: f"title {pct(overall['title_present'], n)}%, desc {pct(overall['desc_present'], n)}%, "
                    f"date {pct(overall['created_present'], n)}%, url {pct(overall['url_present'], n)}%",
        core[5][0]: f"{skill_cov}%",
        enrich[0][0]: f"median {desc_med:.0f}, max {max(overall['desc_lens'])} chars",
        enrich[1][0]: f"{sal_cov}%",
        enrich[2][0]: f"{exp_cov}%",
        enrich[3][0]: f"{pct(overall['wm_api'], n)}%",
    }
    for tier, rows in (("Core", core), ("Enrichment", enrich)):
        for name, ok in rows:
            w(f"| {tier} | {name} | {obs[name]} | {'PASS' if ok else 'FAIL'} |")
    w("")
    failed_core = [nm for nm, ok in core if not ok]
    failed_enrich = [nm for nm, ok in enrich if not ok]
    w("**Reasons:**")
    w("")
    if failed_core:
        for nm in failed_core:
            w(f"- Core criterion failed: {nm}.")
    else:
        w("- All core criteria passed: the API authenticates, honours keyword and city filters, returns unique, "
          "well-attributed postings (title, company, location, date, URL) that flow through the pipeline, and the "
          "snippets still yield skills.")
    for nm in failed_enrich:
        w(f"- Enrichment criterion failed: {nm}.")
    if verdict == "B":
        w("- Therefore Adzuna is viable as the MVP's posting source for discovery, geography, role and skill-demand "
          "analytics, but salary, experience level and full-description features must be treated as limited "
          "(see Section 9), or supplemented by a second source.")
    w("")
    w("## 2. Query audit")
    w("")
    w("| # | Query | HTTP | Results returned | Adzuna total `count` | Unique IDs | Duplicate IDs | Content duplicates* |")
    w("| :-: | :--- | :-: | ---: | ---: | ---: | ---: | ---: |")
    for i, (pq, m) in enumerate(zip(per_query, qm), 1):
        w(f"| {i} | {pq['q']['what']} — {pq['q']['where']} | {pq['status']} | {m['total']} | {pq['count_total']} | "
          f"{m['unique_ids']} | {m['dup_ids']} | {m['content_dupes']} |")
    w(f"| **All** | | | **{n}** | | **{overall['unique_ids']}** | **{overall['dup_ids']}** | **{overall['content_dupes']}** |")
    w("")
    w("\\*Content duplicate = same title + company + city under a different ID (likely reposts). "
      "Duplicate IDs are counted within each query; the \"All\" row counts repeated IDs across the combined set.")
    w("")
    w("## 3. Record counts (total vs unique vs duplicates)")
    w("")
    w("| Measure | Value |")
    w("| :--- | ---: |")
    w(f"| Total records returned | {n} |")
    w(f"| Unique records (by Adzuna ID) | {overall['unique_ids']} |")
    w(f"| Duplicate records (by Adzuna ID) | {overall['dup_ids']} |")
    w(f"| IDs appearing in more than one query | {cross_query_dupes} |")
    w(f"| Likely reposts (same title+company+city, different ID) | {overall['content_dupes']} |")
    w(f"| Inserted into temp SQLite DB as new | {db_inserted} |")
    w(f"| Skipped as already present in DB | {db_dupes} |")
    w("")
    w("## 4. Observed locations, roles and companies")
    w("")
    w("### 4.1 Location (normalized city) — all queries")
    w("")
    w(dist_table(overall["cities"], n, "City"))
    w("")
    w("### 4.2 Per-query location accuracy and city distribution")
    w("")
    for pq, m in zip(per_query, qm):
        w(f"**{pq['q']['what']} — {pq['q']['where']}**: {m['city_match']}/{m['total']} "
          f"({pct(m['city_match'], m['total'])}%) returned locations match the requested city. "
          f"Observed cities: " + ", ".join(f"{k} ({v})" for k, v in m["cities"].most_common()))
        w("")
    w("### 4.3 Raw location strings — all queries")
    w("")
    w(dist_table(overall["locations_raw"], n, "Adzuna location.display_name", top=25))
    w("")
    w("### 4.4 Observed job titles — all queries")
    w("")
    w(dist_table(overall["titles"], n, "Title", top=30))
    w("")
    w("### 4.5 Normalized role category (our classifier) — all queries")
    w("")
    w(dist_table(overall["roles"], n, "Role category"))
    w("")
    w("### 4.6 Adzuna's own category label")
    w("")
    w(dist_table(overall["adzuna_categories"], n, "Adzuna category"))
    w("")
    w("### 4.7 Role category per query")
    w("")
    for pq, m in zip(per_query, qm):
        w(f"- **{pq['q']['what']} — {pq['q']['where']}**: " + ", ".join(f"{k} ({v})" for k, v in m["roles"].most_common()))
    w("")
    w("### 4.8 Observed companies — all queries")
    w("")
    w(f"{len(overall['companies'])} distinct companies across {n} records.")
    w("")
    w(dist_table(overall["companies"], n, "Company", top=25))
    w("")
    w("## 5. Field availability and missing-field percentages")
    w("")
    w("Availability is measured on the **raw Adzuna payload** (what the API actually supplied), not on our "
      "normalized columns, because the normalizer fills defaults (e.g. `experience_level = Mid-level`, "
      "`work_model = Onsite`) that would otherwise mask gaps.")
    w("")
    w("| Field | Present | Missing | Missing % | Note |")
    w("| :--- | ---: | ---: | ---: | :--- |")

    def row(name, present, note=""):
        w(f"| {name} | {present} | {n - present} | {pct(n - present, n)}% | {note} |")

    row("title", overall["title_present"])
    row("company (company.display_name)", overall["company_present"])
    row("location (location.display_name)", overall["location_present"])
    row("description", overall["desc_present"], "snippet, see Section 6")
    row("posted/created date (`created`)", overall["created_present"])
    row("apply URL (`redirect_url`)", overall["url_present"])
    row("salary (min or max > 0)", overall["salary_present"],
        f"{overall['salary_predicted']} of these flagged `salary_is_predicted=1`")
    row("employment type (`contract_time`/`contract_type`)", overall["emp_api"])
    row("experience level (API field)", overall["exp_api"], "Adzuna has no such field")
    row("work model (API field)", overall["wm_api"], "Adzuna has no such field")
    w("")
    w("Inferred-from-text signals (heuristic, not API-supplied):")
    w("")
    w(f"- Experience/seniority cue in title or snippet (years, fresher, senior, lead, manager…): "
      f"{overall['exp_text']}/{n} ({pct(overall['exp_text'], n)}%)")
    w(f"- Work model explicitly Remote/Hybrid in text: {overall['wm_explicit']}/{n} ({pct(overall['wm_explicit'], n)}%); "
      f"the rest default to Onsite by our normalizer.")
    w("")
    w("Employment-type values observed (`contract_time/contract_type`):")
    w("")
    w(dist_table(overall["emp_values"], n, "contract_time/contract_type"))
    w("")
    w("## 6. Description-length statistics (characters, raw `description`)")
    w("")
    w("| Scope | N | Min | Median | Mean | Max | Ends with ellipsis (truncated) |")
    w("| :--- | ---: | ---: | ---: | ---: | ---: | ---: |")

    def lrow(label, m):
        d = m["desc_lens"]
        if d:
            w(f"| {label} | {len(d)} | {min(d)} | {statistics.median(d):.0f} | {statistics.mean(d):.0f} | {max(d)} | "
              f"{m['truncated_desc']} ({pct(m['truncated_desc'], len(d))}%) |")

    for pq, m in zip(per_query, qm):
        lrow(f"{pq['q']['what']} — {pq['q']['where']}", m)
    lrow("**All**", overall)
    w("")
    w("## 7. Skill-extraction coverage")
    w("")
    w("Extractor: existing `SkillExtractor` (dictionary/regex taxonomy) run on title + cleaned description snippet.")
    w("")
    w("| Scope | Jobs | Jobs with ≥1 skill | Coverage | Mean skills/job | Median |")
    w("| :--- | ---: | ---: | ---: | ---: | ---: |")
    for pq, m in zip(per_query, qm):
        sc = m["skill_counts"]
        w(f"| {pq['q']['what']} — {pq['q']['where']} | {m['total']} | {m['with_skills']} | {pct(m['with_skills'], m['total'])}% | "
          f"{statistics.mean(sc):.2f} | {statistics.median(sc):.0f} |")
    sc = overall["skill_counts"]
    w(f"| **All** | {n} | {overall['with_skills']} | {pct(overall['with_skills'], n)}% | {statistics.mean(sc):.2f} | {statistics.median(sc):.0f} |")
    w("")
    w("Jobs with ≥3 skills: " + f"{sum(1 for c in sc if c >= 3)}/{n} ({pct(sum(1 for c in sc if c >= 3), n)}%); "
      f"jobs with 0 skills: {sum(1 for c in sc if c == 0)}/{n}.")
    w("")
    w("Top extracted skills (jobs mentioning):")
    w("")
    w(dist_table(overall["skill_freq"], n, "Skill", top=20))
    w("")
    w("## 8. Salary and experience coverage")
    w("")
    w("| Scope | Salary present | Salary % | Predicted (of present) | Experience (API) % | Experience cue in text % |")
    w("| :--- | ---: | ---: | ---: | ---: | ---: |")
    for pq, m in zip(per_query, qm):
        w(f"| {pq['q']['what']} — {pq['q']['where']} | {m['salary_present']}/{m['total']} | {pct(m['salary_present'], m['total'])}% | "
          f"{m['salary_predicted']} | {pct(m['exp_api'], m['total'])}% | {pct(m['exp_text'], m['total'])}% |")
    w(f"| **All** | {overall['salary_present']}/{n} | {sal_cov}% | {overall['salary_predicted']} | {exp_cov}% | {pct(overall['exp_text'], n)}% |")
    w("")
    w("## 9. Known limitations (documented, not fixed in this phase)")
    w("")
    dsm = [x["norm"] for x in normalized if "data science manager" in x["norm"].title.lower()]
    w("1. **Descriptions are short snippets.** Median observed length " + f"{desc_med:.0f} chars; "
      f"{overall['truncated_desc']}/{n} end in an ellipsis. Full responsibilities/qualification sections are not available, "
      "which caps NLP richness and skill recall.")
    w(f"2. **Salary is frequently missing.** Present on {overall['salary_present']}/{n} records ({sal_cov}%); "
      f"{overall['salary_predicted']} of those are Adzuna-predicted values rather than employer-stated, so they must not be "
      "treated as ground truth.")
    w(f"3. **Experience level is not supplied.** API coverage {exp_cov}%. The normalizer's `Mid-level` is a placeholder "
      "default, not data; any experience feature must derive from text cues and be labelled inferred.")
    w(f"4. **Skill extraction can be sparse.** Coverage {skill_cov}%, mean {statistics.mean(sc):.2f} skills/job, because the "
      "input is a snippet.")
    dsm_bad = [d for d in dsm if d.role_category == "Software Engineering"]
    if dsm_bad:
        w("5. **\"Data Science Manager\" classification is still wrong.** Observed: "
          + "; ".join(f"\"{d.title}\" → {d.role_category}" for d in dsm_bad[:5]) + ".")
    elif dsm:
        w(f"5. **\"Data Science Manager\" classification (resolved).** Earlier runs mapped these titles to Software Engineering; "
          f"in this run all {len(dsm)} such records map to: "
          + ", ".join(sorted({d.role_category for d in dsm})) + ". Guarded by a regression test.")
    else:
        w("5. **\"Data Science Manager\" classification:** no such title appeared in this run, so it is not re-measured here.")
    w("6. **Other observations:** work model is keyword-inferred (default Onsite); employment type depends on Adzuna's "
      "`contract_time` which is often absent; relevance ranking and ~20-record pages mean one call yields a small slice "
      "of a much larger result set (see `count` in Section 2).")
    w("")
    w("## 10. Limits of this test")
    w("")
    w(f"- {n} records from 4 queries (page 1, {RESULTS_PER_PAGE} per query) is a feasibility sample, not a market census.")
    w("- Only two role families and four cities were tested; other roles (e.g. software, finance) were not evaluated today.")
    w("- Skill coverage reflects our current taxonomy and extractor; it is a joint measure of source and extractor.")
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")

    print(f"Report written: {REPORT_PATH}")
    print(f"VERDICT: {verdict} ({verdict_text})")
    print(f"total={n} unique={overall['unique_ids']} dupIDs={overall['dup_ids']} contentDupes={overall['content_dupes']} "
          f"skillCov={skill_cov}% salary={sal_cov}% exp={exp_cov}% descMedian={desc_med:.0f}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "fetch":
        fetch()
    elif mode == "analyze":
        analyze()
    else:
        sys.exit("usage: run_adzuna_feasibility.py fetch|analyze")
