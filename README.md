# Resume Copilot v2

Evidence-based ATS resume analysis + live jobs, internships, freelance gigs and research papers matched to your resume.
Flask · PostgreSQL · Groq (optional) · vanilla JS Bento UI.

## What's inside

| Area | Details |
|---|---|
| **Auth** | PostgreSQL users, scrypt password hashes, httpOnly JWT cookies + CSRF double-submit, refresh tokens, rate limits, server-side password policy, change password, delete account |
| **ATS engine** | Deterministic, explainable 100-point score across 12 dimensions with stage-aware weights (fresher / early career / experienced). Every finding carries the **evidence line** from your resume and a concrete fix |
| **Real findings** | Internships (count, months), work experience (merged months, gaps), projects (stack/link/metric), certifications (vendor vs platform), open source (strong/moderate/weak), achievements (hackathons, ratings, ranks, papers), layout problems (columns, tables, text boxes, header/footer content, scanned PDFs, clickable links) |
| **Impact metrics** | Only real metrics count (%, users/requests, latency, cost, F1...). Years, phone numbers, CGPA are ignored |
| **JD match** | Paste a job description: required vs preferred skills, in-context vs listed-only, keywords, years of experience |
| **Groq AI** | Recruiter-style review, bullet rewrites (verified against your text), JD tailoring, outreach, interview feedback. Model chain with automatic fallback. The AI **never changes** the ATS score |
| **Opportunities** | Remotive, Arbeitnow, Remote OK, Jobicy, The Muse (no key) + Adzuna (key). Cached in Postgres, deduped, atomically rate-limited. Jobs / Internships / Freelance tabs |
| **Research** | arXiv + OpenAlex paper search with topics derived from your skills |
| **Explore** | Deep links for Internshala, Unstop, LinkedIn, Naukri, Devpost, MLH, Upwork, GSoC, Outreachy ... (no scraping) |
| **Dashboard** | Bento grid: ATS ring, trend, breakdown, role radar, pipeline funnel, weekly applications, market-demand skills, matches, roadmap, activity heatmap |
| **Tracker** | Drag-and-drop kanban with status history that feeds the analytics |

## Quick start

```bash
cp .env.example .env            # set SECRET_KEY and DATABASE_URL
python -m venv venv && . venv/bin/activate
pip install -r requirements-dev.txt
python -m flask --app wsgi db upgrade        # create tables in PostgreSQL
python -m flask --app wsgi run               # http://127.0.0.1:5000
```

Docker: `SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(48))") docker compose up --build` then open http://localhost:8000.

Free Postgres options: Neon, Supabase, or Render Postgres (check Render's current free-tier expiry policy; Neon/Supabase are better for long-lived free use).

## Deploy on Render

1. Create a PostgreSQL database (Neon/Supabase/Render) and copy its URL.
2. New Web Service from this repo (`render.yaml` is included). Set `DATABASE_URL`, optionally `GROQ_API_KEY`, `ADZUNA_*`, `CONTACT_EMAIL`.
3. `start.sh` runs `flask db upgrade` on every boot, then gunicorn.

Optional cron to keep listings fresh: `python -m flask --app wsgi refresh-jobs`.

## Configuration

See `.env.example`. Key variables: `SECRET_KEY` (required in production, 32+ chars), `DATABASE_URL`, `GROQ_API_KEY`, `GROQ_MODEL` (default `openai/gpt-oss-120b`, fallbacks `llama-3.3-70b-versatile,openai/gpt-oss-20b`), `ADZUNA_APP_ID/KEY`, `RATELIMIT_STORAGE_URI`.
Groq changes its model lineup often; if a model is retired the app falls through the chain automatically, and you can change `GROQ_MODEL` without code changes.

## How the ATS score works

Weights (sum = 100) depend on the detected stage (based on merged work months, internships at half weight, and graduation year):

| Dimension | Fresher | Early | Experienced |
|---|---|---|---|
| ATS readability (text layer, columns, tables, text boxes, header/footer, pages, length) | 10 | 10 | 10 |
| Contact & links | 6 | 6 | 6 |
| Structure & dates | 8 | 8 | 8 |
| Experience & internships | 14 | 24 | 30 |
| Projects | 14 | 8 | 4 |
| Role keyword match (credit: 1.0 shown in a bullet, 0.6 listed only) | 16 | 16 | 16 |
| Measurable impact (share of bullets with a real metric) | 8 | 10 | 12 |
| Bullet writing (action verbs, weak phrases, length, specificity) | 8 | 8 | 8 |
| Education | 6 | 4 | 2 |
| Certifications (vendor 1.0, platform 0.7, unknown 0.5) | 4 | 3 | 2 |
| Open source | 4 | 2 | 1 |
| Achievements | 2 | 1 | 1 |

Knock-out caps mirror real ATS behaviour: unreadable text caps at 35, no email at 60, no recognisable headings at 50.
Role profiles (core / important / nice skills per role) live in `app/services/skills.py` and are easy to edit.

## Job sources and terms

- **Remotive** limits fetching (about 4 fetches/day, delayed data), requires attribution and forbids re-posting. The app caches in Postgres, refreshes at most every 8h and shows attribution in the UI.
- **Remote OK** requires attribution/link-back. **Arbeitnow, Jobicy, The Muse** are public feeds. **Adzuna** needs a free key.
- **Internshala, Unstop, Devpost, Upwork, Fiverr**: no public API that is generally available, so the app only builds search links (no scraping). Upwork/Fiverr APIs are partner-only.
- Always re-read each provider's terms before launching commercially.

## Tests

```bash
pytest -q                                                   # SQLite
TEST_DATABASE_URL=postgresql+psycopg://user:pw@localhost/rc_test pytest -q   # PostgreSQL
```
25 tests cover ATS logic, real PDF/DOCX layout detection, auth + CSRF, isolation between users, upserts/dedupe, rate-limit claiming, source failure handling and the Groq client (mocked).

## Not verifiable in the build sandbox

External APIs (job boards, arXiv, OpenAlex, Groq) and CDN assets were not reachable from the build environment, so live responses are covered by mocks and defensive parsing; run `python -m flask --app wsgi refresh-jobs` once after deploying and check `/api/sources/status`.

## Layout

```
app/                Flask package (blueprints/, services/, sources/, static/, templates/)
migrations/         Alembic migrations (PostgreSQL JSONB, lower(email) unique index)
tests/              pytest suite + fixture resumes
start.sh            migrate + gunicorn (1 worker, 8 threads; see comments for scaling)
```
