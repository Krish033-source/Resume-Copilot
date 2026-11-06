import { $, $$, api, html, mount, icon, toast, busy, cap } from "./core.js";
import { S } from "./state.js";

const KIND = { cold_email: "Cold email", linkedin_dm: "LinkedIn note", cover_letter: "Cover letter", referral: "Referral request" };
let qs = [], qi = 0;

export async function tools(v) {
  const pre = JSON.parse(sessionStorage.getItem("rc-outreach") || "{}"); sessionStorage.removeItem("rc-outreach");
  mount(v, html`<div class="pagehead"><div><h1>AI tools</h1><p>${S.meta.ai_enabled ? "Powered by Groq" : "Template mode (add GROQ_API_KEY for AI)"} · uses only facts from your resume.</p></div></div>
  <div class="bento"><section class="tile c6"><div class="eyebrow">Outreach writer</div><div class="stack">
    <div class="seg" id="kind">${Object.entries(KIND).map(([k, l], i) => html`<button data-k="${k}" class="${i === 0 ? "on" : ""}">${l}</button>`)}</div>
    <div class="row"><label class="f grow">Company<input class="input" id="oc" value="${pre.company || ""}"></label><label class="f grow">Role<input class="input" id="or" value="${pre.role || ""}"></label></div>
    <button class="btn pri" id="og">${icon("mail")} Generate</button><div id="oo"></div></div></section>
  <section class="tile c6"><div class="eyebrow">Interview practice</div><div id="iv"><div class="skel"></div></div></section></div>`);
  let kind = "cold_email"; $("#kind").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; kind = b.dataset.k; $$("#kind button").forEach((x) => x.classList.toggle("on", x === b)); };
  $("#og").onclick = (e) => busy(e.currentTarget, async () => { try {
    const o = await api("/outreach", { method: "POST", json: { kind, company: $("#oc").value, role: $("#or").value, job_id: pre.job_id } });
    mount($("#oo"), html`${o.subject ? html`<div class="sm"><b>Subject:</b> ${o.subject}</div>` : ""}<div class="pre mt-s" id="ot">${o.body}</div><div class="row mt-s"><button class="btn sm" id="cp">${icon("copy")} Copy</button><span class="chip ${o.ai ? "mint" : ""}">${o.ai ? "AI written" : "template"}</span></div>`);
    $("#cp").onclick = () => navigator.clipboard.writeText((o.subject ? o.subject + "\n\n" : "") + o.body).then(() => toast("Copied")); } catch (er) { toast(er.message, "err"); } });
  const q = await api("/interview/questions"); qs = q.questions; qi = 0; drawQ(q.role);
}
function drawQ(role) {
  const q = qs[qi]; if (!q) return;
  mount($("#iv"), html`<div class="row between"><span class="chip violet">${q.category}</span><span class="xs faint">${qi + 1} / ${qs.length}</span></div><div style="font:600 18px var(--f-display);margin:10px 0">${q.question}</div>
    <textarea class="input" id="ans" placeholder="Answer as you would in the interview. Use real examples and numbers."></textarea>
    <div class="row mt-s"><button class="btn pri sm" id="ev">Get feedback</button><button class="btn sm" id="nx">Next question</button></div><div id="fb" class="mt"></div>`);
  $("#nx").onclick = () => { qi = (qi + 1) % qs.length; drawQ(role); };
  $("#ev").onclick = (e) => busy(e.currentTarget, async () => { try {
    const f = await api("/interview/evaluate", { method: "POST", json: { role, question: q.question, answer: $("#ans").value } });
    const L = (t, a) => a?.length ? html`<div class="eyebrow mt-s">${t}</div><ul class="sm" style="margin:0;padding-left:18px">${a.map((x) => html`<li>${x}</li>`)}</ul>` : "";
    mount($("#fb"), html`<div class="row"><div class="big" style="font-size:40px">${f.score}<span class="faint" style="font-size:18px">/10</span></div><span class="chip ${f.ai ? "mint" : ""}">${f.ai ? "AI feedback" : "rubric check"}</span></div>${L("Strengths", f.strengths)}${L("Improve", f.improvements)}${L("Strong answer outline", f.model_answer_outline)}${f.follow_up ? html`<div class="sm mt-s"><b>Likely follow-up:</b> ${f.follow_up}</div>` : ""}`);
  } catch (er) { toast(er.message, "err"); } });
}
