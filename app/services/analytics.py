"""Analytics for the dashboard (all computed from real user data)."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from ..extensions import db
from ..models import APP_STATUSES, Application, ApplicationEvent, Job, Resume, SavedJob
from .skills import CATEGORY_LABELS, skill_category

PROJECT_IDEAS = {
    "lang": "Solve 30 problems and publish a small CLI/tool in it", "frontend": "Rebuild a real site as a responsive, accessible UI and deploy it",
    "backend": "Build an authenticated REST API with tests and rate limiting", "data": "Design a schema with indexes for a real dataset and benchmark queries",
    "cloud": "Containerise one of your projects and deploy it with a CI pipeline", "ml": "Train, evaluate and serve a model; document metrics in the README",
    "bi": "Build a dashboard answering 5 business questions on a public dataset", "dataeng": "Build an ETL pipeline that loads a public API into a warehouse daily",
    "mobile": "Ship a small app with offline storage and one external API", "security": "Complete a CTF track and write up 3 findings",
    "testing": "Automate tests for a public web app and wire them into CI", "design": "Redesign one real app flow and document research decisions",
    "cs": "Implement the structure from scratch and benchmark it", "chain": "Write and test a small contract on a testnet", "research": "Reproduce one paper's results and write a short report",
}


def _now():
    return datetime.now(timezone.utc)


def roadmap(role_report: dict, limit: int = 8) -> list[dict]:
    items = [r for r in role_report["rows"] if r["status"] != "context"]
    items.sort(key=lambda r: (-r["weight"], r["status"] != "missing"))
    out = []
    for r in items[:limit]:
        cat = r["category"]
        out.append({"skill": r["skill"], "priority": {3: "core", 2: "important", 1: "nice"}[r["weight"]], "status": r["status"],
                    "category": CATEGORY_LABELS.get(cat, cat), "weeks": 2 if r["weight"] == 3 else 1,
                    "action": ("Show it in a project bullet" if r["status"] == "listed" else "Learn the basics, then build: ") + ("" if r["status"] == "listed" else PROJECT_IDEAS.get(cat, "Build one small project with it"))})
    return out


def overview(user, latest: Resume | None, role_report: dict | None) -> dict:
    now = _now()
    resumes = db.session.execute(select(Resume.id, Resume.filename, Resume.ats_score, Resume.created_at, Resume.target_role)
                                 .where(Resume.user_id == user.id).order_by(Resume.created_at)).all()
    trend = [{"id": r.id, "label": r.created_at.strftime("%d %b"), "score": r.ats_score, "filename": r.filename} for r in resumes][-12:]
    delta = (trend[-1]["score"] - trend[-2]["score"]) if len(trend) >= 2 else None

    apps = db.session.execute(select(Application).where(Application.user_id == user.id)).scalars().all()
    by_status = Counter(a.status for a in apps)
    funnel = [{"status": s, "count": by_status.get(s, 0)} for s in APP_STATUSES]
    applied_like = sum(1 for a in apps if a.status != "saved")
    reached = sum(1 for a in apps if a.status in ("oa", "interview", "offer"))
    response_rate = round(100 * reached / applied_like) if applied_like else None
    kind_split = Counter(a.kind for a in apps)

    # weekly applications (12 weeks) and heatmap (26 weeks) from events
    events = db.session.execute(select(ApplicationEvent.at, ApplicationEvent.to_status).join(Application)
                                .where(Application.user_id == user.id, ApplicationEvent.at >= now - timedelta(days=26 * 7))).all()
    day_counts = Counter(e.at.date().isoformat() for e in events)
    monday = (now.date() - timedelta(days=now.weekday()))
    weekly = []
    for i in range(11, -1, -1):
        ws = monday - timedelta(weeks=i)
        n = sum(1 for e in events if ws <= e.at.date() < ws + timedelta(days=7) and e.to_status == "applied")
        weekly.append({"label": ws.strftime("%d %b"), "count": n})
    heat = []
    start = monday - timedelta(weeks=25)
    for d in range(26 * 7):
        day = start + timedelta(days=d)
        heat.append({"date": day.isoformat(), "count": day_counts.get(day.isoformat(), 0)})
    # average days from applied -> first response
    gaps = []
    for a in apps:
        ap = next((e.at for e in a.events if e.to_status == "applied"), None)
        resp = next((e.at for e in a.events if e.to_status in ("oa", "interview", "offer", "rejected") and ap and e.at > ap), None)
        if ap and resp:
            gaps.append((resp - ap).total_seconds() / 86400)
    # streak: consecutive active days ending today (or yesterday)
    streak, d = 0, now.date()
    if not day_counts.get(d.isoformat()):
        d -= timedelta(days=1)
    while day_counts.get(d.isoformat()):
        streak += 1
        d -= timedelta(days=1)

    # market demand from cached jobs (last 30 days) vs resume
    since = now - timedelta(days=30)
    jobs = db.session.execute(select(Job.skills, Job.kind).where((Job.posted_at >= since) | (Job.posted_at.is_(None)))).all()
    dem = Counter()
    for sk, _k in jobs:
        for s in set(sk or []):
            dem[s] += 1
    have = set((latest.parsed or {}).get("skills", {}).get("all", {})) if latest else set()
    market = [{"skill": s, "jobs": n, "have": s in have, "category": CATEGORY_LABELS.get(skill_category(s), "")} for s, n in dem.most_common(10)]
    kinds = Counter(k for _s, k in jobs)

    saved = db.session.query(SavedJob).filter_by(user_id=user.id).count()
    analysis = (latest.analysis or {}) if latest else {}
    return {
        "ats": {"score": latest.ats_score if latest else None, "grade": analysis.get("grade"), "stage": analysis.get("stage_label"),
                "delta": delta, "trend": trend, "components": [{"key": k, **v} for k, v in (analysis.get("components") or {}).items()],
                "role": analysis.get("role"), "quick_wins": analysis.get("quick_wins", [])},
        "skills": {"categories": (role_report or {}).get("categories", {}), "coverage": (role_report or {}).get("coverage"),
                   "roadmap": roadmap(role_report) if role_report else []},
        "pipeline": {"total": len(apps), "funnel": funnel, "response_rate": response_rate, "avg_days_to_response": round(sum(gaps) / len(gaps), 1) if gaps else None,
                     "kinds": dict(kind_split), "weekly": weekly, "heatmap": heat, "streak": streak, "saved_jobs": saved},
        "market": {"top_skills": market, "jobs_in_db": len(jobs), "kinds": dict(kinds)},
        "profile": {"stage": analysis.get("stage_label"), **(analysis.get("summary") or {})},
    }
