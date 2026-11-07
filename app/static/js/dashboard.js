import { $, $$, api, html, mount, icon, ring, chart, cssv, cap, scoreColor, esc, ago, safeUrl, miniRing } from "./core.js";
import { S } from "./state.js";

const LBL = { saved: "Saved", applied: "Applied", oa: "Online test", interview: "Interview", offer: "Offer", rejected: "Rejected" };
const tint = (s) => (s >= 75 ? "tint-mint" : s >= 55 ? "tint-amber" : "");

export async function dashboard(v) {
  mount(v, html`<div class="pagehead"><div><h1>Dashboard</h1></div></div><div class="bento"><div class="tile c12 skel"></div></div>`);
  const o = await api("/analytics/overview");
  const a = o.ats, p = o.pipeline, has = a.score != null;
  const hr = new Date().getHours(), greet = hr < 12 ? "Good morning" : hr < 18 ? "Good afternoon" : "Good evening";
  const maxHeat = Math.max(1, ...p.heatmap.map((h) => h.count));
  mount(v, html`
  <div class="pagehead"><div><h1>${greet}, ${S.user.name.split(" ")[0]}</h1><p>${has ? html`Scoring as <b>${a.stage}</b> for <b>${a.role}</b>.` : "Upload your resume to unlock your analytics."}</p></div>
    <a class="btn pri" href="#/resume">${icon("upload")} ${has ? "Re-analyse resume" : "Upload resume"}</a></div>
  <div class="bento">
    <section class="tile glow c5 r2"><div class="eyebrow"><span class="dot"></span>Quick wins</div>
      ${has && a.quick_wins.length ? html`<div>${a.quick_wins.slice(0, 4).map((q, i) => html`<div class="step"><div class="n">${i + 1}</div><div><div style="font-weight:600">${q.title}</div><div class="sm muted">${q.fix}</div></div>${q.points ? html`<span class="chip mint">+${q.points}</span>` : ""}</div>`)}</div>
        <a class="btn sm mt" href="#/resume">See all findings</a>`
      : has ? html`<div class="empty"><b>No blocking issues</b>Your resume has no high-impact fixes pending.</div>` : html`<div class="empty"><b>Start with your resume</b>We extract internships, open source, certifications and score 12 dimensions.<div class="mt"><a class="btn pri" href="#/resume">Upload now</a></div></div>`}
    </section>
    <section class="tile c3 r2 ${tint(a.score || 0)}"><div class="eyebrow">ATS score</div>
      <div style="display:grid;place-items:center;gap:6px">${has ? ring(a.score, 150) : html`<div class="big faint">--</div>`}
      <div style="font-weight:600">${a.grade || "No resume yet"}</div>
      ${a.delta != null ? html`<span class="delta ${a.delta >= 0 ? "up" : "down"}">${a.delta >= 0 ? "▲" : "▼"} ${Math.abs(a.delta)} vs previous</span>` : ""}</div></section>
    <section class="tile c2 kpi"><div class="eyebrow">Applications</div><div class="big">${p.total}</div><div class="xs muted">${p.kinds.internship || 0} internships</div></section>
    <section class="tile c2 kpi"><div class="eyebrow">Response rate</div><div class="big">${p.response_rate == null ? "--" : p.response_rate + "%"}</div><div class="xs muted">${p.avg_days_to_response ? "avg " + p.avg_days_to_response + "d to reply" : "reached test/interview"}</div></section>
    <section class="tile c2 kpi"><div class="eyebrow">Saved jobs</div><div class="big">${p.saved_jobs}</div><a class="xs" href="#/opportunities">Browse more</a></section>
    <section class="tile c2 kpi"><div class="eyebrow">Day streak</div><div class="big">${p.streak}</div><div class="xs muted">days with activity</div></section>

    <section class="tile c4"><div class="eyebrow">Score trend</div><div class="canvas-box sm">${a.trend.length > 1 ? html`<canvas id="ch-trend"></canvas>` : html`<div class="empty">Upload two versions to see progress.</div>`}</div></section>
    <section class="tile c4"><div class="eyebrow">Score breakdown</div>${has ? a.components.slice().sort((x, y) => (y.weight - y.points) - (x.weight - x.points)).slice(0, 7).map((c) => html`<div class="comp"><span>${c.label}</span><div class="bar ${c.fraction >= .75 ? "mint" : c.fraction < .45 ? "coral" : ""}"><i style="width:${Math.round(c.fraction * 100)}%"></i></div><span>${c.points}/${c.weight}</span></div>`) : html`<div class="empty">No data yet.</div>`}</section>
    <section class="tile c4"><div class="eyebrow">Role coverage</div><div class="canvas-box sm">${Object.keys(o.skills.categories).length >= 3 ? html`<canvas id="ch-radar"></canvas>` : html`<div class="empty">Upload a resume to see skill coverage by area.</div>`}</div></section>

    <section class="tile c4"><div class="eyebrow">Pipeline</div>${p.total ? html`<div class="canvas-box sm"><canvas id="ch-funnel"></canvas></div>` : html`<div class="empty"><b>No applications yet</b><a href="#/opportunities">Find opportunities</a></div>`}</section>
    <section class="tile c4"><div class="eyebrow">Applications per week</div><div class="canvas-box sm"><canvas id="ch-weekly"></canvas></div></section>
    <section class="tile c4"><div class="eyebrow">In-demand skills (live listings)</div>${o.market.top_skills.length ? o.market.top_skills.slice(0, 7).map((s) => html`<div class="comp" style="grid-template-columns:110px 1fr 40px"><span>${s.skill}</span><div class="bar ${s.have ? "mint" : "coral"}"><i style="width:${Math.round(100 * s.jobs / o.market.top_skills[0].jobs)}%"></i></div><span>${s.jobs}</span></div>`)
      : html`<div class="empty">Open <a href="#/opportunities">Opportunities</a> once to load market data.</div>`}<div class="xs faint mt-s"><span style="color:var(--mint)">●</span> you have it &nbsp;<span style="color:var(--coral)">●</span> gap</div></section>

    <section class="tile c8"><div class="eyebrow">Top matches for you</div><div id="matches"><div class="skel" style="min-height:150px"></div></div>
      <a class="btn sm mt-s" href="#/opportunities">View all</a></section>
    <section class="tile c4"><div class="eyebrow">Learning roadmap</div>${o.skills.roadmap.length ? o.skills.roadmap.slice(0, 4).map((r) => html`<div class="item"><div class="row between"><span class="t">${r.skill}</span><span class="chip ${r.priority === "core" ? "coral" : "amber"}">${r.priority}</span></div><div class="xs muted">${r.action}</div></div>`) : html`<div class="empty">No gaps detected.</div>`}<a class="btn sm mt-s" href="#/skills">Full plan</a></section>
    <section class="tile c12"><div class="eyebrow">Activity · last 26 weeks</div><div class="heat" role="img" aria-label="Activity heatmap">${p.heatmap.map((h) => html`<i class="${h.count ? "l" + Math.min(3, Math.ceil(3 * h.count / maxHeat)) : ""}" title="${h.date}: ${h.count}"></i>`)}</div></section>
  </div>`);

  loadMatches(0);
  const c = { mint: cssv("--mint"), amber: cssv("--amber"), sky: cssv("--sky"), line: cssv("--line"), coral: cssv("--coral") };
  if (a.trend.length > 1) chart("ch-trend", { type: "line", data: { labels: a.trend.map((t) => t.label), datasets: [{ data: a.trend.map((t) => t.score), borderColor: c.amber, backgroundColor: c.amber + "22", fill: true, tension: .35, pointRadius: 3 }] }, options: { plugins: { legend: { display: false } }, scales: { y: { min: 0, max: 100 } } } });
  const cats = Object.entries(o.skills.categories);
  if (cats.length >= 3) chart("ch-radar", { type: "radar", data: { labels: cats.map((x) => x[0]), datasets: [{ data: cats.map((x) => Math.round(x[1] * 100)), borderColor: c.mint, backgroundColor: c.mint + "33", pointRadius: 2 }] }, options: { plugins: { legend: { display: false } }, scales: { r: { min: 0, max: 100, ticks: { display: false }, grid: { color: c.line }, angleLines: { color: c.line } } } } });
  if (p.total) chart("ch-funnel", { type: "bar", data: { labels: p.funnel.map((f) => LBL[f.status]), datasets: [{ data: p.funnel.map((f) => f.count), backgroundColor: [c.sky, c.amber, c.amber, c.mint, c.mint, c.coral], borderRadius: 8 }] }, options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { ticks: { precision: 0 } } } } });
  chart("ch-weekly", { type: "bar", data: { labels: p.weekly.map((w) => w.label), datasets: [{ data: p.weekly.map((w) => w.count), backgroundColor: c.amber, borderRadius: 6 }] }, options: { plugins: { legend: { display: false } }, scales: { y: { ticks: { precision: 0 }, beginAtZero: true } } } });
}


async function loadMatches(n) {
  const box = $("#matches"); if (!box) return;
  try {
    const d = await api("/opportunities?per_page=5&fast=1", { timeout: 15000 });
    if (!d.items.length) {
      mount(box, html`<div class="empty">${d.sync === "refreshing" ? html`<span class="spinner"></span><br>Fetching listings in the background…` : html`No listings yet. Open <a href="#/opportunities">Opportunities</a> to load some.`}</div>`);
      if (d.sync === "refreshing" && n < 8) setTimeout(() => loadMatches(n + 1), 5000);
      return;
    }
    mount(box, html`${d.items.map((j) => html`<div class="row item"><div class="logo">${j.logo ? html`<img src="${safeUrl(j.logo)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : (j.company || "?")[0]}</div>
      <div class="grow" style="min-width:0"><div class="t" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${j.title}</div><div class="sm muted">${j.company} · ${j.location || "Remote"} · <span class="chip ${j.kind === "internship" ? "violet" : j.kind === "freelance" ? "sky" : ""}">${cap(j.kind)}</span></div></div>
      ${j.match ? miniRing(j.match.score) : ""}</div>`)}`);
  } catch { if ($("#matches")) mount($("#matches"), html`<div class="empty">Could not load matches right now.</div>`); }
}
