import { $, $$, api, html, mount, icon, ring, toast, busy, cap, esc, ago, sevLabel, ApiError, dialog } from "./core.js";
import { S, loadLatest } from "./state.js";

let cur = null;
const MONTHS = (m) => (m >= 12 ? (m / 12).toFixed(1).replace(/\.0$/, "") + " yrs" : m + " mo");
const levelChip = { strong: ["mint", "Strong"], moderate: ["amber", "Mentioned"], weak: ["sky", "Link only"], none: ["coral", "None found"] };

export async function resumeView(v) {
  mount(v, html`<div class="pagehead"><div><h1>Resume &amp; ATS</h1><p>Upload a PDF, DOCX or TXT. Every finding below is backed by text found in your file.</p></div></div>
    <div class="bento"><section class="tile c12" id="up"></section></div><div id="res" class="bento mt"></div>`);
  drawUpload();
  const l = S.latest || (await loadLatest());
  if (l) { cur = l; drawResult(); } else mount($("#res"), html`<div class="tile c12 empty"><b>No resume yet</b>Upload one to see your ATS score, internship/open-source/certification detection and a prioritised fix list.</div>`);
}

function drawUpload() {
  if (!$("#up")) return;
  mount($("#up"), html`<div class="row wrap" style="gap:18px;align-items:stretch">
    <div class="drop grow" id="drop" tabindex="0" role="button" aria-label="Upload resume">${icon("upload")}<b>Drop your resume here or click to browse</b><span class="sm muted">PDF, DOCX or TXT · up to 8 MB · stored privately in your account</span><input type="file" id="file" accept=".pdf,.docx,.txt" hidden></div>
    <div class="stack" style="min-width:240px;flex:0 0 260px"><label class="f">Target role<select class="input" id="role">${S.meta.roles.map((r) => html`<option ${r === (cur?.target_role || S.user.target_role) ? "selected" : ""}>${r}</option>`)}</select></label>
      <div class="xs faint">Scoring adapts to your stage (fresher, early career, experienced) and this role's keyword profile.</div></div></div>`);
  const drop = $("#drop"), file = $("#file");
  drop.onclick = () => file.click(); drop.onkeydown = (e) => (e.key === "Enter" || e.key === " ") && file.click();
  ["dragover", "dragenter"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]));
  file.onchange = () => file.files[0] && upload(file.files[0]);
  $("#role").onchange = async (e) => { if (!cur) return; try { cur = await api(`/resumes/${cur.id}/rescore`, { method: "POST", json: { role: e.target.value } }); S.latest = cur; drawResult(); toast("Re-scored for " + e.target.value); } catch (er) { toast(er.message, "err"); } };
}

async function upload(file) {
  const fd = new FormData(); fd.append("file", file); fd.append("target_role", $("#role").value);
  mount($("#res"), html`<div class="tile c12 skel"></div>`); const d = $("#drop"); d.innerHTML = '<span class="spinner"></span><b>Analysing…</b>';
  try { cur = await api("/resumes", { method: "POST", form: fd }); S.latest = cur; drawUpload(); drawResult(); toast("Analysis complete: " + cur.ats_score + "/100");
    if (S.meta.ai_enabled) runAI(true); }
  catch (e) { drawUpload(); mount($("#res"), ""); toast(e.message, "err"); }
}

const list = (arr, fn, empty) => arr.length ? arr.map(fn) : html`<div class="sm faint">${empty}</div>`;

function drawResult() {
  if (!$("#res")) return;
  const r = cur, a = r.analysis, p = r.parsed, c = p.contact, t = p.totals;
  const sevCount = (s) => a.findings.filter((f) => f.severity === s).length;
  const rr = a.role_report;
  mount($("#res"), html`
  <section class="tile c3 r2 ${a.score >= 75 ? "tint-mint" : a.score >= 55 ? "tint-amber" : ""}"><div class="eyebrow">ATS score</div><div style="display:grid;place-items:center;gap:6px">${ring(a.score, 160)}
    <div style="font:700 20px var(--f-display)">${a.grade}</div><span class="chip violet">${a.stage_label}</span>
    ${a.caps.length ? html`<div class="sm" style="color:var(--coral);text-align:center">Capped: ${a.caps.join("; ")}</div>` : ""}
    <div class="xs faint">${r.filename}</div></div></section>
  <section class="tile c5 r2"><div class="eyebrow">Score breakdown (weights for ${a.stage_label.toLowerCase()})</div>
    ${Object.values(a.components).map((x) => html`<div class="comp"><span>${x.label}</span><div class="bar ${x.fraction >= .75 ? "mint" : x.fraction < .45 ? "coral" : ""}"><i style="width:${Math.round(x.fraction * 100)}%"></i></div><span>${x.points}/${x.weight}</span></div>`)}</section>
  <section class="tile c4 r2"><div class="eyebrow">Biggest score gains</div>${list(a.quick_wins, (q, i) => html`<div class="step"><div class="n">${i + 1}</div><div><div style="font-weight:600">${q.title}</div><div class="sm muted">${q.fix}</div></div>${q.points ? html`<span class="chip mint">+${q.points}</span>` : ""}</div>`, "No major fixes pending.")}</section>

  <section class="tile c6"><div class="eyebrow">Experience &amp; internships</div>
    <div class="row wrap" style="margin-bottom:8px"><span class="chip violet">${t.internships} internship${t.internships === 1 ? "" : "s"}</span><span class="chip">${t.jobs} job${t.jobs === 1 ? "" : "s"}</span>${t.freelance ? html`<span class="chip sky">${t.freelance} freelance</span>` : ""}<span class="chip mint">${MONTHS(t.experience_months)} total</span></div>
    ${list(p.experience, (e) => html`<div class="item"><div class="row between"><span class="t">${e.role || e.heading}</span><span class="chip ${e.kind === "internship" ? "violet" : e.kind === "freelance" ? "sky" : ""}">${e.kind}</span></div>
      <div class="sm muted">${e.org} ${e.date_text ? "· " + e.date_text : html`<span style="color:var(--coral)">· no dates found</span>`} · ${e.bullets.length} bullets</div></div>`, "No work or internship entries detected.")}</section>
  <section class="tile c6"><div class="eyebrow">Projects</div>${list(p.projects, (e) => html`<div class="item"><div class="t">${e.heading}</div>
      <div class="chips mt-s">${e.tech.slice(0, 6).map((x) => html`<span class="chip sky">${x}</span>`)}${e.urls.length ? html`<span class="chip mint">link</span>` : html`<span class="chip out">no link</span>`}</div>
      <div class="xs muted mt-s">${e.bullets.length} detail line${e.bullets.length === 1 ? "" : "s"}</div></div>`, "No projects detected.")}</section>

  <section class="tile c4"><div class="eyebrow">Certifications</div>${list(p.certifications, (x) => html`<div class="item"><div class="sm" style="font-weight:600">${x.name}</div><span class="chip ${x.tier === "vendor" ? "mint" : x.tier === "platform" ? "amber" : ""}">${x.tier}</span> ${x.year ? html`<span class="chip">${x.year}</span>` : ""}</div>`, "None detected.")}</section>
  <section class="tile c4"><div class="eyebrow">Open source</div><span class="chip ${levelChip[p.open_source.level][0]}">${levelChip[p.open_source.level][1]}</span>
    ${p.open_source.evidence.map((e) => html`<blockquote class="sm muted" style="margin:8px 0 0;border-left:2px solid var(--line2);padding-left:8px">${e}</blockquote>`)}
    ${p.open_source.level === "none" ? html`<div class="sm muted mt-s">Add merged PRs, GSoC/Outreachy/LFX or maintained repos.</div>` : ""}</section>
  <section class="tile c4"><div class="eyebrow">Achievements</div>${list(p.achievements, (x) => html`<div class="item"><span class="chip amber">${x.type.replace("_", " ")}</span><div class="sm mt-s">${x.text}</div></div>`, "None detected.")}</section>

  <section class="tile c4"><div class="eyebrow">Contact &amp; education</div>
    ${[["Name", c.name], ["Email", c.email], ["Phone", c.phone], ["LinkedIn", c.linkedin], ["GitHub", c.github], ["Location", c.location], ["Degree", p.education.degree], ["Grad year", p.education.grad_year], ["CGPA", p.education.cgpa ? p.education.cgpa + "/" + p.education.cgpa_scale : ""]].map(([k, x]) => html`<div class="kv"><span>${k}</span><span>${x || html`<span style="color:var(--coral)">missing</span>`}</span></div>`)}</section>
  <section class="tile c8"><div class="eyebrow">${a.role} keyword match · ${Math.round(rr.coverage * 100)}% weighted coverage</div>
    <div class="chips">${rr.rows.map((x) => html`<span class="chip ${x.status === "context" ? "mint" : x.status === "listed" ? "amber" : "out"}" title="${x.weight === 3 ? "core" : x.weight === 2 ? "important" : "nice to have"}">${x.skill}${x.weight === 3 ? " ★" : ""}</span>`)}</div>
    <div class="xs faint mt"><span class="chip mint">shown in use</span> <span class="chip amber">listed only</span> <span class="chip out">missing</span> · ★ core skills</div></section>

  <section class="tile c12"><div class="row between wrap"><div class="eyebrow" style="margin:0">Findings with evidence</div>
    <div class="seg" id="fsev"><button data-s="" class="on">All ${a.findings.length}</button>${["critical", "warning", "info", "good"].map((s) => html`<button data-s="${s}">${sevLabel[s]} ${sevCount(s)}</button>`)}</div></div><div id="flist" class="mt"></div></section>

  <section class="tile c6"><div class="eyebrow">Match against a job description</div><textarea class="input" id="jd" placeholder="Paste a job description to see required skills you are missing, keyword coverage and experience fit…"></textarea>
    <div class="row mt-s"><button class="btn pri sm" id="jdgo">Analyse match</button>${S.meta.ai_enabled ? html`<button class="btn sm" id="tailor">${icon("spark")} Tailor with AI</button>` : ""}</div><div id="jdout" class="mt"></div></section>
  <section class="tile c6 tint-violet"><div class="row between"><div class="eyebrow" style="margin:0">AI recruiter review ${S.meta.ai_model ? html`<span class="chip">${S.meta.ai_model}</span>` : ""}</div>
    <button class="btn sm" id="ai" ${S.meta.ai_enabled ? "" : "disabled"}>${icon("spark")} ${r.ai_review ? "Re-run" : "Run review"}</button></div>
    <div id="aiout" class="mt">${S.meta.ai_enabled ? "" : html`<div class="sm muted">AI review is off. Set <span class="mono">GROQ_API_KEY</span> on the server to enable. The ATS score above never depends on AI.</div>`}</div></section>
  <section class="tile c12"><div class="eyebrow">Version history</div><div id="hist"></div></section>`);
  drawFindings(""); if (cur.ai_review) drawAI(cur.ai_review);
  $("#fsev").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; $$("#fsev button").forEach((x) => x.classList.toggle("on", x === b)); drawFindings(b.dataset.s); };
  $("#jdgo").onclick = (e) => busy(e.currentTarget, jdMatch); $("#tailor") && ($("#tailor").onclick = (e) => busy(e.currentTarget, tailor));
  $("#ai") && ($("#ai").onclick = (e) => busy(e.currentTarget, () => runAI(false)));
  drawHistory();
}

function drawFindings(sev) {
  const fs = cur.analysis.findings.filter((f) => !sev || f.severity === sev);
  mount($("#flist"), fs.length ? html`${fs.map((f) => html`<details class="finding" ${f.severity === "critical" ? "open" : ""}><summary><span class="sev ${f.severity}"></span><span>${f.title}</span>${f.points_at_stake ? html`<span class="pts">+${f.points_at_stake} pts</span>` : ""}</summary>
    <div class="body">${f.detail ? html`<div>${f.detail}</div>` : ""}${f.evidence.map((e) => html`<blockquote>${e}</blockquote>`)}${f.fix ? html`<div class="fix"><b>Fix:</b> ${f.fix}</div>` : ""}</div></details>`)}` : html`<div class="empty">Nothing here.</div>`);
}

async function jdMatch() {
  const jd = $("#jd").value; try {
    const m = await api(`/resumes/${cur.id}/jd-match`, { method: "POST", json: { jd } });
    mount($("#jdout"), html`<div class="row"><div>${ring(m.score, 90, "Match")}</div><div class="grow"><div style="font:700 18px var(--f-display)">${m.score >= 70 ? "Strong match" : m.score >= 45 ? "Partial match" : "Weak match"}</div><div class="sm muted">Experience: JD asks ${m.years_required ? m.years_required + "+ yrs" : "n/a"}, resume shows ~${m.years_have} yrs</div></div></div>
      <div class="chips mt">${m.skills.map((s) => html`<span class="chip ${s.status === "context" ? "mint" : s.status === "listed" ? "amber" : "out"}">${s.skill}${s.requirement === "preferred" ? " (pref)" : ""}</span>`)}</div>
      ${m.keywords.length ? html`<div class="xs faint mt-s">Other JD keywords:</div><div class="chips">${m.keywords.map((k) => html`<span class="chip ${k.found ? "mint" : "out"}">${k.keyword}</span>`)}</div>` : ""}
      ${m.findings.map((f) => html`<div class="sm mt-s"><span class="sev ${f.severity}" style="display:inline-block;margin-right:6px"></span><b>${f.title}</b><div class="muted">${f.fix}</div></div>`)}`);
  } catch (e) { toast(e.message, "err"); }
}

async function tailor() {
  try { const t = await api(`/resumes/${cur.id}/tailor`, { method: "POST", json: { jd: $("#jd").value }, timeout: 90000 });
    mount($("#jdout"), html`<div class="eyebrow">AI tailoring</div><div class="pre">${t.summary}</div>${t.keyword_additions.length ? html`<div class="chips mt-s">${t.keyword_additions.map((k) => html`<span class="chip mint">${k}</span>`)}</div>` : ""}
      ${t.bullet_edits.map((b) => html`<div class="item"><div class="xs faint">Before</div><div class="sm muted">${b.original}</div><div class="xs faint mt-s">After</div><div class="sm">${b.improved}</div></div>`)}
      ${t.honest_gaps.length ? html`<div class="sm mt-s"><b>Honest gaps:</b><ul>${t.honest_gaps.map((g) => html`<li>${g}</li>`)}</ul></div>` : ""}${t.cover_note ? html`<div class="eyebrow mt">Cover note</div><div class="pre">${t.cover_note}</div>` : ""}`);
  } catch (e) { toast(e.message, "err"); }
}

async function runAI(silent) {
  const out = $("#aiout"); if (out && silent) out.innerHTML = '<div class="row"><span class="spinner"></span><span class="sm muted">Running AI review…</span></div>';
  try { const d = await api(`/resumes/${cur.id}/ai-review`, { method: "POST", timeout: 90000 }); cur.ai_review = d.ai_review; drawAI(d.ai_review); }
  catch (e) { if (!silent) toast(e.message, "err"); if (out) out.innerHTML = `<div class="sm muted">${esc(e.message)}</div>`; }
}
function drawAI(a) {
  const ul = (t, arr) => arr?.length ? html`<div class="eyebrow mt">${t}</div><ul class="sm" style="margin:0;padding-left:18px">${arr.map((x) => html`<li>${x}</li>`)}</ul>` : "";
  mount($("#aiout"), html`<div style="font:600 17px var(--f-display)">${a.headline}</div><span class="chip ${a.verdict === "strong" ? "mint" : a.verdict === "promising" ? "amber" : "coral"} mt-s">${a.verdict.replace("_", " ")}</span>
    ${ul("Strengths", a.strengths)}${ul("Gaps", a.gaps)}
    ${Object.entries(a.experience_notes || {}).filter(([, x]) => x).map(([k, x]) => html`<div class="sm mt-s"><b>${cap(k.replace("_", " "))}:</b> <span class="muted">${x}</span></div>`)}
    ${a.bullet_rewrites.length ? html`<div class="eyebrow mt">Bullet rewrites</div>${a.bullet_rewrites.map((b) => html`<div class="item"><div class="sm muted">${b.original} ${b.verified_original ? "" : html`<span class="chip out">not found verbatim</span>`}</div><div class="sm mt-s">→ ${b.improved}</div><div class="xs faint">${b.why}</div></div>`)}` : ""}
    ${a.missing_keywords.length ? html`<div class="eyebrow mt">Missing keywords</div><div class="chips">${a.missing_keywords.map((k) => html`<span class="chip out">${k}</span>`)}</div>` : ""}
    ${a.summary_suggestion ? html`<div class="eyebrow mt">Suggested summary</div><div class="pre">${a.summary_suggestion}</div>` : ""}${ul("Next steps", a.next_steps)}${ul("Red flags", a.red_flags)}
    <div class="xs faint mt">AI text is advice only. Verify every claim before using it. Placeholders like [X%] need your real numbers.</div>`);
}

async function drawHistory() {
  const h = (await api("/resumes")).items;
  mount($("#hist"), h.map((x) => html`<div class="row item"><div class="grow"><div class="t">${x.filename}</div><div class="xs muted">${ago(x.created_at)} · ${x.target_role}</div></div>
    <span class="chip ${x.ats_score >= 75 ? "mint" : x.ats_score >= 55 ? "amber" : "coral"}">${x.ats_score}</span>
    <button class="btn sm" data-open="${x.id}">View</button><a class="btn sm" href="/api/resumes/${x.id}/download">Download</a><button class="btn sm danger icon" data-del="${x.id}" aria-label="Delete">${icon("trash")}</button></div>`));
  $$("[data-open]").forEach((b) => b.onclick = async () => { cur = await api("/resumes/" + b.dataset.open); drawResult(); window.scrollTo({ top: 0, behavior: "smooth" }); });
  $$("[data-del]").forEach((b) => b.onclick = async () => { if (!confirm("Delete this resume version?")) return; await api("/resumes/" + b.dataset.del, { method: "DELETE" });
    const l = await loadLatest(); cur = l; if (l) drawResult(); else mount($("#res"), html`<div class="tile c12 empty"><b>No resume yet</b></div>`); });
}
