import { $, $$, api, html, mount, icon, toast, cap, dialog, ago } from "./core.js";
import { S } from "./state.js";

const LBL = { saved: "Saved", applied: "Applied", oa: "Online test", interview: "Interview", offer: "Offer", rejected: "Rejected" };
let items = [];

export async function tracker(v) {
  mount(v, html`<div class="pagehead"><div><h1>Application tracker</h1><p>Drag cards between stages. Every move is logged for your analytics.</p></div><button class="btn pri" id="add">${icon("plus")} Add application</button></div><div id="kb"></div>`);
  $("#add").onclick = () => form();
  await refresh();
}
async function refresh() { const d = await api("/applications"); items = d.items; draw(d.statuses); }

function draw(statuses) {
  if (!items.length) { mount($("#kb"), html`<div class="tile empty"><b>Nothing tracked yet</b>Add one manually, or press “Track” on any listing in Opportunities.</div>`); return; }
  mount($("#kb"), html`<div class="kanban">${statuses.map((s) => html`<div class="col" data-s="${s}"><h4><span>${LBL[s]}</span><span>${items.filter((x) => x.status === s).length}</span></h4>
    ${items.filter((x) => x.status === s).map((a) => html`<div class="card" draggable="true" data-id="${a.id}"><b>${a.company}</b><div class="sm muted">${a.role}</div>
      <div class="row mt-s"><span class="chip ${a.kind === "internship" ? "violet" : a.kind === "freelance" ? "sky" : ""}">${cap(a.kind)}</span><span class="xs faint">${a.applied_on ? ago(a.applied_on) : ""}</span></div></div>`)}</div>`)}</div>`);
  $$(".card").forEach((c) => { c.ondragstart = (e) => { e.dataTransfer.setData("text/plain", c.dataset.id); c.classList.add("drag"); }; c.ondragend = () => c.classList.remove("drag"); c.onclick = () => form(items.find((x) => x.id == c.dataset.id)); });
  $$(".col").forEach((col) => { col.ondragover = (e) => { e.preventDefault(); col.classList.add("over"); }; col.ondragleave = () => col.classList.remove("over");
    col.ondrop = async (e) => { e.preventDefault(); col.classList.remove("over"); const id = e.dataTransfer.getData("text/plain"); const a = items.find((x) => x.id == id); if (!a || a.status === col.dataset.s) return;
      try { await api("/applications/" + id, { method: "PATCH", json: { status: col.dataset.s } }); await refresh(); } catch (er) { toast(er.message, "err"); } }; });
}

function form(a) {
  const d = dialog(html`<h2 style="font-size:22px;margin-bottom:14px">${a ? "Edit application" : "Add application"}</h2><form id="tf" class="stack">
    <div class="row wrap"><label class="f grow">Company<input class="input" name="company" required value="${a?.company || ""}"></label><label class="f grow">Role<input class="input" name="role" required value="${a?.role || ""}"></label></div>
    <div class="row wrap"><label class="f grow">Status<select class="input" name="status">${S.meta.statuses.map((s) => html`<option value="${s}" ${(a?.status || "applied") === s ? "selected" : ""}>${LBL[s]}</option>`)}</select></label>
      <label class="f grow">Type<select class="input" name="kind">${["job", "internship", "freelance"].map((k) => html`<option value="${k}" ${(a?.kind || "job") === k ? "selected" : ""}>${cap(k)}</option>`)}</select></label></div>
    <label class="f">Link<input class="input" name="url" type="url" value="${a?.url || ""}"></label><label class="f">Notes<textarea class="input" name="notes">${a?.notes || ""}</textarea></label>
    ${a?.history?.length ? html`<div class="xs muted">${a.history.map((h) => html`<div>${h.from ? LBL[h.from] + " → " : ""}${LBL[h.to]} · ${ago(h.at)}</div>`)}</div>` : ""}
    <div class="row"><button class="btn pri">Save</button><button type="button" class="btn ghost" id="cx">Cancel</button>${a ? html`<button type="button" class="btn danger" id="rm" style="margin-left:auto">Delete</button>` : ""}</div></form>`);
  $("#cx", d).onclick = () => d.close();
  $("#rm", d)?.addEventListener("click", async () => { if (!confirm("Delete this application?")) return; await api("/applications/" + a.id, { method: "DELETE" }); d.close(); refresh(); });
  $("#tf", d).onsubmit = async (e) => { e.preventDefault(); const j = Object.fromEntries(new FormData(e.target));
    try { await api(a ? "/applications/" + a.id : "/applications", { method: a ? "PATCH" : "POST", json: j }); d.close(); refresh(); } catch (er) { toast(er.message, "err"); } };
}
