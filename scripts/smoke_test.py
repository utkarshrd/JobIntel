"""
End-to-end smoke test against the RUNNING stack (PostgreSQL + FastAPI, which also serves the web UI).

  1. start PostgreSQL;  alembic upgrade head;  python scripts/run_ingestion.py --ats   (or load saved data)
  2. python -m uvicorn backend.app.main:app --port 8000
  3. python scripts/smoke_test.py          (then, optionally: node scripts/ui_e2e.js  for the real-browser UI test)

It registers ONE temporary account (unique email) through the real API, exercises sign-in, profile, recommendations,
interactions, analytics and persistence, then deletes that account again through the API (cascading its data).
Jobs and everything else are left untouched. Exit code 1 on any failure.
"""
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

API = os.getenv("API_URL", "http://127.0.0.1:8000/api/v1")
SITE = API.rsplit("/api/", 1)[0]
PASSWORD = "smoke-test-passphrase"
results = []
AUTH = {}   # bearer header of the temporary account, set after registration


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    return ok


def get(path, **kw):
    return requests.get(f"{API}/{path}", timeout=60, headers=AUTH, **kw)


def main():
    email = f"smoke_{int(time.time())}@example.com"
    h = get("health").json()
    check("1 health: backend online, database healthy", h["status"] == "online" and h["database"] == "healthy", str(h))

    r = get("jobs/", params={"page_size": 5}).json()
    check("2 jobs retrievable", r["total"] > 1000 and len(r["items"]) == 5, f"total={r['total']}")
    job = get(f"jobs/{r['items'][0]['id']}")
    check("2b job detail", job.status_code == 200 and job.json()["title"] == r["items"][0]["title"])
    check("2c missing job -> 404", get("jobs/99999999").status_code == 404)
    check("2d no placeholder experience level in stored jobs",
          all(j["experience_level"] is None for j in get("jobs/", params={"page_size": 50}).json()["items"]))
    srcs = {s: get("jobs/", params={"source": s, "page_size": 1}).json()["total"] for s in ("adzuna", "greenhouse", "lever")}
    check("2e jobs from all three live sources", all(v > 0 for v in srcs.values()), str(srcs))
    check("2f ATS jobs carry full descriptions",
          all(len(j["description"]) > 1500 for j in get("jobs/", params={"source": "greenhouse", "page_size": 5}).json()["items"]))

    # ---- accounts
    check("3 anonymous access to private data is refused", get("recommendations/1").status_code == 401 and get("auth/me").status_code == 401)
    check("3a open profile creation is closed", requests.post(f"{API}/users/", json={"email": email, "full_name": "x"}, timeout=30).status_code == 403)
    check("3b weak password rejected", requests.post(f"{API}/auth/register", timeout=30, json={"email": email, "full_name": "Smoke Test", "password": "short"}).status_code == 422)
    reg = requests.post(f"{API}/auth/register", timeout=30, json={"email": email, "full_name": "Smoke Test", "password": PASSWORD})
    check("3c account registered and signed in", reg.status_code == 201 and reg.json()["access_token"], reg.text[:80])
    uid, AUTH["Authorization"] = reg.json()["user"]["id"], f"Bearer {reg.json()['access_token']}"
    check("3d duplicate email rejected (409)", requests.post(f"{API}/auth/register", timeout=30, json={"email": email.upper(), "full_name": "x", "password": PASSWORD}).status_code == 409)
    check("3e wrong password gives a generic 401", requests.post(f"{API}/auth/login", timeout=30, json={"email": email, "password": "wrong-wrong-wrong"}).status_code == 401)
    login = requests.post(f"{API}/auth/login", timeout=30, json={"email": email, "password": PASSWORD})
    check("3f sign in with email + password", login.status_code == 200 and login.json()["user"]["id"] == uid)
    check("3g /auth/me returns the profile and no credentials", get("auth/me").json()["email"] == email and "password" not in get("auth/me").text)
    other = requests.get(f"{API}/users/{uid + 100000}", headers=AUTH, timeout=30)
    check("3h another user's data is refused", other.status_code == 401)

    rec0 = get(f"recommendations/{uid}").json()
    check("3i new account is served as cold start (recency only, flagged)", rec0["personalization_mode"] == "cold_start" and rec0["cold_start"] and rec0["count"] > 0)

    upd = requests.put(f"{API}/users/{uid}", timeout=30, headers=AUTH, json={
        "target_role": "Data Analyst", "preferred_roles": ["Data & Analytics"], "preferred_locations": ["Mumbai"],
        "experience_years": 2, "skills": [{"skill_name": "SQL"}, {"skill_name": "python"}, {"skill_name": "ml"}]})
    names = sorted(s["skill_name"] for s in upd.json()["skills"])
    check("4 profile/skills saved (alias resolved)", upd.status_code == 200 and names == ["machine learning", "python", "sql"], str(names))

    t0 = time.time()
    rec1 = get(f"recommendations/{uid}", params={"limit": 10}).json()
    dt = time.time() - t0
    top = rec1["items"][0]
    check("5 profile-based recommendations", rec1["personalization_mode"] == "profile_based" and not rec1["cold_start"] and rec1["count"] == 10)
    check("5a recommendation latency under 3s at current scale", dt < 3, f"{dt:.2f}s")
    check("5b ranked 1..10 with descending scores", [i["rank"] for i in rec1["items"]] == list(range(1, 11))
          and all(a["match_score"] >= b["match_score"] for a, b in zip(rec1["items"], rec1["items"][1:])))
    check("5c explanations present and signal-backed", bool(top["explanation"]["reasons"]) and all(
        i["explanation"]["primary_reason"] for i in rec1["items"]), "; ".join(top["explanation"]["reasons"])[:160])
    for strat in ("skills", "content", "popularity"):
        s = get(f"recommendations/{uid}", params={"ranking_strategy": strat, "limit": 5})
        check(f"5d strategy {strat}", s.status_code == 200 and s.json()["count"] == 5)

    # ---- real interaction through the API, then verify it changes personalization
    target = top["job"]["id"]
    ix = requests.post(f"{API}/users/interactions", json={"user_id": uid, "job_id": target, "interaction_type": "save"}, timeout=30, headers=AUTH)
    check("6 interaction recorded", ix.status_code == 201 and ix.json()["interaction_type"] == "save")
    check("6b bad interaction rejected", requests.post(f"{API}/users/interactions", timeout=30, headers=AUTH,
          json={"user_id": uid, "job_id": target, "interaction_type": "bogus"}).status_code == 422)
    rec2 = get(f"recommendations/{uid}", params={"limit": 10}).json()
    saved = next((i for i in rec2["items"] if i["job"]["id"] == target), None)
    check("7 interaction-informed state recognised", rec2["personalization_mode"] == "interaction_informed"
          and rec2["interactions_used"] == 1 and rec2["weights_used"]["behavior"] > 0)
    check("7b saved job flagged and behavior reasons shown", saved is not None and saved["interaction_state"] == "saved"
          and any("you saved" in r for i in rec2["items"] for r in i["explanation"]["reasons"]))
    p = get(f"users/{uid}/personalization").json()
    check("7c personalization summary", p["personalization_mode"] == "interaction_informed"
          and p["learned_from_interactions"]["counts_by_type"] == {"save": 1})
    check("7d interaction history", [h["interaction_type"] for h in get(f"users/{uid}/interactions").json()] == ["save"])

    tw = get("analytics/twsma").json()
    check("8 TWSMA report", tw["total_jobs"] > 0 and tw["top_skills"] and tw["skill_cooccurrence"] is not None
          and tw["posting_dates"]["trend_supported"] is False, f"jobs={tw['total_jobs']}")
    check("8b analytics summary", get("analytics/summary").json()["total_jobs"] == tw["total_jobs"])
    gap = get("skill-gap/analyze", params={"user_id": uid, "target_role": "Data & Analytics"}).json()
    check("8c skill gap", gap["total_jobs_analyzed"] > 0 and any(s["user_has_skill"] for s in gap["skills"]) and any(not s["user_has_skill"] for s in gap["skills"]))
    check("8d job-level skill gap", get(f"skill-gap/job/{target}", params={"user_id": uid}).status_code == 200)
    check("8e ingestion runs from live sources", {r["source"] for r in get("ingestion/runs", params={"limit": 20}).json()} >= {"adzuna_live", "ats_boards"})

    # ---- web UI served by the API
    check("9 web UI served at /ui/", requests.get(f"{SITE}/ui/", timeout=10).status_code == 200 and "JobIntel" in requests.get(f"{SITE}/ui/", timeout=10).text)
    check("9b web UI assets served", all(requests.get(f"{SITE}/ui/{a}", timeout=10).status_code == 200 for a in ("app.js", "style.css")))
    check("9c browser root redirects to the UI", requests.get(SITE + "/", headers={"Accept": "text/html"}, timeout=10, allow_redirects=False).status_code in (302, 307))

    # ---- PostgreSQL persistence (direct DB read)
    from backend.app.core.database import SessionLocal, engine
    from backend.app.models import Interaction, Job, JobSkill, User, UserSkill
    db = SessionLocal()
    try:
        check("10 backend DB is PostgreSQL", engine.dialect.name == "postgresql", engine.dialect.name)
        u = db.query(User).filter(User.email == email).one()
        check("10b user persisted with profile", u.target_role == "Data Analyst" and u.preferred_locations == ["Mumbai"])
        check("10c password stored only as a salted hash", u.password_hash.startswith("scrypt$") and PASSWORD not in u.password_hash)
        check("10d user skills persisted", db.query(UserSkill).filter(UserSkill.user_id == u.id).count() == 3)
        check("10e interaction persisted", db.query(Interaction).filter(Interaction.user_id == u.id, Interaction.job_id == target,
              Interaction.interaction_type == "save").count() == 1)
        check("10f jobs and job-skills persisted", db.query(Job).count() > 0 and db.query(JobSkill).count() > 0,
              f"jobs={db.query(Job).count()} job_skills={db.query(JobSkill).count()}")
    finally:
        db.close()

    # ---- clean up ONLY the temporary account, through the API (cascades its skills and interactions)
    d = requests.delete(f"{API}/auth/me", json={"password": PASSWORD}, headers=AUTH, timeout=30)
    db = SessionLocal()
    try:
        check("11 temporary account deleted through the API, data cascaded", d.status_code == 204
              and db.query(User).filter(User.email == email).count() == 0 and db.query(Interaction).filter(Interaction.user_id == uid).count() == 0)
    finally:
        db.close()

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
