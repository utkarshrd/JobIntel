"""The web UI (web/) is served by the API; static checks on its code (no browser needed here:
scripts/ui_e2e.js drives a real browser against the running stack)."""
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")


def test_ui_pages_and_assets_are_served(client):
    html = client.get("/ui/")
    assert html.status_code == 200 and "JobIntel" in html.text and 'src="app.js"' in html.text
    assert client.get("/ui/app.js").status_code == 200 and "javascript" in client.get("/ui/app.js").headers["content-type"]
    assert client.get("/ui/style.css").status_code == 200
    assert client.get("/ui/nope.js").status_code == 404


def test_root_redirects_browsers_but_not_api_clients(client):
    r = client.get("/", headers={"Accept": "text/html,application/xhtml+xml"}, follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/ui/"
    j = client.get("/")
    assert j.status_code == 200 and j.json()["ui"] == "/ui/"


def test_ui_never_injects_untrusted_text_as_html():
    """Job postings come from external sources: the UI must only use textContent / text nodes."""
    js = open(os.path.join(WEB, "app.js"), encoding="utf-8").read()
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert banned not in js, f"{banned} found in app.js"
    assert "createTextNode" in js


def test_ui_only_calls_endpoints_that_exist(client):
    js = open(os.path.join(WEB, "app.js"), encoding="utf-8").read()
    called = set(re.findall(r'api\(\s*[`"]([a-z\-/]+?)(?:/?\$\{|[`"/])', js))
    spec = client.get("/api/v1/openapi.json").json()["paths"]
    known = {p.replace("/api/v1", "").strip("/").split("/")[0] for p in spec} | {p.strip("/").split("/")[0] for p in spec}
    for c in called:
        assert c.strip("/").split("/")[0] in known, f"UI calls unknown endpoint {c}"
    assert {"recommendations", "jobs", "analytics", "users", "skill-gap", "ingestion", "health"} <= {c.split("/")[0] for c in called}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_app_js_has_valid_syntax():
    r = subprocess.run(["node", "--check", os.path.join(WEB, "app.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_twsma_report_is_cached_until_jobs_change(client, db_session, monkeypatch):
    from backend.app.api.v1.endpoints import analytics
    from backend.app.models import Job
    from backend.app.services import twsma_service as tw
    calls = []
    real = tw.build_twsma_report
    monkeypatch.setattr(tw, "build_twsma_report", lambda recs, *a, **k: (calls.append(1), real(recs, *a, **k))[1])
    analytics._TWSMA_CACHE.clear()
    db_session.add(Job(job_id="c1", source="t", title="Data Analyst", company_name="A", description="sql"))
    db_session.commit()
    a, b = client.get("/api/v1/analytics/twsma").json(), client.get("/api/v1/analytics/twsma").json()
    assert a == b and len(calls) == 1                      # second call served from cache
    db_session.add(Job(job_id="c2", source="t", title="Data Scientist", company_name="B", description="python"))
    db_session.commit()
    assert client.get("/api/v1/analytics/twsma").json()["total_jobs"] == 2 and len(calls) == 2   # data changed -> recomputed
