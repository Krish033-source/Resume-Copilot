import { $, api, html, mount, toast, busy } from "./core.js";
import { S } from "./state.js";

export async function profile(v) {
  const u = S.user;
  const fld = (k, l, type = "text") => html`<label class="f">${l}<input class="input" type="${type}" name="${k}" value="${u[k] ?? ""}"></label>`;
  mount(v, html`<div class="pagehead"><div><h1>Profile</h1><p>Used to personalise matches, outreach and links.</p></div></div>
  <div class="bento"><section class="tile c7"><div class="eyebrow">Your details</div><form id="pf" class="stack"><div class="row wrap"><div class="grow">${fld("name", "Name")}</div><label class="f grow">Target role<select class="input" name="target_role">${S.meta.roles.map((r) => html`<option ${r === u.target_role ? "selected" : ""}>${r}</option>`)}</select></label></div>
    <div class="row wrap"><div class="grow">${fld("college", "College / employer")}</div><div class="grow">${fld("degree", "Degree")}</div></div>
    <div class="row wrap"><div class="grow">${fld("grad_year", "Graduation year", "number")}</div><div class="grow">${fld("location", "Location")}</div><div class="grow">${fld("phone", "Phone")}</div></div>
    ${fld("linkedin", "LinkedIn URL")}${fld("github", "GitHub URL")}${fld("portfolio", "Portfolio URL")}<div class="row"><button class="btn pri">Save profile</button></div></form></section>
  <section class="tile c5"><div class="eyebrow">Account</div><div class="sm muted">Email</div><div style="font-weight:600">${u.email}</div>
    <form id="pw" class="stack mt"><label class="f">Current password<input class="input" type="password" name="current_password" autocomplete="current-password" required></label>
      <label class="f">New password<input class="input" type="password" name="new_password" autocomplete="new-password" required></label><button class="btn">Change password</button></form>
    <div class="eyebrow mt" style="color:var(--coral)">Danger zone</div><div class="sm muted">Deletes your account, resumes and tracker permanently.</div><button class="btn danger mt-s" id="del">Delete account</button></section></div>`);
  $("#pf").onsubmit = (e) => { e.preventDefault(); busy($("#pf .pri"), async () => { try { S.user = (await api("/profile", { method: "PUT", json: Object.fromEntries(new FormData(e.target)) })).user; toast("Profile saved"); } catch (er) { toast(er.message, "err"); } }); };
  $("#pw").onsubmit = async (e) => { e.preventDefault(); try { await api("/auth/change-password", { method: "POST", json: Object.fromEntries(new FormData(e.target)) }); e.target.reset(); toast("Password updated"); } catch (er) { toast(er.message, "err"); } };
  $("#del").onclick = async () => { const pw = prompt("Type your password to permanently delete your account:"); if (!pw) return; try { await api("/auth/account", { method: "DELETE", json: { password: pw } }); location.reload(); } catch (er) { toast(er.message, "err"); } };
}
