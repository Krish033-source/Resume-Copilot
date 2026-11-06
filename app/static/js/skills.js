import { $, api, html, mount, chart, cssv, cap } from "./core.js";
import { S } from "./state.js";

export async function skills(v) {
  if (!S.latest) return mount(v, html`<div class="pagehead"><div><h1>Skill gap</h1></div></div><div class="tile empty"><b>Upload a resume first</b><a class="btn pri mt" href="#/resume">Upload resume</a></div>`);
  mount(v, html`<div class="pagehead"><div><h1>Skill gap &amp; roadmap</h1><p>Try “what if” roles to see how your resume maps to each one.</p></div>
    <label class="f" style="min-width:230px">Compare against<select class="input" id="role">${S.meta.roles.map((r) => html`<option ${r === S.latest.target_role ? "selected" : ""}>${r}</option>`)}</select></label></div><div class="bento" id="g"></div>`);
  $("#role").onchange = draw; draw();
}
async function draw() {
  const d = await api("/skill-gap?role=" + encodeURIComponent($("#role").value)), rr = d.role_report, cats = Object.entries(rr.categories);
  const have = rr.rows.filter((r) => r.status !== "missing").length;
  mount($("#g"), html`
  <section class="tile c4 tint-mint"><div class="eyebrow">Weighted coverage</div><div class="big">${Math.round(rr.coverage * 100)}%</div><div class="sm muted">${have} of ${rr.rows.length} ${rr.role} skills present</div>
    <div class="bar mt"><i style="width:${Math.round(rr.coverage * 100)}%"></i></div></section>
  <section class="tile c4"><div class="eyebrow">By area</div><div class="canvas-box sm"><canvas id="rd"></canvas></div></section>
  <section class="tile c4"><div class="eyebrow">How credit works</div><div class="sm muted"><span class="chip mint">shown in use</span> full credit<br><br><span class="chip amber">listed only</span> 60% credit<br><br><span class="chip out">missing</span> no credit<br><br>Core skills weigh 3x, important 2x, nice-to-have 1x.</div></section>
  <section class="tile c6"><div class="eyebrow">Skill by skill</div>${rr.rows.map((r) => html`<div class="row item" style="padding:7px 0"><span class="grow">${r.skill} <span class="xs faint">${r.weight === 3 ? "core" : r.weight === 2 ? "important" : "nice"}</span></span><span class="chip ${r.status === "context" ? "mint" : r.status === "listed" ? "amber" : "out"}">${r.status === "context" ? "shown in use" : r.status}</span></div>`)}</section>
  <section class="tile c6"><div class="eyebrow">Your roadmap</div>${d.roadmap.length ? d.roadmap.map((s, i) => html`<div class="step"><div class="n">${i + 1}</div><div><div style="font-weight:600">${s.skill} <span class="chip ${s.priority === "core" ? "coral" : "amber"}">${s.priority}</span></div><div class="sm muted">${s.action}</div></div><span class="chip">${s.weeks}w</span></div>`) : html`<div class="empty"><b>No gaps</b>You cover this role well.</div>`}</section>`);
  chart("rd", { type: "radar", data: { labels: cats.map((c) => c[0]), datasets: [{ data: cats.map((c) => Math.round(c[1] * 100)), borderColor: cssv("--amber"), backgroundColor: cssv("--amber") + "33" }] }, options: { plugins: { legend: { display: false } }, scales: { r: { min: 0, max: 100, ticks: { display: false } } } } });
}
