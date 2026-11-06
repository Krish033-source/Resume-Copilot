from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..services import analytics as svc
from ..services.ats import role_report
from ..services.skills import normalize_role
from .common import current_user, err, latest_resume

bp = Blueprint("analytics", __name__, url_prefix="/api")


@bp.get("/analytics/overview")
@jwt_required()
def overview():
    u = current_user()
    r = latest_resume(u.id)
    rr = (r.analysis or {}).get("role_report") if r else None
    return jsonify(svc.overview(u, r, rr))


@bp.get("/skill-gap")
@jwt_required()
def skill_gap():
    u = current_user()
    r = latest_resume(u.id)
    if not r:
        return err("Upload a resume first.", 404)
    role = normalize_role(request.args.get("role") or r.target_role)
    rr = role_report(r.parsed, role)
    return jsonify({"role_report": rr, "roadmap": svc.roadmap(rr, 10)})
