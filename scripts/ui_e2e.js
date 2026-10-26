/* Real-browser end-to-end check of the web UI (needs Node 22+, Google Chrome/Edge, and the stack running).
     node scripts/ui_e2e.js [baseUrl] [outDir]
   Drives headless Chrome through the DevTools protocol like a user would: registers an account through the real
   form, completes the profile (tag input), uses the feed, signs out and in, changes the password and finally DELETES
   the account again, so it leaves no data behind. Screenshots go to outDir. */
const { spawn } = require("child_process");
const fs = require("fs"), os = require("os"), path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:8000/ui/";
const OUT = process.argv[3] || path.join(os.tmpdir(), "jobintel_ui");
const CHROME = [process.env.CHROME, "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"].find((p) => p && fs.existsSync(p));
if (!CHROME) { console.error("No Chrome/Edge found (set CHROME=path)"); process.exit(2); }
fs.mkdirSync(OUT, { recursive: true });
const results = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log(`[${ok ? "PASS" : "FAIL"}] ${name}${detail ? " - " + detail : ""}`); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PASSWORD = "viva-demo-passphrase", NEW_PASSWORD = "an even better passphrase";

(async () => {
  const port = 9300 + Math.floor(Math.random() * 500);
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "ji-chrome-"));
  const chrome = spawn(CHROME, [`--remote-debugging-port=${port}`, "--headless=new", "--disable-gpu", "--hide-scrollbars",
    `--user-data-dir=${profile}`, "--window-size=1280,1400", "about:blank"], { stdio: "ignore" });
  let target;
  for (let i = 0; i < 50 && !target; i++) { await sleep(200); try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page"); } catch (e) { /* starting */ } }
  const ws = new WebSocket(target.webSocketDebuggerUrl); await new Promise((r) => (ws.onopen = r));
  let id = 0; const pending = new Map(); const errors = [];
  ws.onmessage = (m) => { const d = JSON.parse(m.data);
    if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); }
    if (d.method === "Runtime.exceptionThrown") errors.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
    if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error") errors.push(d.params.args.map((a) => a.value || a.description).join(" ")); };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const js = async (expr) => { const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true }); if (r.result.exceptionDetails) throw new Error(r.result.exceptionDetails.exception.description); return r.result.result.value; };
  const shot = async (name) => { const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true }); fs.writeFileSync(path.join(OUT, name + ".png"), Buffer.from(r.result.data, "base64")); };
  const go = async (hash) => { await js(`location.hash = ${JSON.stringify(hash)}`); await sleep(120); };
  const until = async (cond, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await js(cond)) return true; } catch (e) { /* navigating */ } await sleep(150); } return false; };
  const text = () => js("document.getElementById('main').innerText");
  const has = (needle) => `document.getElementById('main').innerText.includes(${JSON.stringify(needle)})`;
  // fill a field located by its label text inside the main area
  const fill = (label, value) => js(`(()=>{const l=[...document.querySelectorAll('#main label')].find(x=>x.firstChild&&x.firstChild.textContent.trim()===${JSON.stringify(label)}); const el=l.querySelector('input,textarea'); el.value=${JSON.stringify(value)}; el.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  const click = (btnText) => js(`[...document.querySelectorAll('#main button, #main a.btn')].find(b=>b.innerText.trim()===${JSON.stringify(btnText)}).click()`);
  await send("Page.enable"); await send("Runtime.enable"); await send("Page.navigate", { url: BASE }); await until("document.readyState==='complete'");
  const email = `viva-${Date.now()}@example.com`;

  // ---- signed out
  check("landing page: hero + live metrics", await until("document.querySelector('.hero') && document.querySelectorAll('.metric').length>=4")); await shot("1_landing");
  check("nav hides private pages when signed out", (await js("[...document.querySelectorAll('#nav a')].map(a=>a.innerText).join('|')")) === "Dashboard|Jobs|Market|How it works");
  await go("#/feed"); check("private page redirects to sign-in", await until(`location.hash.startsWith('#/login') && ${has("Welcome back")}`));
  await go("#/about"); check("about page renders live counts", await until(`${has("How JobIntel works")} && ${has("Greenhouse")} && ${has("Hybrid ranking signals")}`)); await shot("2_about");
  await go("#/jobs"); await until("document.querySelectorAll('article.job').length>0");
  await js("(()=>{const q=document.querySelector('input[type=search]'); q.value='data engineer'; q.dispatchEvent(new Event('input'));})()");
  check("jobs search works signed out", await until("document.querySelector('article.job h3') && document.querySelector('article.job h3').innerText.toLowerCase().includes('data')"));
  check("market page renders", (await go("#/market"), await until(has("Analysing")))); await shot("3_market");

  // ---- register through the real form
  await go("#/register"); await until("document.querySelector('form')");
  await fill("Full name", "Priya Sharma"); await fill("Email", email); await fill("Password", "short"); await fill("Confirm password", "short"); await click("Create account");
  check("weak password is rejected with a clear message", await until(has("at least 8 characters")));
  await fill("Password", PASSWORD); await fill("Confirm password", "something different"); await click("Create account");
  check("mismatched confirmation is rejected", await until(has("do not match")));
  await fill("Confirm password", PASSWORD); await shot("4_register"); await click("Create account");
  check("account created, lands on the welcome profile", await until(`location.hash.includes('/profile') && ${has("Welcome to JobIntel, Priya")}`)); await shot("5_onboarding");
  check("signed-in chrome: avatar + account menu, no ids or tokens shown", (await js("document.querySelector('#auth .avatar').innerText")) === "PS" && !/token|user id/i.test(await js("document.body.innerText")));
  check("session kept in the browser", (await js("(localStorage.getItem('ji_token')||'').length")) > 40);

  // ---- complete the profile with the tag input
  for (const s of ["SQL", "Python", "ml"]) await js(`(()=>{const i=document.querySelector('.tagbox input'); i.value=${JSON.stringify(s)}; i.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));})()`);
  check("tag input adds skill chips", (await js("document.querySelectorAll('.tagbox .chip').length")) === 3);
  await js(`[...document.querySelectorAll('.checks input')].filter(c=>['Data & Analytics','Bengaluru'].includes(c.value)).forEach(c=>c.checked=true)`);
  await fill("Target role (free text)", "Data Analyst"); await click("Save and see my feed");
  check("profile saved -> personalised feed (profile-based)", await until(`location.hash==='#/feed' && document.querySelectorAll('article.job').length>=5 && ${has("Profile-based")}`)); await shot("6_feed");
  check("cards: rank, score, collapsible explanation", /^#1 /.test(await js("document.querySelector('article.job h3').innerText")) && (await js("document.querySelectorAll('article.job details.why').length")) >= 5);
  await js("document.querySelector('article.job details.why summary').click()");
  check("explanation lists real reasons", await until("document.querySelector('details.why[open] li')"));

  // ---- interact
  await js("[...document.querySelectorAll('article.job')][0].querySelector('.actions button:nth-child(2)').click()");
  check("Save -> feed becomes interaction-informed and shows the saved state", await until(`${has("Interaction-informed")} && ${has("✓ Saved")}`)); await shot("7_after_save");
  await js("[...document.querySelectorAll('article.job')][1].querySelector('.actions button').click()");
  check("details panel: description + skill comparison", await until(`document.querySelector('.desc') && ${has("Your skills vs this posting")}`));
  await go("#/gap"); check("skill gap by role", await until(`${has("Your skills:")} && ${has("Matched")} && document.querySelector('.bars')`)); await shot("8_gap");
  await go("#/profile"); check("profile shows what was learned", await until(`${has("Learned from your activity")} && ${has("Recent activity")}`));

  // ---- account: change password, sign out / in
  await js("document.querySelector('#auth .menu > button').click()"); check("account menu opens with name, email, sign out", await until(`document.querySelector('#auth .pop:not([hidden])') && document.querySelector('#auth .pop').innerText.includes('${email}')`)); await shot("9_menu");
  await go("#/account"); await until(has("Change password"));
  await fill("Current password", PASSWORD); await fill("New password (min 8 characters)", NEW_PASSWORD); await click("Change password");
  check("password changed", await until(`document.getElementById('toast').innerText.includes('Password changed')`));
  await js("document.querySelector('#auth .menu > button').click()"); await js("[...document.querySelectorAll('#auth .pop button')].find(b=>b.innerText==='Sign out').click()");
  check("sign out returns to the public site", await until("!localStorage.getItem('ji_token') && document.querySelector('#auth a.btn')"));
  await go("#/login"); await until("document.querySelector('form')");
  await fill("Email", email); await fill("Password", PASSWORD); await click("Sign in");
  check("old password no longer works (generic error)", await until(has("Incorrect email or password")));
  await fill("Password", NEW_PASSWORD); await click("Sign in");
  check("sign in with the new password -> feed", await until(`location.hash==='#/feed' && document.querySelectorAll('article.job').length>=5`));
  check("recommendations remember earlier activity", await until(has("Interaction-informed")));

  // ---- expired / invalid session
  await js("localStorage.setItem('ji_token','bogus.token')"); await js("location.reload()"); await until("document.readyState==='complete'");
  check("invalid session is dropped, public pages still work", await until("document.querySelector('#auth a.btn') && !localStorage.getItem('ji_token')"));
  await go("#/feed"); check("expired session asks to sign in again", await until(`location.hash.startsWith('#/login')`));
  await fill("Email", email); await fill("Password", NEW_PASSWORD); await click("Sign in"); await until("location.hash==='#/feed'");

  // ---- delete the account (leaves no data behind)
  await go("#/account"); await until(has("Delete account"));
  await js(`(()=>{const f=document.querySelector('form.danger-zone'); const set=(sel,v)=>{const e=f.querySelector(sel); e.value=v; e.dispatchEvent(new Event('input',{bubbles:true}));}; set('input[type=password],input[autocomplete=current-password]', ${JSON.stringify(NEW_PASSWORD)}); set('input[placeholder^="type DELETE"]','DELETE'); f.requestSubmit();})()`);
  check("account deletion works and signs out", await until("!localStorage.getItem('ji_token') && location.hash==='#/'"));
  const gone = await fetch(BASE.replace(/ui\/?$/, "") + "api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password: NEW_PASSWORD }) });
  check("deleted account can no longer sign in", gone.status === 401);
  check("no JavaScript errors in the console", errors.length === 0, errors.slice(0, 2).join(" | ").slice(0, 200));

  ws.close(); chrome.kill();
  const failed = results.filter((x) => !x).length;
  console.log(`\n${results.length - failed}/${results.length} checks passed; screenshots in ${OUT}`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
