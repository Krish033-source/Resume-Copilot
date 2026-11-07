import { $, $$, api, html, mount, icon, toast, busy, cap, ring } from "./core.js";
import { S } from "./state.js";

const KIND = { cold_email: "Cold email", linkedin_dm: "LinkedIn note", cover_letter: "Cover letter", referral: "Referral request" };
let qs = [], qi = 0;
const O = { mode: "text", kind: "cold_email", tone: "concise", image: null, jd: "", job_id: null, last: null };

async function shrink(file) {   // keep uploads small and fast: max 1600px JPEG
  try {
    const bmp = await createImageBitmap(file), k = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas"); c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    return await new Promise((r) => c.toBlob((b) => r(b || file), "image/jpeg", 0.88));
  } catch { return file; }
}

export async function tools(v) {
  const pre = JSON.parse(sessionStorage.getItem("rc-outreach") || "{}"); sessionStorage.removeItem("rc-outreach");
  if (pre.job_id) { O.job_id = pre.job_id; O.mode = "text"; O.last = null; }
  const vis = S.meta.vision_enabled;
  mount(v, html`<div class="pagehead"><div><h1>AI tools</h1><p>${S.meta.ai_enabled ? "Writer: " + (S.meta.ai_model || "Groq") + (vis ? " · screenshots read by a vision model" : "") : "Template mode. Add GROQ_API_KEY for AI writing and screenshots"} · uses only facts from your resume.</p></div></div>
  <div class="bento"><section class="tile c7" id="ot"><div class="eyebrow">Smart outreach · paste a job, get a message</div><div class="stack">
    <div class="seg" id="mode"><button data-m="text" class="on">Paste job text</button><button data-m="image" ${vis ? "" : 'title="Needs GROQ_API_KEY"'}>Screenshot</button></div>
    <div id="inp"></div>
    <div class="row wrap"><div class="seg" id="kind">${Object.entries(KIND).map(([k, l]) => html`<button data-k="${k}" class="${k === O.kind ? "on" : ""}">${l}</button>`)}</div>
      <select class="input" id="tone" style="width:auto"><option value="concise">Concise</option><option value="friendly">Friendly</option><option value="formal">Formal</option></select></div>
    <button class="btn pri" id="og">${icon("spark")} Analyse &amp; write</button><div id="oo"></div></div></section>
  <section class="tile c5"><div class="eyebrow">Interview practice</div><div id="iv"><div class="skel"></div></div></section></div>`);
  drawInput(pre);
  $("#mode").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; O.mode = b.dataset.m; $$("#mode button").forEach((x) => x.classList.toggle("on", x === b)); drawInput(); };
  $("#kind").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; O.kind = b.dataset.k; $$("#kind button").forEach((x) => x.classList.toggle("on", x === b)); };
  $("#tone").onchange = (e) => (O.tone = e.target.value);
  $("#ot").addEventListener("paste", (e) => { const f = [...(e.clipboardData?.files || [])].find((x) => x.type.startsWith("image/")); if (f) { e.preventDefault(); O.mode = "image"; $$("#mode button").forEach((x) => x.classList.toggle("on", x.dataset.m === "image")); setImage(f); } });
  $("#og").onclick = (e) => busy(e.currentTarget, () => run());
  try { const q = await api("/interview/questions"); qs = q.questions; qi = 0; drawQ(q.role); } catch (e) { mount($("#iv"), html`<div class="muted sm">${e.message}</div>`); }
}

function drawInput(pre = {}) {
  const box = $("#inp");
  if (O.mode === "text") {
    mount(box, html`${O.job_id && !O.jd ? html`<div class="chip amber">Using the listing you selected${pre.company ? ": " + pre.company : ""}</div>` : ""}
      <textarea class="input" id="jd" placeholder="Paste the full job description here (title, company, requirements)…">${O.jd}</textarea>`);
    $("#jd").oninput = (e) => { O.jd = e.target.value; };
  } else if (!S.meta.vision_enabled) {
    mount(box, html`<div class="tile tint-amber sm" style="padding:12px">Screenshot reading needs the AI key on the server (<span class="mono">GROQ_API_KEY</span>). For now paste the job text instead.</div>`);
  } else {
    mount(box, html`<div class="drop" id="drop" tabindex="0" role="button">${icon("upload")}<b>Drop a job screenshot, click to browse, or press Ctrl+V</b><span class="sm muted">PNG, JPG or WEBP. It is resized in your browser before upload.</span><input type="file" id="img" accept="image/png,image/jpeg,image/webp" hidden></div>
      <div id="prev"></div>`);
    const d = $("#drop"), i = $("#img"); d.onclick = () => i.click(); d.onkeydown = (e) => (e.key === "Enter" || e.key === " ") && i.click();
    ["dragover", "dragenter"].forEach((t) => d.addEventListener(t, (e) => { e.preventDefault(); d.classList.add("over"); })); ["dragleave", "drop"].forEach((t) => d.addEventListener(t, (e) => { e.preventDefault(); d.classList.remove("over"); }));
    d.addEventListener("drop", (e) => e.dataTransfer.files[0] && setImage(e.dataTransfer.files[0])); i.onchange = () => i.files[0] && setImage(i.files[0]);
    if (O.image) showPrev();
  }
}
async function setImage(f) {
  if (!/^image\/(png|jpe?g|webp)$/.test(f.type)) return toast("Use a PNG, JPG or WEBP image", "err");
  if (!S.meta.vision_enabled) { drawInput(); return; }
  if (!$("#prev")) drawInput();
  O.image = await shrink(f); showPrev();
}
function showPrev() {
  if (!O.image || !$("#prev")) return; const url = URL.createObjectURL(O.image);
  mount($("#prev"), html`<div class="shot mt-s"><img src="${url}" alt="Job screenshot preview"><div class="grow sm muted">${Math.round(O.image.size / 1024)} KB ready</div><button class="btn sm ghost" id="rmimg">Remove</button></div>`);
  $("#rmimg").onclick = () => { O.image = null; $("#prev").innerHTML = ""; };
}

async function run(over = {}) {
  const fd = new FormData(); fd.append("kind", O.kind); fd.append("tone", O.tone);
  if (over.company) fd.append("company", over.company); if (over.role) fd.append("role", over.role);
  const text = over.jd_text ?? (O.mode === "text" ? $("#jd")?.value : "");
  if (text && text.trim()) fd.append("jd_text", text);
  else if (O.mode === "image" && O.image) fd.append("image", O.image, "job.jpg");
  else if (O.mode === "text" && O.job_id) fd.append("job_id", O.job_id);
  else return toast(O.mode === "image" ? "Add a screenshot first" : "Paste the job description first", "err");
  try { const r = await api("/outreach/analyze", { method: "POST", form: fd, timeout: 90000 }); O.last = r; draw(r); }
  catch (e) { if (e.data?.code === "no_resume") mount($("#oo"), html`<div class="tile tint-amber sm mt">${e.message} <a href="#/resume">Upload resume</a></div>`); else toast(e.message, "err"); }
}

function draw(r) {
  if (!$("#oo")) return;
  const j = r.job, f = r.fit;
  mount($("#oo"), html`<div class="jobcard mt"><div class="row wrap between"><div><div class="eyebrow" style="margin-bottom:6px">What we understood${r.source === "screenshot" ? " (read from screenshot)" : r.source === "listing" ? " (from listing)" : ""}</div>
      <div class="grid2" style="min-width:min(100%,380px)"><label class="f">Role<input class="input" id="er" value="${j.role}"></label><label class="f">Company<input class="input" id="ec" value="${j.company}" placeholder="Add company"></label></div></div>
      ${f.score != null ? html`<div style="text-align:center">${ring(f.score, 84, "Fit")}<div class="xs muted">resume fit</div></div>` : ""}</div>
    <div class="chips mt-s"><span class="chip ${j.kind === "internship" ? "violet" : j.kind === "freelance" ? "sky" : ""}">${cap(j.kind)}</span>${j.location ? html`<span class="chip">${j.location}</span>` : ""}${j.years ? html`<span class="chip">${j.years}+ yrs asked</span>` : ""}${j.contact_email ? html`<span class="chip mint">${j.contact_email}</span>` : ""}</div>
    <div class="chips mt-s">${f.matched.map((s) => html`<span class="chip mint" title="shown in your projects/experience">${s}</span>`)}${f.listed_only.map((s) => html`<span class="chip amber" title="listed but not shown in use">${s}</span>`)}${f.missing.map((s) => html`<span class="chip out" title="not on your resume">${s}</span>`)}</div></div>
    ${r.proof_points.length ? html`<div class="eyebrow mt">Resume proof used</div>${r.proof_points.map((p) => html`<div class="sm item" style="padding:6px 0"><span class="chip ${p.kind === "internship" ? "violet" : ""}">${p.kind}</span> ${p.text} <span class="muted">(${p.source})</span></div>`)}` : html`<div class="sm muted mt">No resume line overlaps this job's skills yet, so the message stays general.</div>`}
    <div class="eyebrow mt">${KIND[O.kind]} <span class="chip ${r.message.ai ? "mint" : ""}">${r.message.ai ? "AI written" : "template"}</span></div>
    <div class="msg">${r.message.subject ? html`<div class="sm"><b>Subject:</b> <span id="subj">${r.message.subject}</span></div><hr style="border:0;border-top:1px solid var(--line);margin:10px 0">` : ""}<textarea id="mbody" aria-label="Message">${r.message.body}</textarea></div>
    <div class="row wrap mt-s"><button class="btn sm" id="cpy">${icon("copy")} Copy</button>${j.contact_email ? html`<a class="btn sm" id="mail" href="#">${icon("mail")} Open in mail app</a>` : ""}<button class="btn sm" id="regen">Regenerate with edits</button></div>
    ${r.notes.map((n) => html`<div class="xs muted mt-s">• ${n}</div>`)}`);
  const body = () => $("#mbody").value;
  $("#cpy").onclick = () => navigator.clipboard.writeText((r.message.subject ? "Subject: " + r.message.subject + "\n\n" : "") + body()).then(() => toast("Copied"));
  if ($("#mail")) $("#mail").onclick = (e) => { e.preventDefault(); location.href = `mailto:${j.contact_email}?subject=${encodeURIComponent(r.message.subject)}&body=${encodeURIComponent(body())}`; };
  $("#regen").onclick = (e) => busy(e.currentTarget, () => run({ jd_text: r.jd_text, company: $("#ec").value.trim(), role: $("#er").value.trim() }));
}

function drawQ(role) {
  const q = qs[qi]; if (!q || !$("#iv")) return;
  mount($("#iv"), html`<div class="row between"><span class="chip violet">${q.category}</span><span class="xs faint">${qi + 1} / ${qs.length}</span></div><div style="font:600 18px var(--f-display);margin:10px 0">${q.question}</div>
    <textarea class="input" id="ans" placeholder="Answer as you would in the interview. Use real examples and numbers."></textarea>
    <div class="row mt-s"><button class="btn pri sm" id="ev">Get feedback</button><button class="btn sm" id="nx">Next question</button></div><div id="fb" class="mt"></div>`);
  $("#nx").onclick = () => { qi = (qi + 1) % qs.length; drawQ(role); };
  $("#ev").onclick = (e) => busy(e.currentTarget, async () => { try {
    const f = await api("/interview/evaluate", { method: "POST", json: { role, question: q.question, answer: $("#ans").value }, timeout: 60000 });
    const L = (t, a) => a?.length ? html`<div class="eyebrow mt-s">${t}</div><ul class="sm" style="margin:0;padding-left:18px">${a.map((x) => html`<li>${x}</li>`)}</ul>` : "";
    mount($("#fb"), html`<div class="row"><div class="big" style="font-size:40px">${f.score}<span class="faint" style="font-size:18px">/10</span></div><span class="chip ${f.ai ? "mint" : ""}">${f.ai ? "AI feedback" : "rubric check"}</span></div>${L("Strengths", f.strengths)}${L("Improve", f.improvements)}${L("Strong answer outline", f.model_answer_outline)}${f.follow_up ? html`<div class="sm mt-s"><b>Likely follow-up:</b> ${f.follow_up}</div>` : ""}`);
  } catch (er) { toast(er.message, "err"); } });
}
