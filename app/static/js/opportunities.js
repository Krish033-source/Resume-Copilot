import { $, $$, api, html, mount, icon, toast, busy, cap, ago, safeUrl, miniRing, dialog, esc } from "./core.js";
import { S } from "./state.js";

const TABS = [["all", "All"], ["job", "Jobs"], ["internship", "Internships"], ["freelance", "Freelance"], ["research", "Research"], ["explore", "Explore"]];
let f = { tab: "all", q: "", location: "", remote: false, sort: "match", page: 1, rsource: "openalex" };

export async function opportunities(v) {
  mount(v, html`<div class="pagehead"><div><h1>Opportunities</h1><p>Live jobs, internships, freelance and research, ranked by how well they fit your resume.</p></div></div>
    <div class="bento"><section class="tile c12"><div class="row between wrap"><div class="seg" id="tabs">${TABS.map(([k, l]) => html`<button data-t="${k}" class="${f.tab === k ? "on" : ""}">${l}</button>`)}</div>
      <div class="row wrap" id="filters"></div></div></section></div><div id="syncbar" class="sync"></div><div id="out" class="bento mt"></div><div id="foot" class="xs faint mt"></div>`);
  $("#tabs").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; f.tab = b.dataset.t; f.page = 1; $$("#tabs button").forEach((x) => x.classList.toggle("on", x === b)); load(); };
  load();
}

function filters() {
  const t = f.tab;
  if (t === "explore") return mount($("#filters"), "");
  if (t === "research") return mount($("#filters"), html`<input class="input" id="q" placeholder="Search papers…" value="${f.q}" style="width:230px"><select class="input" id="rs" style="width:auto"><option value="openalex" ${f.rsource === "openalex" ? "selected" : ""}>OpenAlex</option><option value="arxiv" ${f.rsource === "arxiv" ? "selected" : ""}>arXiv</option></select><button class="btn pri sm" id="go">${icon("search")} Search</button>`);
  mount($("#filters"), html`<input class="input" id="q" placeholder="Role, skill or company" value="${f.q}" style="width:200px"><input class="input" id="loc" placeholder="Location" value="${f.location}" style="width:140px">
    <label class="row sm muted"><input type="checkbox" id="rem" ${f.remote ? "checked" : ""}> Remote</label><select class="input" id="sort" style="width:auto"><option value="match" ${f.sort === "match" ? "selected" : ""}>Best match</option><option value="recent" ${f.sort === "recent" ? "selected" : ""}>Most recent</option></select><button class="btn pri sm" id="go">${icon("search")} Search</button>`);
}
function bindFilters() {
  const go = $("#go"); if (!go) return;
  const run = () => { f.q = $("#q").value.trim(); if ($("#loc")) { f.location = $("#loc").value.trim(); f.remote = $("#rem").checked; f.sort = $("#sort").value; } if ($("#rs")) f.rsource = $("#rs").value; f.page = 1; load(false); };
  go.onclick = run; $("#q").onkeydown = (e) => e.key === "Enter" && run();
}

let pollTimer = null, pollN = 0, lastSig = "";
function syncBar(d) { const el = $("#syncbar"); if (!el) return; el.innerHTML = d && d.sync === "refreshing" ? `<span class="spinner"></span> Loading more listings from other sources in the background… <b>${d.total}</b> so far` : ""; }
function schedule(d) {
  clearTimeout(pollTimer);
  if (d && d.sync === "refreshing" && pollN < 14) pollTimer = setTimeout(() => { pollN++; if ($("#out") && !["research", "explore"].includes(f.tab)) load(false, true); }, 5000);
}

async function load(redraw = true, silent = false) {
  if (redraw) { filters(); } bindFilters();
  const out = $("#out");
  if (!silent) { clearTimeout(pollTimer); pollN = 0; lastSig = ""; mount(out, html`<div class="tile c6 skel"></div><div class="tile c6 skel"></div>`); }
  try {
    if (f.tab === "research") { syncBar(null); return await research(out); }
    if (f.tab === "explore") { syncBar(null); return await explore(out); }
    const qs = new URLSearchParams({ q: f.q, location: f.location, sort: f.sort, page: f.page, per_page: 20 }); if (f.tab !== "all") qs.set("kind", f.tab); if (f.remote) qs.set("remote", "1");
    const d = await api("/opportunities?" + qs, { timeout: 25000 });
    if (!$("#out")) return;                                  // user left the page
    syncBar(d);
    const sig = d.items.map((x) => x.id).join(",") + "|" + d.total;
    if (silent && sig === lastSig) return schedule(d);       // nothing new, keep polling quietly
    lastSig = sig;
    if (!d.items.length) {
      mount(out, html`<div class="tile c12 empty">${d.sync === "refreshing" ? html`<span class="spinner"></span><b>Fetching listings…</b>Live results are being collected. The first load can take up to a minute. This page updates by itself.` : html`<b>No matches</b>Try a broader keyword, or open the Explore tab for platforms without public APIs.`}</div>`);
      schedule(d); return foot();
    }
    mount(out, html`${!d.personalized ? html`<div class="tile c12 tint-amber"><b>Upload a resume</b> <span class="muted">to see match scores and get listings ranked for your skills.</span> <a href="#/resume">Upload</a></div>` : ""}
      ${d.items.map(card)}<div class="c12 row" style="justify-content:center">${d.page > 1 ? html`<button class="btn" id="prev">Previous</button>` : ""}<span class="sm muted">Page ${d.page} / ${d.pages} · ${d.total} listings</span>${d.page < d.pages ? html`<button class="btn" id="next">Next</button>` : ""}</div>`);
    $$("[data-save]").forEach((b) => b.onclick = () => toggleSave(b)); $$("[data-track]").forEach((b) => b.onclick = () => track(b.dataset.track));
    $$("[data-open]").forEach((b) => b.onclick = () => detail(b.dataset.open));
    $("#prev") && ($("#prev").onclick = () => { f.page--; load(false); window.scrollTo(0, 0); }); $("#next") && ($("#next").onclick = () => { f.page++; load(false); window.scrollTo(0, 0); });
    schedule(d); foot();
  } catch (e) { if (!silent) mount(out, html`<div class="tile c12 empty"><b>Could not load</b>${e.message}</div>`); }
}

const setFoot = (t) => { const el = $("#foot"); if (el) el.textContent = t; };
async function foot() {
  try { const s = (await api("/sources/status")).sources;
    mount($("#foot"), html`Sources: ${s.filter((x) => x.last_status === "ok" || x.configured && x.source === "adzuna").map((x) => html`<a href="${x.homepage}" target="_blank" rel="noopener noreferrer">${x.attribution}</a>${" · "}`)} Listings are cached and refreshed every few hours to respect each provider's limits.`); } catch {}
}

const card = (j) => html`<article class="tile c6"><div class="job"><div class="row"><div class="logo">${j.logo ? html`<img src="${safeUrl(j.logo)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : (j.company || "?")[0]}</div>
  <div class="grow" style="min-width:0"><div class="sm muted">${j.company || "Company"} · ${j.location || (j.remote ? "Remote" : "")}</div><h4 data-open="${j.id}">${j.title}</h4></div>${j.match ? miniRing(j.match.score) : ""}</div>
  <div class="chips"><span class="chip ${j.kind === "internship" ? "violet" : j.kind === "freelance" ? "sky" : ""}">${cap(j.kind)}</span>${j.remote ? html`<span class="chip mint">Remote</span>` : ""}${j.salary ? html`<span class="chip amber">${j.salary}</span>` : ""}<span class="chip">${j.source}</span><span class="chip">${ago(j.posted_at) || "date n/a"}</span></div>
  <div class="sm muted">${j.snippet}</div>
  ${j.match ? html`<div class="chips">${j.match.matched.slice(0, 5).map((s) => html`<span class="chip mint">${s}</span>`)}${j.match.missing.slice(0, 3).map((s) => html`<span class="chip out">${s}</span>`)}</div>` : ""}
  <div class="row" style="margin-top:auto"><a class="btn pri sm" href="${safeUrl(j.url)}" target="_blank" rel="noopener noreferrer">Apply ${icon("ext")}</a><button class="btn sm" data-track="${j.id}">${icon("plus")} Track</button>
    <button class="btn sm icon" data-save="${j.id}" data-on="${j.saved ? 1 : 0}" aria-label="Save">${icon("bookmark")}</button></div></div></article>`;

async function toggleSave(b) { const on = b.dataset.on === "1"; try { await api(`/opportunities/${b.dataset.save}/save`, { method: on ? "DELETE" : "POST" }); b.dataset.on = on ? 0 : 1; b.style.color = on ? "" : "var(--amber)"; toast(on ? "Removed from saved" : "Saved"); } catch (e) { toast(e.message, "err"); } }
async function track(id) { try { await api("/applications", { method: "POST", json: { job_id: id, status: "applied" } }); toast("Added to tracker as Applied"); } catch (e) { toast(e.message, "err"); } }

async function detail(id) {
  const j = await api("/opportunities/" + id);
  const d = dialog(html`<div class="row between"><div><div class="sm muted">${j.company} · ${j.location}</div><h2 style="font-size:24px">${j.title}</h2></div>${j.match ? miniRing(j.match.score) : ""}</div>
    ${j.match ? html`<div class="chips mt">${j.match.reasons.map((r) => html`<span class="chip amber">${r}</span>`)}</div><div class="chips mt-s">${j.match.matched.map((s) => html`<span class="chip mint">${s}</span>`)}${j.match.missing.map((s) => html`<span class="chip out">${s}</span>`)}</div>` : ""}
    <div class="pre mt" style="max-height:340px;overflow:auto">${j.description || "No description provided."}</div><div class="xs faint mt-s">${j.attribution}</div>
    <div class="row mt"><a class="btn pri" href="${safeUrl(j.url)}" target="_blank" rel="noopener noreferrer">Apply ${icon("ext")}</a><button class="btn" id="dt">${icon("plus")} Track</button><button class="btn" id="dm">${icon("mail")} Draft outreach</button><button class="btn ghost" id="dc">Close</button></div>`);
  $("#dt", d).onclick = () => track(id); $("#dc", d).onclick = () => d.close();
  $("#dm", d).onclick = () => { sessionStorage.setItem("rc-outreach", JSON.stringify({ company: j.company, role: j.title, job_id: j.id })); location.hash = "#/tools"; d.close(); };
}

async function research(out) {
  if (!f.q) { const t = await api("/research/topics"); mount(out, html`<div class="tile c12"><div class="eyebrow">Suggested topics for ${t.role}</div><div class="chips">${t.topics.map((x) => html`<button class="chip amber" data-topic="${x}" style="cursor:pointer">${x}</button>`)}</div></div>`);
    $$("[data-topic]").forEach((b) => b.onclick = () => { f.q = b.dataset.topic; filters(); bindFilters(); $("#q").value = f.q; load(false); }); return; }
  const d = await api(`/research?q=${encodeURIComponent(f.q)}&source=${f.rsource}&limit=12`);
  mount(out, d.items.length ? d.items.map((p) => html`<article class="tile c6"><div class="job"><div class="chips"><span class="chip violet">${p.source}</span>${p.year ? html`<span class="chip">${p.year}</span>` : ""}${p.citations != null ? html`<span class="chip">${p.citations} citations</span>` : ""}${p.related_skills.map((s) => html`<span class="chip mint">${s}</span>`)}</div>
    <h4><a href="${safeUrl(p.url)}" target="_blank" rel="noopener noreferrer" style="color:inherit">${p.title}</a></h4><div class="xs muted">${p.authors.join(", ")}${p.venue ? " · " + p.venue : ""}</div><div class="sm muted">${p.abstract}${p.abstract.length >= 690 ? "…" : ""}</div>
    <div class="row" style="margin-top:auto"><a class="btn sm" href="${safeUrl(p.url)}" target="_blank" rel="noopener noreferrer">Open ${icon("ext")}</a>${p.pdf_url ? html`<a class="btn sm" href="${safeUrl(p.pdf_url)}" target="_blank" rel="noopener noreferrer">PDF</a>` : ""}</div></div></article>`) : html`<div class="tile c12 empty"><b>No papers found</b>Try broader terms.</div>`);
  setFoot(d.source === "arxiv" ? "Thank you to arXiv for use of its open access interoperability." : "Paper metadata via OpenAlex.");
}

async function explore(out) {
  const d = await api("/explore?q=" + encodeURIComponent(f.q) + "&location=" + encodeURIComponent(f.location)); const groups = [...new Set(d.links.map((l) => l.group))];
  mount(out, html`<div class="tile c12 tint-sky"><b>Platforms without a public API.</b> <span class="muted">These open a pre-filled search for “${d.query}” on the site, so you stay inside their terms of service.</span></div>
    ${groups.map((g) => html`<div class="tile c6"><div class="eyebrow">${g}</div>${d.links.filter((l) => l.group === g).map((l) => html`<a class="row item" style="color:inherit;text-decoration:none" href="${safeUrl(l.url)}" target="_blank" rel="noopener noreferrer"><div class="grow"><div class="t">${l.name}</div><div class="xs muted">${l.note}</div></div>${icon("ext")}</a>`)}</div>`)}`);
  setFoot("Link patterns can change; if a site redirects, use its own search.");
}
