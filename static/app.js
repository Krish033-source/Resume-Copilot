// ============================================================
// Resume Copilot — frontend logic
// ============================================================
const API = "/api";
let TOKEN = localStorage.getItem("rc_token") || null;
let LATEST_RESUME_ID = localStorage.getItem("rc_latest_resume_id") || null;
let LATEST_JOB_MATCHES = [];

function authHeaders() {
  return TOKEN ? { Authorization: "Bearer " + TOKEN } : {};
}

async function api(path, { method = "GET", body, isForm = false } = {}) {
  const opts = { method, headers: { ...authHeaders() } };
  if (body !== undefined) {
    if (isForm) {
      opts.body = body; // FormData sets its own headers
    } else {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
  }
  const res = await fetch(API + path, opts);
  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }
  if (!res.ok) {
    const msg = (data && data.error) || `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

// ---------------- Auth screen ----------------
const authScreen = document.getElementById("auth-screen");
const appShell = document.getElementById("app-shell");

document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    document.getElementById("login-form").classList.toggle("hidden", tab !== "login");
    document.getElementById("register-form").classList.toggle("hidden", tab !== "register");
  });
});

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("login-error");
  errorEl.textContent = "";
  try {
    const data = await api("/login", {
      method: "POST",
      body: {
        email: document.getElementById("login-email").value,
        password: document.getElementById("login-password").value,
      },
    });
    onAuthSuccess(data);
  } catch (err) {
    errorEl.textContent = err.message;
  }
});

document.getElementById("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("register-error");
  errorEl.textContent = "";
  try {
    const data = await api("/register", {
      method: "POST",
      body: {
        name: document.getElementById("reg-name").value,
        email: document.getElementById("reg-email").value,
        password: document.getElementById("reg-password").value,
        phone: document.getElementById("reg-phone").value,
        grad_year: document.getElementById("reg-gradyear").value,
        college: document.getElementById("reg-college").value,
        degree: document.getElementById("reg-degree").value,
      },
    });
    onAuthSuccess(data);
  } catch (err) {
    errorEl.textContent = err.message;
  }
});

function onAuthSuccess(data) {
  TOKEN = data.token;
  localStorage.setItem("rc_token", TOKEN);
  showApp();
}

document.getElementById("logout-btn").addEventListener("click", () => {
  TOKEN = null;
  localStorage.removeItem("rc_token");
  localStorage.removeItem("rc_latest_resume_id");
  authScreen.classList.remove("hidden");
  appShell.classList.add("hidden");
});

// ---------------- Navigation ----------------
document.querySelectorAll(".nav-btn[data-view]").forEach(btn => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

function switchView(view) {
  document.querySelectorAll(".nav-btn[data-view]").forEach(b => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + view));
  if (view === "dashboard") loadDashboard();
  if (view === "resume") loadResumeHistory();
  if (view === "tracker") loadApplications();
  if (view === "profile") loadProfile();
}

// ---------------- App bootstrap ----------------
async function showApp() {
  authScreen.classList.add("hidden");
  appShell.classList.remove("hidden");
  await loadDashboard();
}

if (TOKEN) {
  showApp().catch(() => {
    TOKEN = null;
    localStorage.removeItem("rc_token");
  });
}

// ============================================================
// DASHBOARD
// ============================================================
async function loadDashboard() {
  try {
    const d = await api("/dashboard");
    document.getElementById("dash-name").textContent = d.name || "there";
    document.getElementById("dash-ats-stamp").textContent = d.average_ats || "--";
    document.getElementById("dash-latest-ats").textContent = d.latest_ats_score ?? "--";
    document.getElementById("dash-apps").textContent = d.total_applications;
    document.getElementById("dash-saved").textContent = d.saved_jobs_count;

    const stages = ["Applied", "Viewed", "Shortlisted", "Interview", "Offer", "Rejected"];
    const pipelineEl = document.getElementById("dash-pipeline");
    pipelineEl.innerHTML = stages.map(s => `
      <div class="stage"><div class="n">${d.applications_by_status[s] || 0}</div><div class="l">${s}</div></div>
    `).join("");

    const topSkillsEl = document.getElementById("dash-top-skills");
    topSkillsEl.innerHTML = d.top_skills.length
      ? d.top_skills.map(s => `<span class="chip">${escapeHtml(s)}</span>`).join("")
      : "Upload a resume to see this.";
    topSkillsEl.classList.toggle("chip-row", d.top_skills.length > 0);

    const missingEl = document.getElementById("dash-missing-skills");
    missingEl.innerHTML = d.missing_skills.length
      ? d.missing_skills.map(s => `<span class="chip">${escapeHtml(s)}</span>`).join("")
      : "No target-role gaps detected yet.";

    const suggEl = document.getElementById("dash-suggestions");
    if (d.ai_suggestions.length) {
      suggEl.innerHTML = d.ai_suggestions.map(s => `<li>${escapeHtml(s)}</li>`).join("");
    } else {
      suggEl.innerHTML = "Upload a resume to get suggestions.";
    }
  } catch (err) {
    console.error(err);
  }
}

// ============================================================
// RESUME & ATS
// ============================================================
document.getElementById("upload-btn").addEventListener("click", async () => {
  const fileInput = document.getElementById("resume-file");
  const statusEl = document.getElementById("upload-status");
  if (!fileInput.files.length) {
    statusEl.textContent = "Please choose a PDF or DOCX file first.";
    return;
  }
  const fd = new FormData();
  fd.append("file", fileInput.files[0]);
  statusEl.textContent = "Analyzing... this can take a few seconds.";
  try {
    const data = await api("/resume/upload", { method: "POST", body: fd, isForm: true });
    LATEST_RESUME_ID = data.resume_id;
    localStorage.setItem("rc_latest_resume_id", LATEST_RESUME_ID);
    statusEl.textContent = "Done!";
    renderResumeResults(data.parsed, data.analysis);
    loadResumeHistory();
  } catch (err) {
    statusEl.textContent = "Error: " + err.message;
  }
});

function renderResumeResults(parsed, analysis) {
  document.getElementById("resume-results").classList.remove("hidden");
  document.getElementById("result-ats").textContent = analysis.ats_score;
  document.getElementById("result-summary").textContent = analysis.summary;
  document.getElementById("result-role").textContent = analysis.predicted_role;

  const breakdownLabels = {
    contact_info: ["Contact Info", 10],
    skills: ["Skills", 20],
    action_verbs: ["Action Verbs", 15],
    quantifiable_impact: ["Quantifiable Impact", 15],
    sections: ["Section Completeness", 20],
    length: ["Length", 10],
    readability: ["Readability", 10],
  };
  const bd = document.getElementById("result-breakdown");
  bd.innerHTML = Object.entries(analysis.breakdown).map(([k, v]) => {
    const [label, max] = breakdownLabels[k] || [k, v];
    const pct = Math.round((v / max) * 100);
    return `<div class="breakdown-item">
      <div class="label">${label}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      <div class="value">${v}/${max}</div>
    </div>`;
  }).join("");

  document.getElementById("result-strengths").innerHTML = analysis.strengths.map(s => `<li>${escapeHtml(s)}</li>`).join("");
  document.getElementById("result-suggestions").innerHTML = (analysis.suggestions.length ? analysis.suggestions : ["No major issues found!"]).map(s => `<li>${escapeHtml(s)}</li>`).join("");

  const kv = document.getElementById("result-parsed");
  const rows = [
    ["Name", parsed.name], ["Email", parsed.email], ["Phone", parsed.phone],
    ["LinkedIn", parsed.linkedin], ["GitHub", parsed.github],
    ["Skills detected", parsed.skills.length], ["Word count", parsed.word_count],
  ];
  kv.innerHTML = rows.map(([k, v]) => `<div class="kv"><span>${k}</span><span>${v || "—"}</span></div>`).join("");
}

document.getElementById("optimize-btn").addEventListener("click", async () => {
  if (!LATEST_RESUME_ID) { alert("Upload a resume first."); return; }
  const btn = document.getElementById("optimize-btn");
  btn.textContent = "Optimizing...";
  btn.disabled = true;
  try {
    const data = await api(`/resume/${LATEST_RESUME_ID}/optimize`, { method: "POST", body: {} });
    document.getElementById("optimize-results").classList.remove("hidden");
    document.getElementById("optimize-original").textContent = data.original_text;
    document.getElementById("optimize-new").textContent = data.optimized_text + "\n\n---\nNotes:\n" + data.notes.join("\n");
  } catch (err) {
    alert("Error: " + err.message);
  } finally {
    btn.textContent = "Optimize My Resume";
    btn.disabled = false;
  }
});

async function loadResumeHistory() {
  try {
    const rows = await api("/resume/history");
    const el = document.getElementById("resume-history");
    if (!rows.length) { el.innerHTML = "No resumes uploaded yet."; return; }
    el.innerHTML = rows.map(r => `
      <div class="history-row">
        <span>${escapeHtml(r.filename)} — ${new Date(r.created_at).toLocaleString()}</span>
        <span class="score">${r.ats_score}/100</span>
      </div>
    `).join("");
  } catch (err) { console.error(err); }
}

// ============================================================
// SKILL GAP & ROADMAP
// ============================================================
document.getElementById("analyze-gap-btn").addEventListener("click", async () => {
  if (!LATEST_RESUME_ID) { alert("Upload a resume first (Resume & ATS tab)."); return; }
  const role = document.getElementById("target-role-select").value;
  try {
    const data = await api(`/resume/${LATEST_RESUME_ID}/skill-gap`, { method: "POST", body: { target_role: role } });
    document.getElementById("gap-results").classList.remove("hidden");
    document.getElementById("gap-current").innerHTML = data.skill_gap.current_skills.map(s => `<span class="chip">${escapeHtml(s)}</span>`).join("") || "No skills detected yet.";
    document.getElementById("gap-missing").innerHTML = data.skill_gap.missing_skills.map(s => `<span class="chip">${escapeHtml(s)}</span>`).join("") || "No gaps — great fit!";

    const timelineEl = document.getElementById("roadmap-timeline");
    timelineEl.innerHTML = data.roadmap.map(w => `
      <div class="timeline-item">
        <div class="timeline-week">Week ${w.week}</div>
        <div class="timeline-body"><strong>${escapeHtml(w.focus)}</strong><span>${escapeHtml(w.goal)}</span></div>
      </div>
    `).join("");
  } catch (err) {
    alert("Error: " + err.message);
  }
});

// ============================================================
// JOB MATCHES
// ============================================================
document.getElementById("find-jobs-btn").addEventListener("click", async () => {
  if (!LATEST_RESUME_ID) { alert("Upload a resume first (Resume & ATS tab)."); return; }
  const listEl = document.getElementById("jobs-list");
  listEl.innerHTML = "Finding matches...";
  try {
    const jobs = await api("/jobs/recommend", { method: "POST", body: { resume_id: LATEST_RESUME_ID } });
    LATEST_JOB_MATCHES = jobs;
    renderJobs(jobs);
    populateOutreachSelect(jobs);
  } catch (err) {
    listEl.innerHTML = "Error: " + err.message;
  }
});

function renderJobs(jobs) {
  const listEl = document.getElementById("jobs-list");
  if (!jobs.length) { listEl.innerHTML = "No matches found."; return; }
  listEl.innerHTML = jobs.map((j, i) => `
    <div class="job-card">
      <div class="job-head">
        <div>
          <h3>${escapeHtml(j.title)}</h3>
          <div class="job-company">${escapeHtml(j.company)} · ${escapeHtml(j.location)}</div>
        </div>
        <div class="job-match">${j.match_score}% match</div>
      </div>
      <div class="job-meta">
        <span>💰 ${escapeHtml(j.salary)}</span>
        <span>🧭 ${escapeHtml(j.remote)}</span>
        <span>📈 ${escapeHtml(j.experience)}</span>
        ${j.rating ? `<span>⭐ ${j.rating}</span>` : ""}
      </div>
      <div class="chip-row">${j.matching_skills.map(s => `<span class="chip">${escapeHtml(s)}</span>`).join("")}</div>
      <div class="job-actions">
        <button class="btn-secondary" onclick="saveJob(${i}, this)">Save Job</button>
        <a href="${j.apply_link}" target="_blank" rel="noopener"><button class="btn-primary">Apply Link</button></a>
        <button class="btn-secondary" onclick="quickTrack(${i})">Track Application</button>
      </div>
    </div>
  `).join("");
}

async function saveJob(index, btn) {
  try {
    await api("/jobs/save", { method: "POST", body: LATEST_JOB_MATCHES[index] });
    btn.textContent = "Saved ✓";
    btn.disabled = true;
  } catch (err) { alert("Error: " + err.message); }
}

async function quickTrack(index) {
  const j = LATEST_JOB_MATCHES[index];
  try {
    await api("/applications", { method: "POST", body: { company: j.company, role: j.title, job_id: j.id } });
    alert(`Tracked application: ${j.title} at ${j.company}`);
  } catch (err) { alert("Error: " + err.message); }
}

function populateOutreachSelect(jobs) {
  const sel = document.getElementById("outreach-job-select");
  sel.innerHTML = jobs.map((j, i) => `<option value="${i}">${escapeHtml(j.title)} — ${escapeHtml(j.company)} (${j.match_score}%)</option>`).join("");
}

// ============================================================
// OUTREACH (cover letter / cold email)
// ============================================================
document.getElementById("gen-cover-btn").addEventListener("click", () => generateOutreach("cover"));
document.getElementById("gen-email-btn").addEventListener("click", () => generateOutreach("email"));

async function generateOutreach(kind) {
  if (!LATEST_RESUME_ID) { alert("Upload a resume first (Resume & ATS tab)."); return; }
  const idx = document.getElementById("outreach-job-select").value;
  if (idx === "" || idx === undefined || !LATEST_JOB_MATCHES.length) { alert("Find job matches first, then pick one."); return; }
  const job = LATEST_JOB_MATCHES[idx];
  const outputEl = document.getElementById("outreach-output");
  outputEl.textContent = "Generating...";
  try {
    const path = kind === "cover" ? "/coverletter" : "/coldemail";
    const data = await api(path, { method: "POST", body: { resume_id: LATEST_RESUME_ID, job } });
    outputEl.textContent = data.cover_letter || data.cold_email;
  } catch (err) {
    outputEl.textContent = "Error: " + err.message;
  }
}

// ============================================================
// APPLICATION TRACKER
// ============================================================
document.getElementById("add-app-btn").addEventListener("click", async () => {
  const company = document.getElementById("app-company").value.trim();
  const role = document.getElementById("app-role").value.trim();
  const notes = document.getElementById("app-notes").value.trim();
  if (!company || !role) { alert("Company and role are required."); return; }
  try {
    await api("/applications", { method: "POST", body: { company, role, notes } });
    document.getElementById("app-company").value = "";
    document.getElementById("app-role").value = "";
    document.getElementById("app-notes").value = "";
    loadApplications();
  } catch (err) { alert("Error: " + err.message); }
});

const STATUS_OPTIONS = ["Applied", "Viewed", "Shortlisted", "Interview", "Offer", "Rejected"];

async function loadApplications() {
  try {
    const rows = await api("/applications");
    const tbody = document.getElementById("app-table-body");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="muted-text">No applications tracked yet.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td>${escapeHtml(r.company)}</td>
        <td>${escapeHtml(r.role)}</td>
        <td>
          <select onchange="updateAppStatus(${r.id}, this.value)">
            ${STATUS_OPTIONS.map(s => `<option value="${s}" ${s === r.status ? "selected" : ""}>${s}</option>`).join("")}
          </select>
        </td>
        <td>${escapeHtml(r.notes || "")}</td>
        <td><button class="btn-secondary" onclick="deleteApp(${r.id})">Delete</button></td>
      </tr>
    `).join("");
  } catch (err) { console.error(err); }
}

async function updateAppStatus(id, status) {
  try { await api(`/applications/${id}`, { method: "PUT", body: { status } }); loadDashboard(); }
  catch (err) { alert("Error: " + err.message); }
}

async function deleteApp(id) {
  try { await api(`/applications/${id}`, { method: "DELETE" }); loadApplications(); loadDashboard(); }
  catch (err) { alert("Error: " + err.message); }
}

// ============================================================
// INTERVIEW PREP
// ============================================================
document.getElementById("get-questions-btn").addEventListener("click", async () => {
  const category = document.getElementById("interview-category").value;
  const difficulty = document.getElementById("interview-difficulty").value;
  try {
    const data = await api(`/interview/questions?category=${encodeURIComponent(category)}&difficulty=${encodeURIComponent(difficulty)}`);
    document.getElementById("interview-questions").innerHTML = data.questions.map(q => `<li>${escapeHtml(q)}</li>`).join("");
  } catch (err) { alert("Error: " + err.message); }
});

// ============================================================
// PROFILE
// ============================================================
async function loadProfile() {
  try {
    const p = await api("/profile");
    document.getElementById("prof-name").value = p.name || "";
    document.getElementById("prof-target-role").value = p.target_role || "AI Engineer";
    document.getElementById("prof-linkedin").value = p.linkedin || "";
    document.getElementById("prof-github").value = p.github || "";
    document.getElementById("prof-portfolio").value = p.portfolio || "";
    document.getElementById("prof-cgpa").value = p.cgpa || "";
    document.getElementById("prof-bio").value = p.bio || "";
  } catch (err) { console.error(err); }
}

document.getElementById("save-profile-btn").addEventListener("click", async () => {
  try {
    await api("/profile", {
      method: "PUT",
      body: {
        name: document.getElementById("prof-name").value,
        target_role: document.getElementById("prof-target-role").value,
        linkedin: document.getElementById("prof-linkedin").value,
        github: document.getElementById("prof-github").value,
        portfolio: document.getElementById("prof-portfolio").value,
        cgpa: document.getElementById("prof-cgpa").value,
        bio: document.getElementById("prof-bio").value,
      },
    });
    document.getElementById("profile-saved-msg").textContent = "Saved!";
    setTimeout(() => document.getElementById("profile-saved-msg").textContent = "", 2000);
    loadDashboard();
  } catch (err) { alert("Error: " + err.message); }
});

document.getElementById("theme-toggle-btn").addEventListener("click", () => {
  document.body.classList.toggle("light");
});

// ---------------- Utilities ----------------
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
