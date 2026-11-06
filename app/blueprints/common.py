from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity

from ..extensions import db
from ..models import Resume, User


def err(msg, status=400, **extra):
    return jsonify({"error": msg, **extra}), status


def current_user() -> User | None:
    ident = get_jwt_identity()
    return db.session.get(User, int(ident)) if ident else None


def body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def latest_resume(user_id: int) -> Resume | None:
    return Resume.query.filter_by(user_id=user_id).order_by(Resume.created_at.desc(), Resume.id.desc()).first()


def clip(v, n) -> str:
    return str(v or "").strip()[:n]
