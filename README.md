# Resume Copilot

An AI-powered career assistant: upload your resume, get a real ATS score and
breakdown, find skill gaps against a target role, get a week-by-week roadmap,
see matching jobs, generate a cover letter / cold email, and track your
applications — all in one lightweight app.

🔗 **Live demo:**https://resume-copilot-64eq.onrender.com/

This is a working, from-scratch full-stack build (Flask + vanilla JS +
SQLite), kept to a **minimal file count** on purpose:

```
resume-copilot/
├── app.py              # Entire backend: auth, resume parsing, ATS scoring,
│                        # skill gap, job matching, cover letters, tracker, etc.
├── templates/
│   └── index.html      # Single-page app shell (all screens)
├── static/
│   ├── style.css       # Design system
│   └── app.js          # All frontend logic / API calls
├── requirements.txt
├── .env.example
└── README.md
```

No separate database file, ORM layer, or job-scraper needed — the app is
self-contained and runs with just Python + SQLite (built into Python).

## What's real vs. what's scoped down

Your brief described a ~140-feature platform (SMTP email sending, live
scraping from LinkedIn/Internshala/etc., a mock-interview AI, an admin panel,
semantic embeddings). Building all of that "properly" isn't realistic in one
pass — a lot of it needs paid APIs, scraping infrastructure that violates
most sites' terms, or is genuinely a multi-week engineering project.

Instead, this build covers the **real, working core** of every major module,
with no smoke and mirrors:

| Module | What's implemented |
|---|---|
| Auth | Register/login, JWT sessions, password hashing |
| Resume parsing | Real PDF/DOCX text extraction (pdfplumber, python-docx), regex-based extraction of contact info, skills, sections |
| ATS scoring | Transparent, rule-based 100-point scoring engine (contact info, skills, action verbs, quantified impact, sections, length, readability) — with a full breakdown and suggestions |
| Resume optimizer | Rule-based rewrite suggestions; auto-upgrades to AI rewriting if you add a Groq API key |
| Skill gap & roadmap | Compares your resume's skills against 10 predefined target roles, generates a week-by-week learning roadmap |
| **Job / internship / hackathon matching** | **Real, live results** merged from three sources: **Adzuna** (jobs, official API), **Unstop** (internships, public endpoint), **Devpost** (hackathons, public API) — each scored against your resume's skills. Falls back to a small local sample dataset only if none of the live sources return anything |
| Cover letter / cold email | Template-based generation using your resume + job data; auto-upgrades to AI generation if a Groq key is set. Fully editable draft before anything is sent |
| **Real email sending** | Actually sends your cover letter/cold email via your own SMTP account (e.g. Gmail), with your uploaded resume attached, to a recipient email you provide. Every send is logged in a history table |
| Application tracker | Full CRUD with pipeline status (Applied → Viewed → Shortlisted → Interview → Offer / Rejected) |
| Interview prep | Question bank across 5 categories × 3 difficulty levels |
| Dashboard | Live stats: average ATS, applications, saved jobs, top/missing skills, AI suggestions |

Left out of this pass: an admin panel, and a live "AI mock interview" chat loop. Addable later without a rewrite.

## Setup

```bash
cd resume-copilot
pip install -r requirements.txt
cp .env.example .env       # needed for live jobs + real email sending, see below
python app.py
```

Open **http://localhost:5000** in your browser.

The first run creates `instance/resume_copilot.db` (SQLite) and
`instance/uploads/` automatically — nothing else to configure to get the app
running with sample data.

## Optional: enable AI-generated text (Groq)

By default, resume rewrites / cover letters / cold emails use solid
rule-based templates and work with zero configuration. If you want more
natural, LLM-generated text instead:

1. Get a free key at https://console.groq.com/keys
2. Put it in `.env`:
   ```
   GROQ_API_KEY=your-key-here
   ```
3. Restart the app. It'll automatically use Groq wherever relevant and fall
   back to the built-in templates if the API call ever fails.

## Real job / internship / hackathon sources

**Adzuna (jobs)** — official, free, key-based API.
1. Register at https://developer.adzuna.com/ → dashboard gives you an App ID + App Key.
2. Add to `.env`:
   ```
   ADZUNA_APP_ID=your_app_id
   ADZUNA_APP_KEY=your_app_key
   ADZUNA_COUNTRY=in
   ```
   (Use `gb`, `us`, `au`, etc. for other countries.)

**Unstop (internships)** and **Devpost (hackathons)** — both are called
automatically, no keys needed. Devpost's public API
(`devpost.com/api/hackathons`) is stable and verified working. Unstop's
endpoint is the same public JSON endpoint their own site calls — there's no
official partner agreement backing it, so treat it as best-effort: if Unstop
ever changes its response shape or starts blocking automated requests, that
source quietly returns nothing rather than breaking the app (whatever other
sources are up still show).

If none of the live sources return anything (no internet, or Adzuna keys
missing and Unstop/Devpost both happen to be unreachable), job matching
falls back to a small built-in sample dataset so the feature never just
breaks.

**What I deliberately did NOT wire in:**
- **Indeed** — they shut down their public job-search API years ago (what
  remains today is only for employers posting jobs, not for searching
  listings). No legitimate free option exists here anymore.
- **foundit.in** — their `robots.txt` explicitly disallows automated access
  to the search endpoint. Respecting that.
- **LinkedIn / raw HTML scraping of any site** — breaks terms of service,
  not something this project does.

## Real email sending

By default, "Send Email" in the app will tell you it isn't configured. To
actually send cover letters / cold emails (with your resume attached):

1. Add to `.env`:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your.email@gmail.com
   SMTP_PASSWORD=your-16-character-app-password
   SMTP_FROM_NAME=Your Name
   ```
2. For Gmail: turn on 2-Step Verification, then generate an **App Password**
   at https://myaccount.google.com/apppasswords — use that, not your normal
   Gmail password. Other providers (Outlook, Yahoo, a custom domain) work
   the same way with their own SMTP host/port.
3. Restart the app.

Important: none of the job/internship/hackathon APIs publish recruiter email
addresses (true of virtually every job platform — applications get routed
through their own portal to prevent spam). So there's no "auto-discover the
recruiter's email" step. You type in a recipient email you already have
(company site, LinkedIn, a referral, etc.), review the generated draft —
it's fully editable in a text box — and only then hit Send. Nothing goes out
automatically or in bulk.

## Notes

- Passwords are hashed with Werkzeug's `generate_password_hash` (never stored
  in plain text).
- `SECRET_KEY` in `.env` signs login sessions — change it before deploying
  anywhere real.
- This uses Flask's built-in dev server for local use. For real deployment,
  it now ships with `gunicorn` + a `Procfile` — see below.

## Deploying it for real

### Step 1 — Push to GitHub (without your secrets)

A `.gitignore` is already included — it excludes `.env` and `instance/`
(your database + uploaded resumes) automatically, so as long as you don't
force-add them, your secrets never reach GitHub.

```bash
cd resume-copilot
git init
git add .
git commit -m "Resume Copilot"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/resume-copilot.git
git push -u origin main
```

Double-check before pushing: run `git status` — you should **not** see
`.env` listed. If you ever do commit it by accident, treat every key inside
it as compromised: rotate the Groq/Adzuna keys and change your Gmail app
password immediately, then remove it from git history (`git rm --cached .env`
+ commit, or use `git filter-repo` if it's already pushed).

### Step 2 — Deploy (Render — easiest free option)

1. Go to https://render.com → sign up (can use your GitHub account directly).
2. **New → Web Service** → connect your `resume-copilot` GitHub repo.
3. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
     (Render auto-detects this from the included `Procfile` too, so this step
     is often filled in for you.)
   - **Instance type:** Free is fine to start.
4. **Environment** tab → add each variable from your `.env` **one by one**
   here (never upload the `.env` file itself — Render's dashboard is where
   secrets belong in production):
   ```
   SECRET_KEY=<a long random string>
   GROQ_API_KEY=...
   ADZUNA_APP_ID=...
   ADZUNA_APP_KEY=...
   ADZUNA_COUNTRY=in
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=...
   SMTP_PASSWORD=...
   SMTP_FROM_NAME=...
   ```
5. Click **Create Web Service**. First deploy takes a couple of minutes.
   You'll get a live URL like `https://resume-copilot.onrender.com`.

**Other free/cheap options that work the same way** (GitHub-connected,
env vars in a dashboard, `Procfile` + `requirements.txt` auto-detected):
Railway (railway.app), Fly.io, PythonAnywhere. Render is the simplest to
start with.

### Important: SQLite + uploaded files on free tiers

This app stores its database (`instance/resume_copilot.db`) and uploaded
resumes (`instance/uploads/`) as local files. On most free hosting tiers,
the filesystem is **ephemeral** — it resets on every redeploy or restart,
so accumulated user data can get wiped. Fine for a demo/portfolio link;
**not fine for a real product with real users.** If you outgrow this:
- Add a persistent disk (Render/Railway both offer this on paid plans), or
- Migrate to a hosted Postgres database (Render/Railway both offer a free
  Postgres instance) — this is a moderate refactor (swap `sqlite3` calls for
  `psycopg2`/`SQLAlchemy`), happy to do that pass when you're ready for it.

### Step 3 — Put the live link on GitHub

Once deployed, add the URL to the top of your GitHub repo's README (or as
the repo's "Website" field in GitHub's sidebar — the gear icon next to
**About**) so it shows up right under the repo name:

```markdown
```

One more thing on Render's free tier specifically: the service **sleeps
after inactivity** and takes ~30-50 seconds to wake up on the next visit —
normal for free tiers, not a bug. Mention that in your README/portfolio
blurb so it doesn't look broken to whoever clicks the link first.

