# Resume Copilot

An AI-assisted career toolkit: upload your resume, get an ATS score with a full breakdown, find skill gaps against a target role, follow a week-by-week roadmap, see matching jobs, generate a cover letter or cold email draft, practise interview questions, and track your applications, all in one lightweight app.

🔗 **Live demo:** https://resume-copilot-64eq.onrender.com/

> **Note on the demo:** it runs on a free Render instance, so the first load after a period of inactivity can take 30-60 seconds. The instance filesystem is not persistent, so accounts and uploaded resumes may be reset when the server restarts or redeploys.

Built from scratch with **Flask + vanilla JavaScript + SQLite**, kept to a small file count on purpose.

---

## Table of Contents

- [What it does](#what-it-does)
- [How the main parts work](#how-the-main-parts-work)
- [Implemented vs. planned](#implemented-vs-planned)
- [Project structure](#project-structure)
- [Setup](#setup)
- [Environment variables](#environment-variables)
- [Deployment (Render)](#deployment-render)
- [API overview](#api-overview)
- [Known limitations](#known-limitations)
- [Future scope](#future-scope)

---

## What it does

| Module | What is implemented |
|---|---|
| **Auth** | Register / login with JWT sessions and hashed passwords (Werkzeug) |
| **Profile** | Store bio, LinkedIn, GitHub, portfolio, CGPA and target role |
| **Resume parsing** | PDF and DOCX text extraction (`pdfplumber`, `python-docx`), then regex / keyword-based extraction of email, phone, LinkedIn, GitHub, skills and section presence. Upload limit is 8 MB |
| **ATS scoring** | A transparent, rule-based 100-point engine with a full breakdown and suggestions (see below) |
| **Resume optimizer** | Rule-based rewrite suggestions. If a Groq API key is configured, it rewrites the resume text with an LLM instead |
| **Skill gap and roadmap** | Compares your resume's skills with the required skills of 10 predefined roles and generates a week-by-week learning roadmap |
| **Job matching** | Live listings from the **Adzuna** API when keys are configured, scored against your resume's skills. Without keys, it falls back to a built-in sample set of 16 placeholder listings (their apply links are not real) |
| **Saved jobs** | Save and remove jobs |
| **Cover letter / cold email** | Generates an editable **draft** from your resume and the job details. Template-based by default, LLM-generated (Groq) when a key is set. Drafts are not sent from the app |
| **Application tracker** | Create, update and delete applications through a 6-stage pipeline: Applied, Viewed, Shortlisted, Interview, Offer, Rejected |
| **Interview prep** | Question bank across 5 categories (Technical, HR, Behavioral, Coding, System Design) and 3 difficulty levels (Easy, Medium, Hard) |
| **Dashboard** | Latest ATS score, ATS history, application and saved-job counts, top and missing skills, suggestions |

---

## How the main parts work

### ATS score (100 points, rule-based)

| Component | Points | How it is scored |
|---|---|---|
| Contact info | 10 | 5 for a detected email, 5 for a detected phone number |
| Skills | 20 | 2 points per matched skill keyword, capped at 20 |
| Action verbs | 15 | 2 points per distinct action verb found, capped at 15 |
| Quantified impact | 15 | 2 points per number / percentage / metric found, capped at 15 |
| Section completeness | 20 | 5 each for Education, Experience, Projects, Achievements |
| Length | 10 | Full marks for roughly 300-900 words, partial outside that range |
| Readability | 10 | Heuristic penalty for very long, run-on lines |

The app also predicts the closest role by comparing your skills with the role skill map. This is **not a machine-learning model**: scoring and extraction are deterministic rules and keyword matching, so every score can be explained from the breakdown.

### AI text generation (optional)

Resume rewriting, cover letters and cold emails use built-in rule-based templates by default and work with zero configuration. When `GROQ_API_KEY` is set, the app calls Groq's chat completions API for more natural text, and silently falls back to the templates if the call fails.

### Job matching

When `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` are set, the app fetches current listings from Adzuna and scores each against your resume's skills. If the keys are missing or the request fails, it falls back to the local sample dataset so the feature does not break.

---

## Implemented vs. planned

| Feature | Status |
|---|---|
| Auth, profile, resume upload and parsing | ✅ Implemented |
| Rule-based ATS scoring with breakdown | ✅ Implemented |
| Resume optimizer (rule-based + optional Groq) | ✅ Implemented |
| Skill gap analysis and weekly roadmap | ✅ Implemented |
| Live jobs via Adzuna (with local fallback) | ✅ Implemented |
| Cover letter and cold email drafts | ✅ Implemented |
| Application tracker | ✅ Implemented |
| Interview question bank | ✅ Implemented |
| Dashboard | ✅ Implemented |
| Internship listings from Unstop | 🔜 Planned, not implemented |
| Hackathon listings from Devpost | 🔜 Planned, not implemented |
| Sending emails from the app via SMTP, with send history | 🔜 Planned, not implemented |
| AI mock-interview chat | 🔜 Planned, not implemented |
| Admin panel | 🔜 Planned, not implemented |

---

## Project structure

```
Resume-Copilot/
├── app.py              # Entire backend: auth, resume parsing, ATS scoring,
│                       # skill gap, job matching, cover letters, tracker, etc.
├── templates/
│   └── index.html      # Single-page app shell (all screens)
├── static/
│   ├── style.css       # Styling
│   └── app.js          # All frontend logic and API calls
├── requirements.txt
├── Procfile            # gunicorn start command for deployment
├── .env.example        # Template for environment variables
├── .gitignore
└── README.md
```

The SQLite database and uploaded resumes are created automatically under `instance/` on first run (this folder is git-ignored).

---

## Setup

```bash
git clone https://github.com/Krish033-source/Resume-Copilot.git
cd Resume-Copilot
pip install -r requirements.txt
cp .env.example .env        # optional: needed only for Groq and Adzuna
python app.py
```

Open **http://localhost:5000**.

The first run creates `instance/resume_copilot.db` and `instance/uploads/` automatically. The app works without any API keys, using rule-based text generation and the local sample job dataset.

---

## Environment variables

| Variable | Required | Purpose | Default |
|---|---|---|---|
| `SECRET_KEY` | **Yes, for any real deployment** | Signs JWT login tokens | Insecure development value |
| `GROQ_API_KEY` | No | Enables LLM resume rewriting, cover letters and cold emails. Free key: https://console.groq.com/keys | Not set (templates are used) |
| `GROQ_MODEL` | No | Groq model name | `llama-3.1-8b-instant` |
| `ADZUNA_APP_ID` | No | Adzuna API app ID (https://developer.adzuna.com/) | Not set |
| `ADZUNA_APP_KEY` | No | Adzuna API app key | Not set |
| `ADZUNA_COUNTRY` | No | Country code for Adzuna (`in`, `gb`, `us`, `au`, ...) | `in` |
| `PORT` | No | Port to listen on | `5000` |
| `FLASK_DEBUG` | No | Debug mode when started with `python app.py` | `true` |

> ⚠️ **Always set a strong random `SECRET_KEY` before deploying.** With the default value, anyone could forge login tokens.

---

## Deployment (Render)

The repo ships with a `Procfile`:

```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

1. Create a new **Web Service** on Render and connect this repository.
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
4. Add environment variables: `SECRET_KEY` (required), and optionally `GROQ_API_KEY`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `ADZUNA_COUNTRY`.
5. Deploy.

Without the Adzuna keys, the deployed app shows only the 16 built-in sample listings.

---

## API overview

| Area | Endpoints |
|---|---|
| Auth and profile | `POST /api/register`, `POST /api/login`, `GET/PUT /api/profile` |
| Resume | `POST /api/resume/upload`, `GET /api/resume/history`, `GET/DELETE /api/resume/<id>`, `POST /api/resume/<id>/optimize`, `POST /api/resume/<id>/skill-gap` |
| Jobs | `POST /api/jobs/recommend`, `POST /api/jobs/save`, `DELETE /api/jobs/save/<job_id>`, `GET /api/jobs/saved` |
| Drafts | `POST /api/coverletter`, `POST /api/coldemail` |
| Applications | `GET/POST /api/applications`, `PUT/DELETE /api/applications/<id>` |
| Interview and roadmap | `GET /api/interview/questions`, `GET /api/roadmap/<role>` |
| Dashboard | `GET /api/dashboard` |

Protected endpoints require the JWT returned by `/api/login`.

---

## Known limitations

- **Rule-based, not ML.** Skill extraction, ATS scoring and role prediction rely on keyword lists and regex, so unusual resume formats or skills outside the keyword list may be missed.
- **Skill and role coverage is fixed.** Only 10 predefined target roles and a fixed skill keyword list are supported.
- **Live jobs need Adzuna keys.** Without them, only 16 placeholder sample listings are shown.
- **Drafts only.** Cover letters and cold emails are generated for you to copy; the app does not send email.
- **Ephemeral storage on free hosting.** SQLite and uploaded files live on the instance disk, which free Render instances do not persist across restarts.
- **No automated tests or CI yet.**
- **Single-file backend.** `app.py` holds all logic, which is convenient for a prototype but would be split into modules for a larger project.

---

## Future scope

Things that were planned but are **not yet implemented**:

- [ ] **Internship listings from Unstop** as an additional job source alongside Adzuna
- [ ] **Hackathon listings from Devpost**, matched against resume skills
- [ ] **Sending cover letters and cold emails via SMTP** (with the resume attached) and a **send-history log**
- [ ] **AI mock-interview chat loop** that asks follow-up questions and gives feedback
- [ ] **Admin panel** for managing users and viewing usage
- [ ] **Semantic skill and job matching** using embeddings or TF-IDF / scikit-learn instead of keyword overlap
- [ ] **Persistent database** (e.g. PostgreSQL) for hosted deployments
- [ ] **Automated tests and GitHub Actions CI**
- [ ] **Dockerfile** for one-command local and cloud deployment
- [ ] **Rate limiting** on login and upload endpoints
- [ ] Support for more target roles and an editable skill dictionary

---

## Notes

- Passwords are hashed with Werkzeug's `generate_password_hash`; plain-text passwords are never stored.
- Secrets live in `.env`, which is git-ignored. Never commit it.
- Running `python app.py` uses Flask's development server. For deployment, use the included `gunicorn` + `Procfile` setup.
