from datetime import date, datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..extensions import db
from ..models import APP_STATUSES, Application, ApplicationEvent, Job
from .common import body, clip, current_user, err

bp = Blueprint("applications", __name__, url_prefix="/api")


def _ser(a: Application):
    return {"id": a.id, "company": a.company, "role": a.role, "kind": a.kind, "status": a.status, "url": a.url, "notes": a.notes,
            "job_id": a.job_id, "applied_on": a.applied_on.isoformat() if a.applied_on else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            "history": [{"from": e.from_status, "to": e.to_status, "at": e.at.isoformat()} for e in a.events]}


def _own(aid):
    a = db.session.get(Application, aid)
    u = current_user()
    return a if a and a.user_id == u.id else None


def _date(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


@bp.get("/applications")
@jwt_required()
def list_apps():
    rows = Application.query.filter_by(user_id=current_user().id).order_by(Application.updated_at.desc()).all()
    return jsonify({"items": [_ser(a) for a in rows], "statuses": APP_STATUSES})


@bp.post("/applications")
@jwt_required()
def create_app_():
    u, d = current_user(), body()
    job = db.session.get(Job, int(d["job_id"])) if str(d.get("job_id") or "").isdigit() else None
    company = clip(d.get("company") or (job.company if job else ""), 200)
    role = clip(d.get("role") or (job.title if job else ""), 200)
    if not company or not role:
        return err("Company and role are required.")
    status = d.get("status", "applied")
    if status not in APP_STATUSES:
        return err("Invalid status.")
    kind = job.kind if job else d.get("kind", "job")
    if kind not in ("job", "internship", "freelance"):
        kind = "job"
    a = Application(user_id=u.id, job_id=job.id if job else None, company=company, role=role, kind=kind, status=status,
                    url=clip(d.get("url") or (job.url if job else ""), 1000), notes=clip(d.get("notes"), 4000),
                    applied_on=_date(d.get("applied_on")) or (date.today() if status != "saved" else None))
    db.session.add(a)
    db.session.flush()
    db.session.add(ApplicationEvent(application_id=a.id, from_status=None, to_status=status))
    db.session.commit()
    return jsonify(_ser(a)), 201


@bp.patch("/applications/<int:aid>")
@jwt_required()
def update_app(aid):
    a, d = _own(aid), body()
    if not a:
        return err("Application not found.", 404)
    for k, n in (("company", 200), ("role", 200), ("url", 1000), ("notes", 4000)):
        if k in d and (v := clip(d[k], n)) is not None:
            if k in ("company", "role") and not v:
                return err(f"{k.title()} cannot be empty.")
            setattr(a, k, v)
    if "applied_on" in d:
        a.applied_on = _date(d["applied_on"])
    if "status" in d and d["status"] != a.status:
        if d["status"] not in APP_STATUSES:
            return err("Invalid status.")
        db.session.add(ApplicationEvent(application_id=a.id, from_status=a.status, to_status=d["status"]))
        if a.status == "saved" and d["status"] == "applied" and not a.applied_on:
            a.applied_on = date.today()
        a.status = d["status"]
    a.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(_ser(a))


@bp.delete("/applications/<int:aid>")
@jwt_required()
def delete_app(aid):
    a = _own(aid)
    if not a:
        return err("Application not found.", 404)
    db.session.delete(a)
    db.session.commit()
    return jsonify({"ok": True})
