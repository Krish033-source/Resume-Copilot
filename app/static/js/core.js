// ---------- safe templating: every interpolation is escaped unless wrapped in raw()/html``
export class Raw { constructor(s) { this.s = s; } toString() { return this.s; } }
export const raw = (s) => new Raw(String(s ?? ""));
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const render = (v) => v == null || v === false ? "" : v instanceof Raw ? v.s : Array.isArray(v) ? v.map(render).join("") : esc(v);
export const html = (strings, ...vals) => new Raw(strings.reduce((o, s, i) => o + s + (i < vals.length ? render(vals[i]) : ""), ""));
export const mount = (el, tpl) => { if (!el) return null; el.innerHTML = tpl instanceof Raw ? tpl.s : esc(tpl); return el; };  // tolerant: page may have changed while a request was in flight
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const safeUrl = (u) => /^https?:\/\//i.test(u || "") ? u : "#";

// ---------- icons
const P = {
  home: "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10", file: "M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8zM14 3v5h5M9 13h6M9 17h6",
  brief: "M3 8h18v12H3zM8 8V5h8v3M3 13h18", board: "M4 4h6v16H4zM14 4h6v9h-6z", target: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 16a4 4 0 100-8 4 4 0 000 8zM12 12h.01",
  spark: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z", user: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0",
  upload: "M12 16V4M7 9l5-5 5 5M4 20h16", search: "M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4", bookmark: "M6 3h12v18l-6-4-6 4z", ext: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3", plus: "M12 5v14M5 12h14", sun: "M12 16a4 4 0 100-8 4 4 0 000 8zM12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5",
  moon: "M20 14a8 8 0 11-10-10 6 6 0 0010 10z", out: "M9 4H5v16h4M16 8l4 4-4 4M20 12H9", check: "M5 12l5 5 9-10", alert: "M12 4l9 16H3zM12 10v4M12 17h.01",
  x: "M6 6l12 12M18 6L6 18", book: "M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2zM4 19a2 2 0 012-2h13", mail: "M3 6h18v12H3zM3 7l9 7 9-7", copy: "M9 9h11v11H9zM5 15V5h10",
};
export const icon = (n) => raw(`<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="${P[n] || ""}"/></svg>`);

// ---------- api
export class ApiError extends Error { constructor(m, status, data) { super(m); this.status = status; this.data = data || {}; } }
const cookie = (n) => (document.cookie.split("; ").find((c) => c.startsWith(n + "=")) || "").split("=").slice(1).join("=");
let refreshing = null;
async function refresh() {
  refreshing ||= fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-TOKEN": cookie("csrf_refresh_token") } })
    .then((r) => r.ok).finally(() => { setTimeout(() => (refreshing = null), 0); });
  return refreshing;
}
export async function api(path, { method = "GET", json, form, retry = true, timeout = 30000 } = {}) {
  const headers = {}; let body;
  if (method !== "GET") headers["X-CSRF-TOKEN"] = cookie("csrf_access_token");
  if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); } else if (form) body = form;
  let r, data;
  const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), timeout);
  try { r = await fetch("/api" + path, { method, headers, body, credentials: "same-origin", signal: ctl.signal }); data = await r.json().catch(() => ({})); }
  catch (e) { throw new ApiError(e.name === "AbortError" ? "This is taking too long. Please try again." : "Network error. Check your connection.", 0); }
  finally { clearTimeout(timer); }
  if (r.status === 401 && retry && (data.code === "token_expired" || data.code === "csrf") && !path.startsWith("/auth/")) {
    if (await refresh()) return api(path, { method, json, form, retry: false, timeout });
  }
  if (r.status === 401 && !path.startsWith("/auth/")) window.dispatchEvent(new Event("rc:logout"));
  if (!r.ok) throw new ApiError(data.error || "Request failed", r.status, data);
  return data;
}

// ---------- ui helpers
export function toast(msg, kind = "ok") {
  const t = document.createElement("div"); t.className = "toast " + (kind === "err" ? "err" : ""); t.textContent = msg;
  $("#toasts").append(t); setTimeout(() => t.remove(), 4200);
}
export const busy = async (btn, fn) => { const t = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>'; try { return await fn(); } finally { btn.disabled = false; btn.innerHTML = t; } };
export const ago = (iso) => { if (!iso) return ""; const d = (Date.now() - new Date(iso)) / 864e5; return d < 1 ? "today" : d < 2 ? "yesterday" : d < 30 ? Math.floor(d) + "d ago" : d < 365 ? Math.floor(d / 30) + "mo ago" : Math.floor(d / 365) + "y ago"; };
export const scoreColor = (s) => s >= 75 ? "var(--mint)" : s >= 55 ? "var(--amber)" : "var(--coral)";
export const initials = (n) => (n || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
export const cap = (s) => (s || "").charAt(0).toUpperCase() + (s || "").slice(1);
export function ring(score, size = 150, label = "ATS") {
  const r = size / 2 - 11, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, score ?? 0));
  return html`<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="${label} ${v} out of 100">
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--bg2)" stroke-width="11"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${scoreColor(v)}" stroke-width="11" stroke-linecap="round"
      stroke-dasharray="${(c * v / 100).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 ${size / 2} ${size / 2})"/>
    <text x="50%" y="50%" text-anchor="middle" dominant-baseline="central" fill="var(--text)" font-family="var(--f-display)" font-weight="700" font-size="${size * 0.3}">${v}</text></svg>`;
}
export const miniRing = (s) => ring(s, 54, "Match");
export function dialog(content) {
  const d = document.createElement("dialog"); d.innerHTML = '<div class="dlg"></div>'; $(".dlg", d).innerHTML = content instanceof Raw ? content.s : esc(content);
  document.body.append(d); d.addEventListener("close", () => d.remove()); d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
  d.showModal(); return d;
}
export const sevLabel = { critical: "Critical", warning: "Fix", info: "Tip", good: "Good" };

// ---------- charts
const charts = new Map();
export function chart(id, cfg) {
  const el = document.getElementById(id); if (!el || !window.Chart) return;
  charts.get(id)?.destroy();
  const css = getComputedStyle(document.documentElement), col = (v) => css.getPropertyValue(v).trim();
  Chart.defaults.color = col("--muted"); Chart.defaults.font.family = "DM Sans"; Chart.defaults.borderColor = col("--line");
  cfg.options = { responsive: true, maintainAspectRatio: false, ...cfg.options };
  charts.set(id, new Chart(el, cfg));
}
export const cssv = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
export const clearCharts = () => { charts.forEach((c) => c.destroy()); charts.clear(); };
