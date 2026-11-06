import { $, $$, api, html, mount, icon, toast, busy, initials, clearCharts, ApiError } from "./core.js";
import { S, loadLatest } from "./state.js";
import { dashboard } from "./dashboard.js";
import { resumeView } from "./resume.js";
import { opportunities } from "./opportunities.js";
import { tracker } from "./tracker.js";
import { skills } from "./skills.js";
import { tools } from "./tools.js";
import { profile } from "./profile.js";

const ROUTES = {
  dashboard: ["Dashboard", "home", dashboard], resume: ["Resume & ATS", "file", resumeView], opportunities: ["Opportunities", "brief", opportunities],
  tracker: ["Tracker", "board", tracker], skills: ["Skill gap", "target", skills], tools: ["AI tools", "spark", tools], profile: ["Profile", "user", profile],
};
const root = $("#app");

function theme(t) { document.documentElement.dataset.theme = t; try { localStorage.setItem("rc-theme", t); } catch {} }
try { theme(localStorage.getItem("rc-theme") || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")); } catch {}


function authScreen(mode = "login") {
  clearCharts();
  mount(root, html`<div class="auth"><section class="pane-l">
    <div class="brand"><b>R</b> Resume Copilot</div>
    <h1>Know exactly why your resume <em>passes</em> or <em>fails</em>.</h1>
    <p class="muted" style="max-width:46ch">Evidence-based ATS analysis for internships, open source, certifications and projects, plus live jobs, internships, freelance gigs and research papers matched to you.</p>
    <div class="mini"><div class="tile"><div class="eyebrow">ATS</div><div class="big" style="font-size:30px">12</div><div class="xs muted">scored dimensions</div></div>
      <div class="tile"><div class="eyebrow">Sources</div><div class="big" style="font-size:30px">7+</div><div class="xs muted">live job &amp; paper feeds</div></div>
      <div class="tile"><div class="eyebrow">Tracker</div><div class="big" style="font-size:30px">6</div><div class="xs muted">pipeline stages</div></div></div></section>
    <section class="pane-r"><form class="authcard tile" id="af" novalidate>
      <div class="seg" style="margin-bottom:16px"><button type="button" data-m="login" class="${mode === "login" ? "on" : ""}">Sign in</button><button type="button" data-m="register" class="${mode === "register" ? "on" : ""}">Create account</button></div>
      <div class="stack">
        ${mode === "register" ? html`<label class="f">Full name<input class="input" name="name" autocomplete="name" required></label>` : ""}
        <label class="f">Email<input class="input" type="email" name="email" autocomplete="email" required></label>
        <label class="f">Password<input class="input" type="password" name="password" autocomplete="${mode === "login" ? "current-password" : "new-password"}" required>
          ${mode === "register" ? html`<span class="xs faint">8+ characters with letters and numbers</span>` : ""}</label>
        <div class="sm" id="aerr" style="color:var(--coral);min-height:20px" role="alert"></div>
        <button class="btn pri" style="justify-content:center">${mode === "login" ? "Sign in" : "Create account"}</button></div></form></section></div>`);
  $$("[data-m]").forEach((b) => b.onclick = () => authScreen(b.dataset.m));
  $("#af").onsubmit = async (e) => {
    e.preventDefault(); const f = Object.fromEntries(new FormData(e.target));
    try { await busy($("#af .pri"), async () => { const d = await api(`/auth/${mode}`, { method: "POST", json: f }); S.user = d.user; }); start(); }
    catch (er) { $("#aerr").textContent = er.message; }
  };
}

function shell() {
  mount(root, html`<div id="shell"><aside class="side"><div class="brand"><b>R</b> Resume Copilot</div>
    <nav class="nav">${Object.entries(ROUTES).map(([k, [l, i]]) => html`<a href="#/${k}" data-r="${k}" title="${l}">${icon(i)}<span>${l}</span></a>`)}</nav>
    <div class="foot"><button class="btn ghost sm" id="th">${icon("sun")}<span>Theme</span></button>
      <div class="userbox"><div class="avatar">${initials(S.user.name)}</div><div class="grow" style="min-width:0"><div class="sm" style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${S.user.name}</div>
      <button class="btn ghost sm" id="lo" style="padding:0;border:0;color:var(--muted)">Sign out</button></div></div></div></aside><main id="view"></main></div>`);
  $("#th").onclick = () => theme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  $("#lo").onclick = async () => { await api("/auth/logout", { method: "POST" }).catch(() => {}); S.user = null; S.latest = null; authScreen(); };
}

async function route() {
  if (!S.user) return;
  const key = (location.hash.match(/^#\/(\w+)/) || [])[1]; const r = ROUTES[key] || ROUTES.dashboard;
  const k = ROUTES[key] ? key : "dashboard";
  $$(".nav a").forEach((a) => a.classList.toggle("on", a.dataset.r === k));
  clearCharts(); const v = $("#view"); window.scrollTo(0, 0);
  try { await r[2](v); } catch (e) { if (e.status !== 401) mount(v, html`<div class="tile empty"><b>Something went wrong</b>${e.message}</div>`); }
}

async function start() {
  shell(); if (!location.hash) location.hash = "#/dashboard";
  try { await loadLatest(); } catch {}
  route();
}
window.addEventListener("hashchange", route);
window.addEventListener("rc:logout", () => { if (S.user) { S.user = null; authScreen(); toast("Session ended. Please sign in again.", "err"); } });

(async () => {
  try { S.meta = await api("/meta"); } catch {}
  try { S.user = (await api("/auth/me")).user; start(); } catch { authScreen(); }
})();
