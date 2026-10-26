/* JobIntel web UI: a small single-page app (no build step, no framework).
   Every number shown comes from the FastAPI backend; this file only fetches and renders.
   All text from the API is inserted as text nodes (never as HTML): job postings come from external sources.
   Authentication: normal email + password sign-in; the signed session token is kept in the browser and never shown. */
"use strict";

// ---------------------------------------------------------------- tiny DOM helper
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return e;
}
// append / replaceChildren accept nested arrays and skip null/false (conditional children), like h() does.
for (const method of ["append", "replaceChildren"]) {
  const native = Element.prototype[method];
  Element.prototype[method] = function (...kids) { return native.apply(this, kids.flat(Infinity).filter((k) => k != null && k !== false)); };
}
const $ = (s, el = document) => el.querySelector(s);
const pct = (x) => `${Math.round(x * 100)}%`;
const SPECIAL = { cpp: "C++", csharp: "C#", "node.js": "Node.js", "next.js": "Next.js", "ci/cd": "CI/CD", "a/b testing": "A/B Testing",
  "scikit-learn": "scikit-learn", "power bi": "Power BI", "rest api": "REST API", "sql server": "SQL Server", dbt: "dbt", golang: "Go" };
const ACRONYMS = new Set(["sql", "aws", "gcp", "etl", "nlp", "llm", "rag", "sas", "seo", "crm", "sap", "vba", "css", "html", "php", "mlops", "bi", "api", "ai", "ml", "hr"]);
// Display name for a canonical (lower-case) skill/term; anything that already has capitals is left alone.
const title = (s) => (!s || s !== s.toLowerCase() ? s : SPECIAL[s] || s.split(" ").map((w) => (ACRONYMS.has(w) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1))).join(" "));
const initials = (name) => (name || "?").trim().split(/\s+/).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
const firstName = (name) => (name || "").trim().split(/\s+/)[0];

// ---------------------------------------------------------------- session + API
const S = { token: localStorage.getItem("ji_token"), user: null };
function setSession(token, user) {
  S.token = token || null; S.user = user || null;
  token ? localStorage.setItem("ji_token", token) : localStorage.removeItem("ji_token");
  renderChrome();
}
function sessionExpiry() {                                   // for display only; the server is the authority
  try { return new Date(JSON.parse(atob(S.token.split(".")[0].replace(/-/g, "+").replace(/_/g, "/"))).exp * 1000); } catch (e) { return null; }
}

async function api(path, { method = "GET", params, body } = {}) {
  const url = new URL("/api/v1/" + path.replace(/^\//, ""), location.origin);
  for (const [k, v] of Object.entries(params || {})) if (v !== "" && v != null && v !== false) url.searchParams.set(k, v);
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (S.token) headers.Authorization = "Bearer " + S.token;
  let res;
  try { res = await fetch(url, { method, headers, body: body ? JSON.stringify(body) : undefined }); }
  catch (e) { throw Object.assign(new Error("Cannot reach the server. Please check that the backend is running."), { status: 0 }); }
  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }
  if (!res.ok) {
    let msg = data && data.detail;
    if (Array.isArray(msg)) msg = msg.map((d) => (d.loc ? d.loc[d.loc.length - 1] + ": " : "") + d.msg).join("; ");
    const err = Object.assign(new Error(msg || res.statusText), { status: res.status });
    if (res.status === 401 && S.token && !path.startsWith("auth/login") && !path.startsWith("auth/register")) {
      setSession(null); err.sessionExpired = true;              // stale or expired session: back to sign-in
      toast("Your session has expired. Please sign in again."); location.hash = "#/login?next=" + encodeURIComponent(currentRoute().path);
    }
    throw err;
  }
  return data;
}
const _cache = {};
async function cached(key, fn, ttl = 60000) {            // tiny client cache for the heavy public analytics
  const c = _cache[key];
  if (c && Date.now() - c.t < ttl) return c.v;
  const v = await fn(); _cache[key] = { t: Date.now(), v }; return v;
}
const twsma = () => cached("twsma", () => api("analytics/twsma"));

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 3000);
}

// ---------------------------------------------------------------- small components
const metric = (v, l, tip) => h("div", { class: "card metric", title: tip }, h("div", { class: "v" }, v), h("div", { class: "l" }, l));
const banner = (kind, ...kids) => h("div", { class: "banner " + kind }, ...kids);
const skeleton = (n = 3) => h("div", null, Array.from({ length: n }, () => h("div", { class: "skeleton" })));
const link = (href, text, cls) => h("a", { href, class: cls }, text);

function bars(items, { label, value, total, fmt, cls } = {}) {
  const max = Math.max(1, ...items.map(value));
  return h("div", { class: "bars" }, items.map((it) => {
    const v = value(it);
    return h("div", { class: "b" }, h("span", { title: label(it) }, label(it)),
      h("div", { class: "t" }, h("div", { class: "f " + (cls ? cls(it) : ""), style: `width:${(100 * v) / (total || max)}%` })),
      h("span", { class: "muted" }, fmt ? fmt(it) : v));
  }));
}
function table(head, rows, numeric = []) {
  return h("table", null, h("thead", null, h("tr", null, head.map((c, i) => h("th", { class: numeric.includes(i) ? "n" : "" }, c)))),
    h("tbody", null, rows.map((r) => h("tr", null, r.map((c, i) => h("td", { class: numeric.includes(i) ? "n" : "" }, c))))));
}
function chips(names, cls) { return h("div", { class: "chips" }, names.map((n) => h("span", { class: "chip " + (cls || "") }, n))); }
const errorBox = (e) => banner("bad", e.message || "Something went wrong. Please try again.");
function emptyState(heading, text, action) { return h("div", { class: "card", style: "text-align:center;padding:34px" }, h("h3", null, heading), h("p", { class: "muted" }, text), action); }

// ---------------------------------------------------------------- job card
const ACTIONS = [["save", "Save", "Saved", "saved"], ["apply", "Mark applied", "Applied", "marked as applied"], ["skip", "Skip", "Skipped", "skipped"]];

function jobCard(job, { rec, onChange } = {}) {
  const ex = rec && rec.explanation;
  const matched = new Set((ex && ex.matched_skills) || []);
  const meta = [job.company_name || "Company not disclosed", job.city || job.location_raw || "location n/a", job.work_model, job.employment_type].filter(Boolean);
  meta.push(job.salary_min ? `INR ${Math.round(job.salary_min).toLocaleString()}${job.salary_max ? " - " + Math.round(job.salary_max).toLocaleString() : "+"}` : "salary not disclosed");
  const detail = h("div", { class: "full", hidden: true });
  const done = new Set(rec && rec.interaction_state ? [{ saved: "save", applied: "apply", clicked: "click", viewed: "view" }[rec.interaction_state]] : []);
  const heading = (rec ? `#${rec.rank}  ` : "") + job.title;
  const reasons = ex && ex.reasons && ex.reasons.length ? ex.reasons : ex ? [ex.primary_reason] : [];
  return h("article", { class: "card job" },
    h("div", { class: "logo-co", "aria-hidden": "true" }, (job.company_name || "?")[0].toUpperCase()),
    h("div", null,
      h("h3", null, job.source_url ? h("a", { href: job.source_url, target: "_blank", rel: "noopener" }, heading) : heading),
      h("div", { class: "meta" }, meta.join(" · ")),
      h("div", { class: "chips" },
        job.role_category && h("span", { class: "chip role" }, job.role_category),
        (job.extracted_skills || []).slice(0, 10).map((s) => h("span", { class: "chip " + (matched.has(s.name) ? "good" : "") }, (matched.has(s.name) ? "✓ " : "") + (s.display_name || s.name))),
        !(job.extracted_skills || []).length && h("span", { class: "muted small" }, "No skills extracted (short description)"))),
    rec ? h("div", { class: "score" }, h("div", { class: "n", title: "Relative ranking score in [0,1]; not a probability of fit" }, rec.match_score.toFixed(2)),
      h("div", { class: "match" }, h("i", { style: `width:${Math.round(rec.match_score * 100)}%` })), h("div", { class: "rk" }, "match score")) : h("span"),
    ex && h("details", { class: "full why" }, h("summary", null, `Why this job · ${reasons.length} reason${reasons.length === 1 ? "" : "s"}`),
      h("ul", null, reasons.map((r) => h("li", null, r))),
      h("div", { class: "small", style: "margin-top:6px" }, h("b", null, "Matched skills: "), (ex.matched_skills || []).map(title).join(", ") || "none", " · ",
        h("b", null, "Not in your profile: "), (ex.missing_skills || []).map(title).join(", ") || "none listed"),
      ex.experience_fit && h("div", { class: "small muted" }, ex.experience_fit),
      h("div", { class: "small muted" }, "Signal scores (n/a = not assessable): " + Object.entries(rec.component_scores || {}).map(([k, v]) => `${k} ${v == null ? "n/a" : v.toFixed(2)}`).join(", "))),
    detail,
    h("div", { class: "actions" },
      h("button", { class: "btn sm ghost", onclick: async () => { await toggleDetail(job, detail); try { await api("users/interactions", { method: "POST", body: { user_id: S.user.id, job_id: job.id, interaction_type: "view", metadata_payload: { source: "web" } } }); } catch (e) { /* view is best-effort */ } } }, "Details"),
      ACTIONS.map(([type, label, doneLabel, verb]) => {
        const b = h("button", { class: "btn sm ghost" + (done.has(type) ? " on" : "") }, done.has(type) ? "✓ " + doneLabel : label);
        b.addEventListener("click", async () => {
          b.disabled = true;
          try { await api("users/interactions", { method: "POST", body: { user_id: S.user.id, job_id: job.id, interaction_type: type, metadata_payload: { source: "web" } } });
                toast(`Job ${verb}. Your feed will use this.`); b.classList.add("on"); b.textContent = "✓ " + doneLabel; if (onChange) onChange(); }
          catch (e) { if (!e.sessionExpired) toast(e.message); }
          b.disabled = false; });
        return b;
      }),
      job.source_url && h("a", { class: "btn sm ghost", href: job.source_url, target: "_blank", rel: "noopener" }, "Open original posting ↗")));
}
async function toggleDetail(job, box) {
  if (!box.hidden) { box.hidden = true; return; }
  box.hidden = false; box.replaceChildren(h("div", { class: "desc" }, job.description_cleaned || job.description || "No description."),
    h("div", { class: "small muted" }, `Source: ${job.source} · posted ${String(job.posted_at || "n/a").slice(0, 10)} · last seen ${String(job.last_seen_at).slice(0, 10)}`));
  try {
    const g = await api(`skill-gap/job/${job.id}`, { params: { user_id: S.user.id } });
    box.append(h("div", { class: "why", style: "border-radius:8px;padding:8px 12px;margin-top:8px" }, g.note ? g.note : [h("b", null, "Your skills vs this posting — "), "matched: " + (g.matched_skills.join(", ") || "none"), " · missing: " + (g.missing_skills.join(", ") || "none")]));
  } catch (e) { /* skill comparison is optional */ }
}

// ---------------------------------------------------------------- pages: auth
function passwordField(label, { autocomplete, id } = {}) {
  const input = h("input", { type: "password", required: true, autocomplete, id, minlength: 1 });
  const toggle = h("button", { type: "button", "aria-label": "Show or hide password", onclick: () => { input.type = input.type === "password" ? "text" : "password"; toggle.textContent = input.type === "password" ? "Show" : "Hide"; } }, "Show");
  return { input, el: h("label", { class: "pw" }, label, input, toggle) };
}
const afterAuth = (q, fallback) => { const next = q.next && q.next.startsWith("/") ? q.next : fallback; if (location.hash === "#" + next) route(); else location.hash = "#" + next; };

async function loginPage(main, q) {
  document.title = "Sign in · JobIntel";
  const email = h("input", { type: "email", required: true, autocomplete: "email", placeholder: "you@example.com" });
  const pw = passwordField("Password", { autocomplete: "current-password" });
  const err = h("p", { class: "err", role: "alert" });
  const go = h("button", { class: "btn block", type: "submit" }, "Sign in");
  const form = h("form", { class: "card", novalidate: true, onsubmit: async (ev) => {
    ev.preventDefault(); err.textContent = ""; go.disabled = true; go.textContent = "Signing in…";
    try { const r = await api("auth/login", { method: "POST", body: { email: email.value.trim(), password: pw.input.value } });
          setSession(r.access_token, r.user); toast(`Welcome back, ${firstName(r.user.full_name)}!`); afterAuth(q, "/feed"); }
    catch (e) { err.textContent = e.message; go.disabled = false; go.textContent = "Sign in"; } } },
    h("label", null, "Email", email), pw.el, err, go);
  main.append(h("div", { class: "authwrap" }, h("h1", null, "Welcome back"),
    h("p", { class: "sub" }, q.next ? "Sign in to continue." : "Sign in to see your personalised job feed."), form,
    h("p", { class: "alt" }, "New to JobIntel? ", link("#/register" + (q.next ? "?next=" + encodeURIComponent(q.next) : ""), "Create an account"))));
  email.focus();
}

async function registerPage(main, q) {
  document.title = "Create account · JobIntel";
  const name = h("input", { required: true, autocomplete: "name", placeholder: "Your full name" });
  const email = h("input", { type: "email", required: true, autocomplete: "email", placeholder: "you@example.com" });
  const pw = passwordField("Password", { autocomplete: "new-password" });
  const pw2 = passwordField("Confirm password", { autocomplete: "new-password" });
  const bar = h("i"), hint = h("div", { class: "hint" }, "At least 8 characters. A longer phrase is stronger.");
  pw.input.addEventListener("input", () => { const v = pw.input.value; const s = Math.min(4, (v.length >= 8) + (v.length >= 12) + (/[A-Z]/.test(v) && /[a-z]/.test(v)) + (/\d|\W/.test(v)));
    bar.style.width = `${s * 25}%`; bar.style.background = ["var(--bad)", "var(--bad)", "var(--warn)", "var(--good)", "var(--good)"][s]; });
  const err = h("p", { class: "err", role: "alert" });
  const go = h("button", { class: "btn block", type: "submit" }, "Create account");
  const form = h("form", { class: "card", novalidate: true, onsubmit: async (ev) => {
    ev.preventDefault(); err.textContent = "";
    if (pw.input.value.length < 8) return (err.textContent = "Password must be at least 8 characters.");
    if (pw.input.value !== pw2.input.value) return (err.textContent = "The two passwords do not match.");
    go.disabled = true; go.textContent = "Creating account…";
    try { const r = await api("auth/register", { method: "POST", body: { full_name: name.value.trim(), email: email.value.trim(), password: pw.input.value } });
          setSession(r.access_token, r.user); toast("Account created. Let's set up your profile."); location.hash = "#/profile?welcome=1"; }
    catch (e) { err.textContent = e.message; go.disabled = false; go.textContent = "Create account"; } } },
    h("label", null, "Full name", name), h("label", null, "Email", email), pw.el, h("div", { class: "strength" }, bar), hint, pw2.el, err, go);
  main.append(h("div", { class: "authwrap" }, h("h1", null, "Create your account"),
    h("p", { class: "sub" }, "Get recommendations that explain themselves. Takes under a minute."), form,
    h("p", { class: "alt" }, "Already have an account? ", link("#/login" + (q.next ? "?next=" + encodeURIComponent(q.next) : ""), "Sign in"))));
  name.focus();
}

// ---------------------------------------------------------------- pages: dashboard
async function dashboardPage(main) {
  document.title = "Dashboard · JobIntel";
  const [r, runs] = await Promise.all([twsma(), api("ingestion/runs", { params: { limit: 5 } })]);
  if (!S.user) main.append(h("section", { class: "hero" }, h("h1", null, "Job-market intelligence with recommendations that explain themselves"),
    h("p", null, `Analytics over ${r.total_jobs.toLocaleString()} real postings, and a personalised feed that tells you why each job was ranked where it is.`),
    h("div", { class: "row" }, link("#/register", "Create a free account", "btn"), link("#/jobs", "Browse jobs", "btn ghost"), link("#/about", "How it works", "btn ghost"))));
  else main.append(h("h1", null, `Hello, ${firstName(S.user.full_name)}`), h("p", { class: "sub" }, "Here is the market snapshot. Your personalised feed is under My Feed."));
  if (!r.total_jobs) return main.append(banner("info", "No jobs stored yet. Run ", h("code", null, "python scripts/run_ingestion.py --ats"), "."));
  const cov = r.skill_coverage, co = r.company_distribution;
  main.append(h("div", { class: "grid g4" },
    metric(r.total_jobs.toLocaleString(), "jobs stored"), metric(co.distinct_companies.toLocaleString(), "distinct companies", `${co.undisclosed_count} postings undisclosed`),
    metric(r.location_distribution.items.length, "cities"), metric(`${cov.coverage_percentage}%`, "jobs with extracted skills", `mean ${cov.mean_skills_per_job} skills per job`)));
  main.append(banner("info", "Statistics describe the collected sample, not the whole job market. Descriptions from Adzuna are short snippets; company-board postings are full text."));
  main.append(h("div", { class: "grid g2" },
    h("div", { class: "card" }, h("h3", null, "Top skills"), bars(r.top_skills.slice(0, 12), { label: (s) => title(s.skill), value: (s) => s.job_count, fmt: (s) => s.job_count })),
    h("div", { class: "card" }, h("h3", null, "Role categories"), bars(r.role_distribution.items, { label: (s) => s.role_category, value: (s) => s.job_count, fmt: (s) => s.percentage + "%" }))));
  main.append(h("div", { class: "grid g2" },
    h("div", { class: "card" }, h("h3", null, "Cities"), bars(r.location_distribution.items.slice(0, 8), { label: (s) => s.city, value: (s) => s.job_count })),
    h("div", { class: "card" }, h("h3", null, "Most frequent companies"), table(["Company", "Postings"], co.items.slice(0, 8).map((c) => [c.company, c.job_count]), [1]))));
  if (runs.length) main.append(h("div", { class: "card" }, h("h3", null, "Recent data collection runs"),
    table(["Run", "Source", "Status", "Fetched", "New", "Started"], runs.map((x) => [x.id, x.source, x.status, x.total_fetched, x.new_inserted, String(x.started_at).slice(0, 16).replace("T", " ")]), [3, 4])));
}

// ---------------------------------------------------------------- pages: feed
const MODE = {
  cold_start: ["warn", "Getting started — you have no profile details and no activity yet, so jobs are ordered by recency only. This is not personalised. Add your skills in your profile, or save/apply to jobs."],
  profile_based: ["info", "Profile-based — ranked from your profile (skills, roles, locations, text). No interaction history is used yet."],
  interaction_informed: ["good", "Interaction-informed — ranked from your profile and your own activity (saves, applies, views, skips)."],
};
async function feedPage(main) {
  document.title = "My feed · JobIntel";
  main.append(h("h1", null, "My feed"), h("p", { class: "sub" }, "Ranked, explainable recommendations."));
  const state = { strategy: "hybrid", limit: 15 }, body = h("div");
  const load = async () => {
    const y = scrollY; body.style.opacity = ".5";
    try {
      const res = await api(`recommendations/${S.user.id}`, { params: { ranking_strategy: state.strategy, limit: state.limit } });
      const [kind, text] = state.strategy === "hybrid" ? MODE[res.personalization_mode] : ["info", `Baseline strategy "${state.strategy}" ignores your activity by design.`];
      const used = Object.entries(res.weights_used).filter(([, v]) => v > 0).map(([k, v]) => `${k} ${pct(v)}`).join(", ");
      body.replaceChildren(banner(kind, text, res.interactions_used ? ` (${res.interactions_used} interactions used)` : "", res.personalization_mode !== "interaction_informed" && state.strategy === "hybrid" ? [" ", link("#/profile", "Complete your profile")] : null),
        h("p", { class: "small muted" }, "Signal weights used for you (renormalised over the signals you have data for): " + used),
        res.items.length ? res.items.map((rec) => jobCard(rec.job, { rec, onChange: load })) : emptyState("Nothing to show", "No active jobs to recommend right now."));
    } catch (e) { if (!e.sessionExpired) body.replaceChildren(errorBox(e)); }
    body.style.opacity = "1"; scrollTo(0, y);
  };
  const strat = h("select", { "aria-label": "Ranking strategy", onchange: () => { state.strategy = strat.value; load(); } },
    [["hybrid", "Hybrid (all signals)"], ["skills", "Skills only"], ["content", "TF-IDF content only"], ["popularity", "Popularity (recency) only"]].map(([v, l]) => h("option", { value: v }, l)));
  const lim = h("select", { "aria-label": "Number of jobs", onchange: () => { state.limit = +lim.value; load(); } }, [10, 15, 25, 50].map((n) => h("option", { value: n, selected: n === 15 }, n + " jobs")));
  main.append(h("div", { class: "filters card" }, h("label", null, "Ranking strategy", strat), h("label", null, "Show", lim)), body);
  body.append(skeleton());
  await load();
}

// ---------------------------------------------------------------- pages: jobs
async function jobsPage(main) {
  document.title = "Jobs · JobIntel";
  main.append(h("h1", null, "Jobs"), h("p", { class: "sub" }, "Search and filter the stored postings."));
  const rep = await twsma();
  const sel = (label, opts, first) => { const s = h("select", { "aria-label": label }, h("option", { value: "" }, first), opts.map((o) => h("option", { value: o }, o))); return [h("label", null, label, s), s]; };
  const q = h("input", { type: "search", placeholder: "title, description or company", "aria-label": "Search" });
  const [lRole, role] = sel("Role", rep.role_distribution.items.map((i) => i.role_category), "All");
  const [lCity, city] = sel("City", rep.location_distribution.items.map((i) => i.city), "All");
  const [lSkill, skill] = sel("Skill", rep.top_skills.map((i) => i.skill), "Any");
  const [lSrc, src] = sel("Source", ["adzuna", "greenhouse", "lever"], "All");
  const sal = h("input", { type: "checkbox" });
  const list = h("div"); let page = 1, t;
  const load = async () => {
    list.style.opacity = ".5";
    try {
      const r = await api("jobs/", { params: { query: q.value.trim(), role_category: role.value, city: city.value, skill: skill.value, source: src.value, has_salary: sal.checked, page, page_size: 10 } });
      list.replaceChildren(h("p", { class: "muted" }, `${r.total.toLocaleString()} matching jobs`),
        r.items.length ? r.items.map((j) => jobCard(j)) : emptyState("No jobs match", "Try fewer filters or a different keyword."),
        r.total_pages > 1 && h("div", { class: "pager" },
          h("button", { class: "btn ghost sm", disabled: page <= 1, onclick: () => { page--; load(); scrollTo(0, 0); } }, "← Prev"), `Page ${page} of ${r.total_pages}`,
          h("button", { class: "btn ghost sm", disabled: page >= r.total_pages, onclick: () => { page++; load(); scrollTo(0, 0); } }, "Next →")));
    } catch (e) { list.replaceChildren(errorBox(e)); }
    list.style.opacity = "1";
  };
  const refilter = () => { page = 1; clearTimeout(t); t = setTimeout(load, 250); };
  [q, role, city, skill, src, sal].forEach((el) => el.addEventListener(el === q ? "input" : "change", refilter));
  main.append(h("div", { class: "card filters" }, h("label", { style: "flex:2" }, "Search", q), lRole, lCity, lSkill, lSrc, h("label", { class: "row" }, sal, "Salary disclosed")),
    !S.user && banner("info", link("#/login?next=/jobs", "Sign in"), " to save, apply to or skip jobs and get a personalised feed."), list);
  list.append(skeleton());
  await load();
}

// ---------------------------------------------------------------- pages: market
async function marketPage(main) {
  document.title = "Market analytics · JobIntel";
  main.append(h("h1", null, "Market analytics"));
  const dedupe = h("input", { type: "checkbox" });
  const holder = h("div");
  const draw = async () => {
    holder.replaceChildren(skeleton());
    const r = await cached("twsma-" + dedupe.checked, () => api("analytics/twsma", { params: { dedupe: dedupe.checked } }));
    holder.replaceChildren(); if (!r.total_jobs) return holder.append(banner("info", "No jobs stored yet."));
    const tabs = {
      "Top skills": () => [bars(r.top_skills, { label: (s) => title(s.skill), value: (s) => s.job_count, fmt: (s) => `${s.job_count} (${s.percentage}%)` })],
      "Skills by role": () => { const sel = h("select", { "aria-label": "Role category" }, Object.keys(r.skills_by_role).map((k) => h("option", null, k))); const out = h("div");
        const show = () => { const d = r.skills_by_role[sel.value]; out.replaceChildren(h("p", { class: "muted small" }, `${d.job_count} jobs, ${d.jobs_with_skills} with extracted skills. Percentages are of this category.`),
          d.top_skills.length ? bars(d.top_skills, { label: (s) => title(s.skill), value: (s) => s.job_count, fmt: (s) => `${s.job_count} (${s.percentage}%)` }) : banner("info", "No skills extracted for this category.")); };
        sel.onchange = show; show(); return [h("label", null, "Role category", sel), out]; },
      "Roles & locations": () => { const sel = h("select", { "aria-label": "City" }, Object.keys(r.skills_by_location).map((k) => h("option", null, k))); const out = h("div");
        const show = () => { const d = r.skills_by_location[sel.value]; out.replaceChildren(h("p", { class: "muted small" }, `${d.job_count} jobs · role mix: ` + (r.roles_by_location[sel.value] || []).map((i) => `${i.role_category} ${i.job_count}`).join(", ")),
          d.top_skills.length ? bars(d.top_skills, { label: (s) => title(s.skill), value: (s) => s.job_count, fmt: (s) => `${s.percentage}%` }) : null); };
        sel.onchange = show; show();
        return [h("div", { class: "grid g2" }, h("div", null, h("h3", null, "Role distribution"), bars(r.role_distribution.items, { label: (s) => s.role_category, value: (s) => s.job_count, fmt: (s) => s.percentage + "%" }),
          h("p", { class: "small muted" }, `Keyword-classified: ${r.role_distribution.classified_by_keyword}; default-category fallback: ${r.role_distribution.unmatched_fallback}.`)),
          h("div", null, h("h3", null, "Cities"), bars(r.location_distribution.items, { label: (s) => s.city, value: (s) => s.job_count }))), h("h3", { style: "margin-top:18px" }, "Top skills in a city"), h("label", null, "City", sel), out]; },
      "Companies": () => [h("p", { class: "muted small" }, `${r.company_distribution.distinct_companies} distinct disclosed companies; ${r.company_distribution.undisclosed_count} postings undisclosed.`),
        table(["Company", "Postings"], r.company_distribution.items.map((c) => [c.company, c.job_count]), [1])],
      "Skill co-occurrence": () => [h("p", { class: "muted small" }, "Pairs seen together in at least 2 jobs. Lift > 1 means they co-occur more than chance would suggest."),
        r.skill_cooccurrence.length ? table(["Pair", "Jobs", "% of jobs", "Lift"], r.skill_cooccurrence.slice(0, 40).map((p) => [`${title(p.skill_a)} + ${title(p.skill_b)}`, p.job_count, p.percentage + "%", p.lift]), [1, 2, 3]) : banner("info", "No skill pair appears in 2+ jobs.")],
      "Text statistics": () => { const t = r.text_analysis, d = t.description, e = t.experience; return [
        h("ul", null, h("li", null, `Descriptions: mean ${d.mean_length} chars (median ${d.median_length}, max ${d.max_length}); ${d.truncated_with_ellipsis}/${d.total_jobs} end in an ellipsis — Adzuna supplies short snippets.`),
          h("li", null, `Experience stated in text: ${e.jobs_with_stated_experience}/${e.total_jobs} jobs (${e.coverage_percentage}%), median minimum ${e.median_min_years} years. Inferred from text; sources supply no experience field.`),
          h("li", null, `Qualifications mentioned: ${t.qualifications.jobs_with_any_qualification}/${t.qualifications.total_jobs} jobs.`)),
        h("div", { class: "grid g2" }, h("div", null, h("h3", null, "Common terms"), table(["Term", "Jobs"], t.common_terms.unigrams.slice(0, 15).map((x) => [x.term, x.job_count]), [1])),
          h("div", null, h("h3", null, "Common bigrams"), table(["Bigram", "Jobs"], t.common_terms.bigrams.slice(0, 15).map((x) => [x.term, x.job_count]), [1])))]; },
      "Dates & trends": () => { const p = r.posting_dates; return [h("p", null, `Posting dates present for ${p.with_date}/${p.total_jobs} jobs, ${p.earliest} to ${p.latest}.`),
        p.freshness && table(["Age at latest posting", "Jobs"], Object.entries(p.freshness), [1]),
        p.trend_supported ? bars(p.monthly_counts, { label: (m) => m.month, value: (m) => m.job_count }) : banner("warn", h("b", null, "Trend analysis is not supported by this data. "), p.trend_reason || "", " ", p.caveat)]; },
    };
    const bar = h("div", { class: "tabs", role: "tablist" }), pane = h("div", { class: "card" });
    const show = (name) => { [...bar.children].forEach((b) => b.classList.toggle("on", b.textContent === name)); pane.replaceChildren(...[].concat(tabs[name]()).filter(Boolean)); };
    Object.keys(tabs).forEach((name) => bar.append(h("button", { role: "tab", onclick: () => show(name) }, name)));
    holder.append(banner("warn", `Analysing ${r.total_jobs.toLocaleString()} stored postings. ${r.scope_note}`),
      h("p", { class: "small muted" }, `Skill extraction coverage: ${r.skill_coverage.jobs_with_skills}/${r.total_jobs} jobs have at least one skill (mean ${r.skill_coverage.mean_skills_per_job}). "Data Science" is a field label, not a tool skill.`), bar, pane);
    show("Top skills");
  };
  dedupe.onchange = () => draw().catch((e) => holder.replaceChildren(errorBox(e)));
  main.append(h("label", { class: "row" }, dedupe, "Drop likely reposts (same title + company + city)"), holder);
  await draw();
}

// ---------------------------------------------------------------- pages: skill gap
async function gapPage(main) {
  document.title = "Skill gap · JobIntel";
  main.append(h("h1", null, "Skill gap"), h("p", { class: "sub" }, "Compare your skills with a role category or one specific job."));
  const mine = S.user.skills.map((s) => s.skill_display_name || s.skill_name);
  main.append(h("p", null, h("b", null, "Your skills: "), mine.join(", ") || "none listed"));
  if (!mine.length) main.append(banner("warn", "Your profile has no skills, so every required skill will show as missing. ", link("#/profile", "Add your skills"), "."));
  const rep = await twsma();
  const mode = h("select", { "aria-label": "Compare against" }, h("option", { value: "role" }, "A role category (aggregate of postings)"), h("option", { value: "job" }, "One specific job"));
  const out = h("div"), holder = h("div");
  const jobView = () => {
    const q = h("input", { type: "search", placeholder: "find a job by title / company / keyword" }); const pick = h("select", { "aria-label": "Job" }); let t;
    const run = async () => { if (!pick.value) return; out.replaceChildren(skeleton(1)); try {
      const g = await api(`skill-gap/job/${pick.value}`, { params: { user_id: S.user.id } });
      out.replaceChildren(g.note ? banner("info", g.note) : h("div", null, metric(`${g.matched_skills.length}/${g.job_skills_extracted}`, "skills of this posting you have"),
        h("div", { class: "grid g2" }, h("div", { class: "card" }, h("h3", null, "Matched"), chips(g.matched_skills, "good")), h("div", { class: "card" }, h("h3", null, "Missing"), chips(g.missing_skills, "bad")))));
    } catch (e) { if (!e.sessionExpired) out.replaceChildren(errorBox(e)); } };
    const search = async () => { const r = await api("jobs/", { params: { query: q.value.trim(), page_size: 25 } });
      pick.replaceChildren(...r.items.map((j) => h("option", { value: j.id }, `${j.title} — ${j.company_name} (${j.city || "n/a"})`))); run(); };
    q.oninput = () => { clearTimeout(t); t = setTimeout(search, 250); }; pick.onchange = run; search();
    return [h("label", null, "Find a job", q), h("label", null, "Job", pick)];
  };
  const switchMode = () => { holder.replaceChildren(); out.replaceChildren();
    if (mode.value === "role") { const role = h("select", { "aria-label": "Target role category" }, rep.role_distribution.items.map((i) => h("option", null, i.role_category)));
      const run = async () => { out.replaceChildren(skeleton(1)); try {
        const g = await api("skill-gap/analyze", { params: { user_id: S.user.id, target_role: role.value } });
        if (!g.skills.length) return out.replaceChildren(banner("info", g.recommendation_summary));
        out.replaceChildren(h("div", { class: "grid g4" }, metric(g.total_jobs_analyzed, "postings analysed"), metric(g.matching_skills_count, "top skills you have"), metric(g.missing_skills_count, "top skills you lack")),
          h("p", { class: "small muted" }, "Based on the most frequent extracted skills; descriptions are short snippets, so real requirement lists are longer."),
          h("div", { class: "card" }, bars(g.skills, { label: (s) => s.display_name + (s.user_has_skill ? "  ✓" : ""), value: (s) => s.frequency_in_target_role, fmt: (s) => s.frequency_in_target_role + "%", cls: (s) => (s.user_has_skill ? "good" : "bad") })),
          h("div", { class: "grid g2" }, h("div", { class: "card" }, h("h3", null, "Matched"), chips(g.skills.filter((s) => s.user_has_skill).map((s) => s.display_name), "good")),
            h("div", { class: "card" }, h("h3", null, "Missing (share of postings)"), chips(g.skills.filter((s) => !s.user_has_skill).map((s) => `${s.display_name} ${s.frequency_in_target_role}%`), "bad"))));
      } catch (e) { if (!e.sessionExpired) out.replaceChildren(errorBox(e)); } };
      role.onchange = run; holder.append(h("label", null, "Target role category", role)); run();
    } else holder.append(...jobView());
  };
  mode.onchange = switchMode;
  main.append(h("label", null, "Compare against", mode), holder, out);
  switchMode();
}

// ---------------------------------------------------------------- pages: profile
function completeness(u) {
  const parts = [["Add at least one skill", (u.skills || []).length > 0, 40], ["Choose preferred roles or a target role", (u.preferred_roles || []).length > 0 || !!u.target_role, 20],
    ["Choose preferred locations", (u.preferred_locations || []).length > 0, 20], ["Add a headline", !!u.headline, 10], ["Add your years of experience", u.experience_years > 0, 10]];
  return { score: parts.reduce((a, [, ok, w]) => a + (ok ? w : 0), 0), todo: parts.filter(([, ok]) => !ok).map(([t]) => t) };
}
function tagInput(initial, suggestions, placeholder) {
  const tags = [...initial], listId = "dl" + Math.random().toString(36).slice(2, 8);
  const input = h("input", { list: listId, placeholder, "aria-label": "Add a skill" });
  const box = h("div", { class: "tagbox", onclick: () => input.focus() });
  const draw = () => box.replaceChildren(tags.map((t, i) => h("span", { class: "chip role" }, t, h("button", { type: "button", "aria-label": "Remove " + t, onclick: (ev) => { ev.stopPropagation(); tags.splice(i, 1); draw(); } }, "×"))), input);
  const add = () => { const v = input.value.replace(/,$/, "").trim(); if (v && !tags.some((t) => t.toLowerCase() === v.toLowerCase())) tags.push(v); input.value = ""; draw(); input.focus(); };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } else if (e.key === "Backspace" && !input.value && tags.length) { tags.pop(); draw(); input.focus(); } });
  input.addEventListener("change", add); input.addEventListener("blur", () => { if (input.value.trim()) add(); });
  draw();
  return { el: h("div", null, box, h("datalist", { id: listId }, suggestions.map((s) => h("option", { value: s })))), get: () => [...tags] };
}

async function profilePage(main, q) {
  document.title = "Profile · JobIntel";
  const me = S.user;
  const [rep, skillList] = await Promise.all([twsma(), cached("skills100", () => api("analytics/skills/top", { params: { limit: 100 } }))]);
  const c = completeness(me);
  main.append(q.welcome ? banner("good", h("b", null, `Welcome to JobIntel, ${firstName(me.full_name)}! `), "Tell us about your skills and preferences to get a personalised feed. You can change all of this later.") : null,
    h("h1", null, "Your profile"), h("p", { class: "sub" }, "Only what you enter here is used to personalise recommendations."),
    h("div", { class: "card" }, h("div", { class: "section-h" }, h("b", null, `Profile ${c.score}% complete`), h("span", { class: "muted small" }, c.todo.length ? "Next: " + c.todo[0] : "All set — nice work.")),
      h("div", { class: "meter" }, h("i", { style: `width:${c.score}%` }))));
  const name = h("input", { value: me.full_name, required: true });
  const headline = h("input", { value: me.headline || "", placeholder: "e.g. Final-year student, data enthusiast" });
  const exp = h("input", { type: "number", min: 0, max: 50, step: 0.5, value: me.experience_years || 0 });
  const skillsIn = tagInput(me.skills.map((s) => s.skill_display_name || s.skill_name), skillList.map((s) => s.display_name), "Type a skill and press Enter (e.g. SQL, Python)");
  const target = h("input", { value: me.target_role || "", placeholder: "e.g. Data Analyst" });
  const checks = (opts, current) => { const set = new Set(current || []); const boxes = opts.map((o) => { const c2 = h("input", { type: "checkbox", value: o }); c2.checked = set.has(o); return c2; });
    return [h("div", { class: "checks" }, opts.map((o, i) => h("label", null, boxes[i], o))), () => boxes.filter((b) => b.checked).map((b) => b.value)]; };
  const roleOpts = [...new Set([...rep.role_distribution.items.map((i) => i.role_category), ...me.preferred_roles])];
  const cityOpts = [...new Set([...rep.location_distribution.items.map((i) => i.city), "Remote", ...me.preferred_locations])];
  const [rolesBox, getRoles] = checks(roleOpts, me.preferred_roles), [citiesBox, getCities] = checks(cityOpts, me.preferred_locations);
  const msg = h("p", { class: "err", role: "alert" }), save = h("button", { class: "btn", type: "submit" }, q.welcome ? "Save and see my feed" : "Save profile");
  main.append(h("form", { onsubmit: async (ev) => {
    ev.preventDefault(); msg.textContent = ""; save.disabled = true;
    try { await api(`users/${me.id}`, { method: "PUT", body: { full_name: name.value.trim(), headline: headline.value.trim() || null, experience_years: +exp.value || 0, target_role: target.value.trim() || null,
            preferred_roles: getRoles(), preferred_locations: getCities(), skills: skillsIn.get().map((s) => ({ skill_name: s })) } });
          S.user = await api("auth/me"); renderChrome(); toast("Profile saved"); if (q.welcome) location.hash = "#/feed"; else route(); }
    catch (e) { if (!e.sessionExpired) msg.textContent = e.message; save.disabled = false; } } },
    h("div", { class: "card" }, h("h3", null, "About you"), h("div", { class: "grid g2" }, h("label", null, "Full name", name), h("label", null, "Years of experience", exp)), h("label", null, "Headline (optional)", headline)),
    h("div", { class: "card" }, h("h3", null, "Skills"), h("p", { class: "hint" }, "Aliases are understood (e.g. “ml” = Machine Learning). Suggestions come from skills found in the stored postings."), skillsIn.el),
    h("div", { class: "card" }, h("h3", null, "What are you looking for?"), h("label", null, "Target role (free text)", target),
      h("label", null, "Preferred role categories"), rolesBox, h("label", null, "Preferred locations"), citiesBox),
    msg, save));
  // what the system has learned from real activity
  main.append(h("h2", null, "Learned from your activity"));
  try {
    const info = await api(`users/${me.id}/personalization`), L = info.learned_from_interactions;
    main.append(h("p", null, "Personalization mode: ", h("b", null, info.personalization_mode.replace("_", " "))));
    if (!L.interactions_used) main.append(banner("info", "No activity yet. Save, apply to, view or skip jobs and your feed will start to learn — nothing is assumed in advance."));
    else {
      main.append(h("p", { class: "small muted" }, `${L.interactions_used} interactions ${JSON.stringify(L.counts_by_type)}. Positive evidence ${L.positive_evidence} (needs ${L.evidence_needed}: ${L.active ? "active" : "not yet active"}); ${L.skipped_jobs} job(s) skipped.`),
        h("div", { class: "grid g2" }, h("div", { class: "card" }, h("h3", null, "Skills you engage with"), L.skills.length ? bars(L.skills, { label: (s) => s.name, value: (s) => s.preference, fmt: (s) => s.preference }) : "none yet"),
          h("div", { class: "card" }, h("h3", null, "Role categories & cities"), L.role_categories.length ? bars(L.role_categories, { label: (s) => s.name, value: (s) => s.preference, fmt: (s) => s.preference }) : "none yet",
            L.cities.length ? bars(L.cities, { label: (s) => s.name, value: (s) => s.preference, fmt: (s) => s.preference }) : null)));
      const hist = await api(`users/${me.id}/interactions`, { params: { limit: 20 } });
      main.append(h("div", { class: "card" }, h("h3", null, "Recent activity"), table(["When", "Job", "Action"], hist.map((x) => [String(x.created_at).slice(0, 16).replace("T", " "), x.job_id, x.interaction_type]))));
    }
  } catch (e) { if (!e.sessionExpired) main.append(errorBox(e)); }
}

// ---------------------------------------------------------------- pages: account
async function accountPage(main) {
  document.title = "Account · JobIntel";
  const me = S.user, exp = sessionExpiry();
  main.append(h("h1", null, "Account"), h("p", { class: "sub" }, "Sign-in details and data controls."),
    h("div", { class: "card" }, h("dl", { class: "kv" }, h("dt", null, "Name"), h("dd", null, me.full_name), h("dt", null, "Email"), h("dd", null, me.email),
      h("dt", null, "Member since"), h("dd", null, String(me.created_at).slice(0, 10)), h("dt", null, "Session"), h("dd", null, exp ? `signed in on this browser until ${exp.toLocaleString()}` : "signed in"))));
  const cur = passwordField("Current password", { autocomplete: "current-password" }), nw = passwordField("New password (min 8 characters)", { autocomplete: "new-password" });
  const pmsg = h("p", { class: "err", role: "alert" });
  main.append(h("form", { class: "card", onsubmit: async (ev) => { ev.preventDefault(); pmsg.textContent = "";
    try { await api("auth/password", { method: "PUT", body: { current_password: cur.input.value, new_password: nw.input.value } }); cur.input.value = nw.input.value = ""; toast("Password changed"); }
    catch (e) { if (!e.sessionExpired) pmsg.textContent = e.message; } } }, h("h3", null, "Change password"), cur.el, nw.el, pmsg, h("button", { class: "btn", type: "submit" }, "Change password")));
  const dpw = passwordField("Your password", { autocomplete: "current-password" }), confirm = h("input", { placeholder: "type DELETE to confirm" }), dmsg = h("p", { class: "err", role: "alert" });
  main.append(h("form", { class: "card danger-zone", onsubmit: async (ev) => { ev.preventDefault(); dmsg.textContent = "";
    if (confirm.value.trim() !== "DELETE") return (dmsg.textContent = "Type DELETE to confirm.");
    try { await api("auth/me", { method: "DELETE", body: { password: dpw.input.value } }); setSession(null); toast("Your account and data were deleted."); location.hash = "#/"; }
    catch (e) { if (!e.sessionExpired) dmsg.textContent = e.message; } } },
    h("h3", null, "Delete account"), h("p", { class: "muted" }, "Permanently deletes your profile, skills and activity history. This cannot be undone."),
    dpw.el, h("label", null, "Confirmation", confirm), dmsg, h("button", { class: "btn danger", type: "submit" }, "Delete my account")));
}

// ---------------------------------------------------------------- pages: about
async function aboutPage(main) {
  document.title = "How it works · JobIntel";
  const [rep, ...src] = await Promise.all([twsma(), ...["adzuna", "greenhouse", "lever"].map((s) => api("jobs/", { params: { source: s, page_size: 1 } }))]);
  const [az, gh, lv] = src.map((r) => r.total.toLocaleString());
  main.append(h("h1", null, "How JobIntel works"), h("p", { class: "sub" }, "Job-market analytics (text analytics over real postings) and explainable recommendations, with an honest account of what the data can and cannot show."),
    h("div", { class: "card" }, h("h3", null, "Pipeline"), h("ol", { class: "steps" },
      h("li", null, h("b", null, "Collect. "), "Scheduled, budgeted calls to the Adzuna API plus public Greenhouse and Lever company boards; every run is audited and raw responses are saved."),
      h("li", null, h("b", null, "Clean and de-duplicate. "), "HTML stripped, locations normalised, missing salary/experience kept as missing, reposts detected."),
      h("li", null, h("b", null, "Extract. "), "Dictionary-based skill extraction (108 skills), degree and experience patterns, a single keyword role classifier."),
      h("li", null, h("b", null, "Analyse (TWSMA). "), "Top skills, skills by role/city, role and company distributions, skill co-occurrence, text statistics."),
      h("li", null, h("b", null, "Recommend. "), "Four strategies (popularity, skills, TF-IDF content, hybrid) with configurable weights and a plain-language explanation for every result."),
      h("li", null, h("b", null, "Learn from you. "), "Saves, applies, views and skips you make adjust the hybrid ranking. Nothing is simulated."))),
    h("div", { class: "grid g2" },
      h("div", { class: "card" }, h("h3", null, "Data in this system"), h("dl", { class: "kv" }, h("dt", null, "Jobs stored"), h("dd", null, rep.total_jobs.toLocaleString()),
        h("dt", null, "Adzuna"), h("dd", null, `${az} (short snippets)`), h("dt", null, "Greenhouse"), h("dd", null, `${gh} (full descriptions)`), h("dt", null, "Lever"), h("dd", null, `${lv} (full descriptions)`),
        h("dt", null, "With extracted skills"), h("dd", null, `${rep.skill_coverage.coverage_percentage}%`), h("dt", null, "Companies"), h("dd", null, rep.company_distribution.distinct_companies.toLocaleString()))),
      h("div", { class: "card" }, h("h3", null, "Hybrid ranking signals"), h("p", { class: "small muted" }, "Default raw weights, renormalised over the signals available for each user:"),
        bars([["skill match", 0.35], ["text similarity (TF-IDF)", 0.30], ["role match", 0.10], ["your activity", 0.10], ["location match", 0.06], ["recency", 0.05]], { label: (x) => x[0], value: (x) => x[1], fmt: (x) => x[1].toFixed(2) }),
        h("p", { class: "small muted" }, "Missing data is never rewarded. Weights are starting values, not tuned."))),
    h("div", { class: "card" }, h("h3", null, "Evaluation (offline proxy — not user feedback)"),
      h("p", null, "With no real users yet there is no ground truth, so the recommenders were compared on a held-out proxy: which Adzuna search returned each job. Results (mean NDCG@10):"),
      table(["Run", "Hybrid", "Skills", "Content", "Popularity", "Random"], [["Original (75 jobs, role-only scenario)", "0.831", "0.652", "0.700", "0.350", "0.310"], ["Live (2,118 jobs, 48 role+city personas)", "0.483", "0.064", "0.142", "0.010", "0.012"]], [1, 2, 3, 4, 5]),
      h("p", { class: "small muted", style: "margin-top:8px" }, "Under the winner rule fixed in advance (best mean, ahead in every persona, confidence interval above zero) Hybrid is a clear winner only in the original role-only scenario; no overall winner is claimed. Hybrid, Content and Skills beat random; Popularity does not. Full tables: docs/evaluation_report*.md.")),
    h("div", { class: "card" }, h("h3", null, "Limitations"), h("ul", null,
      h("li", null, "Two collection snapshots; sources are Adzuna (snippets) and 14 company boards; not a market census."),
      h("li", null, "Salary, experience level and work model are mostly unavailable and shown as missing."),
      h("li", null, "“Data Science” is a field, not a tool skill; company boilerplate is only partly filtered."),
      h("li", null, "Trends are not claimed: repeated daily collection is needed first."),
      h("li", null, "The behavioural layer has not yet been evaluated on real users."))));
}

// ---------------------------------------------------------------- chrome (nav + account menu), router, boot
function renderChrome() {
  const links = [["/", "Dashboard"], ["/feed", "My feed", true], ["/jobs", "Jobs"], ["/market", "Market"], ["/gap", "Skill gap", true], ["/about", "How it works"]].filter(([, , auth]) => !auth || S.user);
  $("#nav").replaceChildren(links.map(([p, l]) => h("a", { href: "#" + p, "data-r": p }, l)));
  markActive();
  const box = $("#auth");
  if (!S.user) return box.replaceChildren(h("div", { class: "row" }, link("#/login", "Sign in", "btn ghost sm"), link("#/register", "Create account", "btn sm")));
  const pop = h("div", { class: "pop", hidden: true },
    h("div", { class: "who" }, h("div", null, h("b", null, S.user.full_name)), h("div", null, S.user.email)),
    link("#/profile", "Profile"), link("#/account", "Account settings"),
    h("button", { type: "button", onclick: () => { setSession(null); toast("Signed out"); location.hash = "#/"; } }, "Sign out"));
  const btn = h("button", { type: "button", "aria-haspopup": "menu", "aria-label": "Account menu", onclick: (e) => { e.stopPropagation(); pop.hidden = !pop.hidden; } },
    h("span", { class: "avatar" }, initials(S.user.full_name)), h("span", { class: "small" }, firstName(S.user.full_name)));
  pop.addEventListener("click", () => (pop.hidden = true));
  box.replaceChildren(h("div", { class: "menu" }, btn, pop));
}
addEventListener("click", () => { const p = $("#auth .pop"); if (p) p.hidden = true; });
function markActive() { const path = currentRoute().path; document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.r === path)); }

function currentRoute() {
  const [path, qs] = (location.hash.replace(/^#/, "") || "/").split("?");
  return { path: path || "/", query: Object.fromEntries(new URLSearchParams(qs || "")) };
}
const ROUTES = { "/": dashboardPage, "/feed": feedPage, "/jobs": jobsPage, "/market": marketPage, "/gap": gapPage, "/profile": profilePage, "/account": accountPage,
  "/about": aboutPage, "/login": loginPage, "/register": registerPage };
const PRIVATE = new Set(["/feed", "/gap", "/profile", "/account"]), GUEST_ONLY = new Set(["/login", "/register"]);
let routeSeq = 0;
async function route() {
  const { path, query } = currentRoute(), seq = ++routeSeq;
  if (PRIVATE.has(path) && !S.user) { location.hash = "#/login?next=" + encodeURIComponent(path); return; }
  if (GUEST_ONLY.has(path) && S.user) { location.hash = "#/feed"; return; }
  const page = ROUTES[path] || dashboardPage;
  markActive();
  const main = $("#main"); main.replaceChildren(skeleton());
  const stage = h("div");
  try { await page(stage, query); } catch (e) { if (!e.sessionExpired) stage.replaceChildren(errorBox(e)); }
  if (seq === routeSeq && !(PRIVATE.has(path) && !S.user)) { main.replaceChildren(...stage.childNodes); scrollTo(0, 0); main.focus({ preventScroll: true }); }
}
async function boot() {
  if (S.token) { try { S.user = await api("auth/me"); } catch (e) { setSession(null); } }   // validate a stored session
  renderChrome();
  api("health").then((r) => { const d = $("#status"); d.className = "dot " + (r.database === "healthy" ? "ok" : "bad"); d.title = r.database === "healthy" ? "Backend and database online" : "Database problem: " + r.database; })
    .catch(() => { $("#status").className = "dot bad"; $("#status").title = "Backend offline"; });
  addEventListener("hashchange", route); route();
}
boot();
