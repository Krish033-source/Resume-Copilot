import random

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..extensions import db, limiter
from ..models import APP_STATUSES, Job
from ..services import ai
from ..services.skills import ROLES, normalize_role
from .common import body, clip, current_user, err, latest_resume

bp = Blueprint("tools", __name__, url_prefix="/api")


@bp.get("/meta")
def meta():
    return jsonify({"roles": list(ROLES), "statuses": APP_STATUSES, "kinds": ["job", "internship", "freelance"], "ai_enabled": ai.enabled(),
                    "ai_model": ai.current_model() if ai.enabled() else None})


@bp.post("/outreach")
@jwt_required()
@limiter.limit("30 per hour")
def outreach():
    u, d = current_user(), body()
    kind = d.get("kind", "cold_email")
    if kind not in ai.KINDS:
        return err("Unknown message type.")
    job = db.session.get(Job, int(d["job_id"])) if str(d.get("job_id") or "").isdigit() else None
    company = clip(d.get("company") or (job.company if job else ""), 120)
    role = clip(d.get("role") or (job.title if job else ""), 120)
    if not company or not role:
        return err("Company and role are required.")
    r = latest_resume(u.id)
    skills = list(((r.parsed or {}).get("skills", {}).get("in_context") or {}))[:6] if r else []
    if ai.enabled() and r:
        try:
            out = ai.outreach(kind, r.raw_text or "", role, company, job.description if job else clip(d.get("jd"), 3000), u.name)
            return jsonify({**out, "ai": True})
        except ai.AIError:
            pass
    return jsonify({**ai.template_outreach(kind, u.name, role, company, skills), "ai": False})


@bp.get("/interview/questions")
@jwt_required()
def questions():
    u = current_user()
    r = latest_resume(u.id)
    role = normalize_role(request.args.get("role") or (r.target_role if r else u.target_role))
    bank = ai.QUESTION_BANK
    role_q = bank["role"].get(role, bank["role"]["Software Engineer"])
    qs = [{"category": "Role", "question": q} for q in role_q] + [{"category": "Core CS", "question": q} for q in random.sample(bank["core"], 3)] + \
         [{"category": "Behavioral", "question": q} for q in random.sample(bank["behavioral"], 3)]
    if r:
        for p in (r.parsed or {}).get("projects", [])[:2]:
            if p.get("heading"):
                qs.insert(0, {"category": "Your resume", "question": f"Walk me through '{p['heading'][:60]}'. What was hardest and what would you change?"})
    return jsonify({"role": role, "questions": qs[:12]})


@bp.post("/interview/evaluate")
@jwt_required()
@limiter.limit("40 per hour")
def evaluate():
    d = body()
    q, a = clip(d.get("question"), 300), clip(d.get("answer"), 3000)
    if len(a.split()) < 8:
        return err("Write a fuller answer (at least a couple of sentences).")
    role = normalize_role(d.get("role"))
    if ai.enabled():
        try:
            return jsonify({**ai.interview_feedback(role, q, a), "ai": True})
        except ai.AIError:
            pass
    return jsonify({**ai.heuristic_interview_feedback(a), "ai": False})
