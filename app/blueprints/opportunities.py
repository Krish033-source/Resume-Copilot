from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import or_

from ..extensions import db
from ..models import Job, SavedJob
from ..services.matching import match_job, resume_profile
from ..services.skills import ROLES, extract_skills, normalize_role
from ..sources import explore, registry, research
from .common import clip, current_user, err, latest_resume

bp = Blueprint("opportunities", __name__, url_prefix="/api")
KINDS = ("job", "internship", "freelance")


def _snippet(t: str, n=260):
    t = " ".join((t or "").split())
    return t if len(t) <= n else t[: n - 1] + "\u2026"


def _card(j: Job, m=None, saved=False):
    return {"id": j.id, "source": j.source, "title": j.title, "company": j.company, "location": j.location, "remote": j.remote, "kind": j.kind,
            "url": j.url, "salary": j.salary, "logo": j.logo, "skills": (j.skills or [])[:8], "snippet": _snippet(j.description),
            "posted_at": j.posted_at.isoformat() if j.posted_at else None, "saved": saved, "match": m}


def _profile(u):
    r = latest_resume(u.id)
    if not r:
        return None, normalize_role(u.target_role), "fresher"
    return resume_profile(r.parsed), normalize_role(r.target_role or u.target_role), (r.analysis or {}).get("stage", "fresher")


@bp.get("/opportunities")
@jwt_required()
def list_opportunities():
    u = current_user()
    a = request.args
    kind = a.get("kind", "")
    q, loc = clip(a.get("q"), 80), clip(a.get("location"), 80)
    page, per = max(1, a.get("page", 1, type=int)), max(5, min(50, a.get("per_page", 20, type=int)))
    state = registry.ensure_fresh()
    if q or kind == "internship":
        registry.adzuna_search((q or "software") + (" intern" if kind == "internship" else ""), loc)
    qs = Job.query
    if kind in KINDS:
        qs = qs.filter(Job.kind == kind)
    if a.get("remote") == "1":
        qs = qs.filter(Job.remote.is_(True))
    if a.get("source"):
        qs = qs.filter(Job.source == a["source"])
    if q:
        like = f"%{q.lower()}%"
        qs = qs.filter(or_(db.func.lower(Job.title).like(like), db.func.lower(Job.company).like(like), db.func.lower(Job.description).like(like)))
    if loc:
        qs = qs.filter(db.func.lower(Job.location).like(f"%{loc.lower()}%"))
    rows = qs.order_by(Job.posted_at.desc().nullslast(), Job.id.desc()).limit(500).all()
    saved_ids = {s.job_id for s in SavedJob.query.filter_by(user_id=u.id).all()}
    prof, role, stage = _profile(u)
    items = [(j, match_job(j, prof, role, stage) if prof else None) for j in rows]
    if a.get("sort", "match") == "match" and prof:
        items.sort(key=lambda x: -x[1]["score"])
    total = len(items)
    chunk = items[(page - 1) * per: page * per]
    return jsonify({"items": [_card(j, m, j.id in saved_ids) for j, m in chunk], "total": total, "page": page, "pages": max(1, -(-total // per)),
                    "sync": state, "personalized": bool(prof), "role": role})


@bp.get("/opportunities/<int:jid>")
@jwt_required()
def job_detail(jid):
    u = current_user()
    j = db.session.get(Job, jid)
    if not j:
        return err("Listing not found.", 404)
    prof, role, stage = _profile(u)
    saved = db.session.query(SavedJob.id).filter_by(user_id=u.id, job_id=jid).first() is not None
    c = _card(j, match_job(j, prof, role, stage) if prof else None, saved)
    c["description"] = j.description
    c["attribution"] = next((s["attribution"] for s in registry.status() if s["source"] == j.source), "")
    return jsonify(c)


@bp.post("/opportunities/<int:jid>/save")
@jwt_required()
def save_job(jid):
    u = current_user()
    if not db.session.get(Job, jid):
        return err("Listing not found.", 404)
    if not SavedJob.query.filter_by(user_id=u.id, job_id=jid).first():
        db.session.add(SavedJob(user_id=u.id, job_id=jid))
        db.session.commit()
    return jsonify({"saved": True})


@bp.delete("/opportunities/<int:jid>/save")
@jwt_required()
def unsave_job(jid):
    SavedJob.query.filter_by(user_id=current_user().id, job_id=jid).delete()
    db.session.commit()
    return jsonify({"saved": False})


@bp.get("/saved")
@jwt_required()
def saved():
    u = current_user()
    prof, role, stage = _profile(u)
    rows = SavedJob.query.filter_by(user_id=u.id).order_by(SavedJob.created_at.desc()).all()
    return jsonify({"items": [_card(s.job, match_job(s.job, prof, role, stage) if prof else None, True) for s in rows]})


@bp.get("/sources/status")
@jwt_required()
def sources_status():
    return jsonify({"sources": registry.status()})


@bp.get("/explore")
@jwt_required()
def explore_links():
    u = current_user()
    r = latest_resume(u.id)
    role = normalize_role(r.target_role if r else u.target_role)
    q = clip(request.args.get("q"), 60) or role.split("/")[0].strip()
    return jsonify({"query": q, "links": explore.build_links(q, clip(request.args.get("location"), 60) or u.location or "")})


ROLE_TOPICS = {
    "ML / AI Engineer": ["large language models", "retrieval augmented generation", "efficient fine-tuning", "model evaluation"],
    "Data Scientist": ["causal inference", "time series forecasting", "interpretable machine learning"],
    "Research Intern / Scientist": ["reinforcement learning", "transformers", "self-supervised learning"],
    "Cybersecurity Analyst": ["intrusion detection", "malware analysis", "LLM security"],
    "Data Engineer": ["data pipelines", "stream processing", "data quality"],
    "DevOps / Cloud Engineer": ["observability", "serverless computing", "infrastructure as code"],
    "Backend Developer": ["distributed systems", "database indexing", "API design"],
    "Software Engineer": ["software testing", "program analysis", "code generation"],
}


@bp.get("/research/topics")
@jwt_required()
def research_topics():
    u = current_user()
    r = latest_resume(u.id)
    role = normalize_role(r.target_role if r else u.target_role)
    topics = list(ROLE_TOPICS.get(role, ["machine learning", "software engineering"]))
    if r:
        for s in list((r.parsed or {}).get("skills", {}).get("all", {}))[:12]:
            if s in ("nlp", "computer vision", "reinforcement learning", "blockchain", "cryptography", "deep learning", "graphql", "kubernetes") and s not in topics:
                topics.append(s)
    return jsonify({"topics": topics[:8], "role": role})


@bp.get("/research")
@jwt_required()
def research_search():
    q = clip(request.args.get("q"), 120)
    if len(q) < 3:
        return err("Enter at least 3 characters to search papers.")
    source = request.args.get("source", "openalex")
    if source not in ("openalex", "arxiv"):
        return err("Unknown source.")
    try:
        items = research.search(q, source, request.args.get("limit", 10, type=int), request.args.get("page", 1, type=int))
    except Exception:
        return err("The paper source is not responding right now. Try again or switch source.", 502)
    r = latest_resume(current_user().id)
    mine = set((r.parsed or {}).get("skills", {}).get("all", {})) if r else set()
    for p in items:
        p["related_skills"] = [s for s in extract_skills(p["title"] + " " + p["abstract"]) if s in mine][:4]
    return jsonify({"items": items, "source": source, "query": q})
