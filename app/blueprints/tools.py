import base64
import random

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..extensions import db, limiter
from ..models import APP_STATUSES, Job
from ..services import ai
from ..services import jobtext
from ..services.skills import ROLES, normalize_role
from .common import body, clip, current_user, err, latest_resume

bp = Blueprint("tools", __name__, url_prefix="/api")


@bp.get("/meta")
def meta():
    return jsonify({"roles": list(ROLES), "statuses": APP_STATUSES, "kinds": ["job", "internship", "freelance"], "ai_enabled": ai.enabled(),
                    "ai_model": ai.current_model() if ai.enabled() else None, "vision_enabled": ai.vision_enabled()})


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


IMG_MAGIC = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg", b"RIFF": "image/webp"}


def _image_mime(data: bytes):
    for m, mime in IMG_MAGIC.items():
        if data.startswith(m) and (mime != "image/webp" or data[8:12] == b"WEBP"):
            return mime
    return None


@bp.post("/outreach/analyze")
@jwt_required()
@limiter.limit("30 per hour")
def outreach_analyze():
    """Job description text, a screenshot, or a saved listing -> understand the job -> match to resume -> write the message."""
    u = current_user()
    r = latest_resume(u.id)
    if not r:
        return err("Upload your resume first so the message can use your real experience.", 404, code="no_resume")
    form = request.form if request.form else body()
    kind = form.get("kind", "cold_email")
    tone = form.get("tone", "concise")
    if kind not in ai.KINDS:
        return err("Unknown message type.")
    if tone not in jobtext.TONES:
        tone = "concise"
    text = clip(form.get("jd_text"), 12000)
    notes, source = [], "text"
    job_id = str(form.get("job_id") or "")
    if job_id.isdigit() and not text:
        j = db.session.get(Job, int(job_id))
        if j:
            text = f"{j.title}\n{j.company}\n{j.location}\n{j.description}"
            source = "listing"
    f = request.files.get("image")
    if f and not text:
        data = f.read()
        mime = _image_mime(data)
        if not mime:
            return err("Upload a PNG, JPG or WEBP screenshot.")
        if len(data) > 3 * 1024 * 1024:
            return err("Screenshot is too large (max 3 MB). Crop it or use a smaller image.")
        if not ai.vision_enabled():
            return err("Reading screenshots needs AI. Set GROQ_API_KEY on the server, or paste the job text instead.", 503, code="vision_disabled")
        try:
            ext = ai.extract_job_from_image(base64.b64encode(data).decode(), mime)
        except ai.AIError as e:
            return err(str(e), 502)
        text = "\n".join(x for x in (ext["role"], ext["company"], ext["location"], ext["description"], ext["contact_email"]) if x)
        source = "screenshot"
    if len(text) < 40:
        return err("Paste the job description or upload a screenshot of it.")
    job = jobtext.analyze_jd(text)
    # user-edited fields win over detection
    for k in ("role", "company"):
        if clip(form.get(k), 90):
            job[k] = clip(form.get(k), 90)
    parsed = r.parsed
    fit = jobtext.fit_summary(parsed, job["skills"])
    proof = jobtext.proof_points(parsed, job["skills"])
    creds = jobtext.credentials(parsed, job["skills"])
    msg, used_ai = None, False
    if ai.enabled():
        cand = {"name": u.name, "target_role": r.target_role, "education": f"{u.degree} {u.college}".strip(), "links": [x for x in (u.linkedin, u.github, u.portfolio) if x],
                "matching_skills": fit["matched"], "missing_skills": fit["missing"], "proof_points": [{"text": p["text"], "where": p["source"], "type": p["kind"]} for p in proof],
                "credentials": creds, "internships": parsed["totals"]["internships"], "open_source": parsed["open_source"]["level"]}
        try:
            msg = ai.outreach_v2(kind, tone, {"role": job["role"], "company": job["company"], "location": job["location"], "required_skills": job["skills"],
                                              "description": text[:3500]}, cand)
            used_ai = True
        except ai.AIError:
            notes.append("AI was unavailable, so a template message was used.")
    if msg is None:
        msg = jobtext.compose_template(kind, tone, u, job["role"], job["company"], fit["matched"], proof, creds)
    if not job["company"]:
        notes.append("Company not detected. Add it in the Company field and regenerate for a better message.")
    if fit["missing"]:
        notes.append("Not on your resume: " + ", ".join(fit["missing"][:5]) + ". The message does not claim them.")
    return jsonify({"job": job, "fit": fit, "proof_points": proof, "credentials": creds, "message": {**msg, "ai": used_ai}, "source": source, "notes": notes, "jd_text": text[:8000]})
