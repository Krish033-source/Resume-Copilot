import re
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import jwt_required

from ..extensions import db, limiter
from ..models import Resume
from ..services import ai
from ..services.ats import analyze, match_jd
from ..services.resume_parser import extract_document, parse_resume
from ..services.skills import normalize_role
from .common import body, clip, current_user, err, latest_resume

bp = Blueprint("resumes", __name__, url_prefix="/api")
MAX_KEEP = 20
ALLOWED = {"pdf": b"%PDF", "docx": b"PK", "txt": None}


def _card(r: Resume):
    return {"id": r.id, "filename": r.filename, "ats_score": r.ats_score, "target_role": r.target_role, "size": r.size,
            "created_at": r.created_at.isoformat(), "grade": (r.analysis or {}).get("grade")}


def _full(r: Resume):
    return {**_card(r), "parsed": r.parsed, "analysis": r.analysis, "ai_review": r.ai_review, "ai_enabled": ai.enabled()}


def _own(rid):
    u = current_user()
    r = db.session.get(Resume, rid)
    return (r if r and r.user_id == u.id else None), u


@bp.post("/resumes")
@jwt_required()
@limiter.limit("20 per hour")
def upload():
    u = current_user()
    f = request.files.get("file")
    if not f or not f.filename:
        return err("Choose a PDF, DOCX or TXT file.")
    name = re.sub(r"[^\w.\- ()]", "_", f.filename)[:200]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        return err("Unsupported file type. Upload PDF, DOCX or TXT.")
    data = f.read()
    if not data:
        return err("The file is empty.")
    magic = ALLOWED[ext]
    if magic and not data.startswith(magic):
        return err(f"This file does not look like a real {ext.upper()}.")
    try:
        doc = extract_document(data, name)
    except Exception:
        return err("We could not read this file. Re-export it as a text-based PDF or DOCX.", 422)
    role = normalize_role(request.form.get("target_role") or u.target_role)
    parsed = parse_resume(doc)
    analysis = analyze(parsed, role)
    r = Resume(user_id=u.id, filename=name, mime=f.mimetype or "", size=len(data), file_bytes=data, raw_text=doc.text,
               target_role=role, parsed=parsed, analysis=analysis, ats_score=analysis["score"])
    db.session.add(r)
    db.session.commit()
    old = Resume.query.filter_by(user_id=u.id).order_by(Resume.created_at.desc(), Resume.id.desc()).offset(MAX_KEEP).all()
    for o in old:
        db.session.delete(o)
    if old:
        db.session.commit()
    return jsonify(_full(r)), 201


@bp.get("/resumes")
@jwt_required()
def list_resumes():
    u = current_user()
    rows = Resume.query.filter_by(user_id=u.id).order_by(Resume.created_at.desc(), Resume.id.desc()).all()
    return jsonify({"items": [_card(r) for r in rows]})


@bp.get("/resumes/latest")
@jwt_required()
def latest():
    r = latest_resume(current_user().id)
    return jsonify({"resume": _full(r) if r else None})


@bp.get("/resumes/<int:rid>")
@jwt_required()
def get_resume(rid):
    r, _ = _own(rid)
    return jsonify(_full(r)) if r else err("Resume not found.", 404)


@bp.delete("/resumes/<int:rid>")
@jwt_required()
def delete_resume(rid):
    r, _ = _own(rid)
    if not r:
        return err("Resume not found.", 404)
    db.session.delete(r)
    db.session.commit()
    return jsonify({"ok": True})


@bp.get("/resumes/<int:rid>/download")
@jwt_required()
def download(rid):
    r, _ = _own(rid)
    if not r:
        return err("Resume not found.", 404)
    safe = re.sub(r"[^\w.\- ]", "_", r.filename)
    return Response(r.file_bytes or b"", mimetype=r.mime or "application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{safe}"'})


@bp.post("/resumes/<int:rid>/rescore")
@jwt_required()
def rescore(rid):
    r, _ = _own(rid)
    if not r:
        return err("Resume not found.", 404)
    role = normalize_role(body().get("role"))
    r.target_role = role
    r.analysis = analyze(r.parsed, role)
    r.ats_score = r.analysis["score"]
    db.session.commit()
    return jsonify(_full(r))


@bp.post("/resumes/<int:rid>/ai-review")
@jwt_required()
@limiter.limit("15 per hour")
def ai_review(rid):
    r, _ = _own(rid)
    if not r:
        return err("Resume not found.", 404)
    if not ai.enabled():
        return err("AI review is not configured on this server.", 503, code="ai_disabled")
    try:
        r.ai_review = ai.review_resume(r.raw_text or "", r.parsed, r.analysis)
    except ai.AIError as e:
        return err(str(e), 502)
    db.session.commit()
    return jsonify({"ai_review": r.ai_review})


@bp.post("/resumes/<int:rid>/jd-match")
@jwt_required()
@limiter.limit("60 per hour")
def jd_match(rid):
    r, _ = _own(rid)
    if not r:
        return err("Resume not found.", 404)
    jd = clip(body().get("jd"), 12000)
    if len(jd) < 80:
        return err("Paste the full job description (at least a few lines).")
    return jsonify(match_jd(r.parsed, r.raw_text or "", jd))


@bp.post("/resumes/<int:rid>/tailor")
@jwt_required()
@limiter.limit("15 per hour")
def tailor(rid):
    r, _ = _own(rid)
    if not r:
        return err("Resume not found.", 404)
    jd = clip(body().get("jd"), 8000)
    if len(jd) < 80:
        return err("Paste the full job description first.")
    if not ai.enabled():
        return err("AI is not configured on this server.", 503, code="ai_disabled")
    try:
        return jsonify(ai.tailor_to_jd(r.raw_text or "", jd, r.target_role))
    except ai.AIError as e:
        return err(str(e), 502)
