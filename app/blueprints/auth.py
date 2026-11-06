from datetime import datetime, timezone

from email_validator import EmailNotValidError, validate_email
from flask import Blueprint, jsonify
from flask_jwt_extended import (create_access_token, create_refresh_token, get_jwt_identity, jwt_required,
                                set_access_cookies, set_refresh_cookies, unset_jwt_cookies)
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, limiter
from ..models import Application, Resume, SavedJob, User
from ..services.skills import normalize_role
from .common import body, clip, current_user, err

bp = Blueprint("auth", __name__, url_prefix="/api")
_DUMMY = generate_password_hash("dummy-password-for-timing")


def _session(user: User, status=200):
    resp = jsonify({"user": user.public()})
    resp.status_code = status
    set_access_cookies(resp, create_access_token(identity=str(user.id)))
    set_refresh_cookies(resp, create_refresh_token(identity=str(user.id)))
    return resp


def _check_password(pw: str):
    if len(pw) < 8:
        return "Password must be at least 8 characters."
    if len(pw) > 128:
        return "Password is too long."
    if not any(c.isalpha() for c in pw) or not any(c.isdigit() for c in pw):
        return "Password must contain letters and numbers."
    return None


@bp.post("/auth/register")
@limiter.limit("8 per hour")
def register():
    d = body()
    name, pw = clip(d.get("name"), 80), str(d.get("password") or "")
    if len(name) < 2:
        return err("Please enter your name.")
    try:
        email = validate_email(str(d.get("email") or ""), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        return err("Enter a valid email address.")
    if (msg := _check_password(pw)):
        return err(msg)
    if db.session.query(User.id).filter(func.lower(User.email) == email).first():
        return err("An account with this email already exists.", 409)
    u = User(name=name, email=email, password_hash=generate_password_hash(pw), last_login_at=datetime.now(timezone.utc))
    db.session.add(u)
    db.session.commit()
    return _session(u, 201)


@bp.post("/auth/login")
@limiter.limit("10 per minute")
def login():
    d = body()
    email = str(d.get("email") or "").strip().lower()
    pw = str(d.get("password") or "")
    u = db.session.query(User).filter(func.lower(User.email) == email).first()
    ok = check_password_hash(u.password_hash if u else _DUMMY, pw)
    if not u or not ok:
        return err("Incorrect email or password.", 401)
    u.last_login_at = datetime.now(timezone.utc)
    db.session.commit()
    return _session(u)


@bp.post("/auth/logout")
def logout():
    resp = jsonify({"ok": True})
    unset_jwt_cookies(resp)
    return resp


@bp.post("/auth/refresh")
@jwt_required(refresh=True)
def refresh():
    u = current_user()
    if not u:
        return err("Please sign in.", 401)
    resp = jsonify({"user": u.public()})
    set_access_cookies(resp, create_access_token(identity=str(u.id)))
    return resp


@bp.get("/auth/me")
@jwt_required()
def me():
    u = current_user()
    return jsonify({"user": u.public()}) if u else err("Please sign in.", 401)


@bp.put("/profile")
@jwt_required()
def update_profile():
    u, d = current_user(), body()
    limits = {"name": 80, "phone": 40, "college": 200, "degree": 120, "location": 120, "linkedin": 255, "github": 255, "portfolio": 255}
    for k, n in limits.items():
        if k in d:
            val = clip(d[k], n)
            if k == "name" and len(val) < 2:
                return err("Name is too short.")
            setattr(u, k, val)
    if "grad_year" in d:
        try:
            y = int(d["grad_year"]) if d["grad_year"] not in ("", None) else None
            u.grad_year = y if y is None or 1990 <= y <= 2040 else None
        except (TypeError, ValueError):
            return err("Graduation year must be a number.")
    if "target_role" in d:
        u.target_role = normalize_role(d["target_role"])
    db.session.commit()
    return jsonify({"user": u.public()})


@bp.post("/auth/change-password")
@jwt_required()
@limiter.limit("5 per hour")
def change_password():
    u, d = current_user(), body()
    if not check_password_hash(u.password_hash, str(d.get("current_password") or "")):
        return err("Current password is incorrect.", 403)
    if (msg := _check_password(str(d.get("new_password") or ""))):
        return err(msg)
    u.password_hash = generate_password_hash(d["new_password"])
    db.session.commit()
    return jsonify({"ok": True})


@bp.delete("/auth/account")
@jwt_required()
@limiter.limit("3 per hour")
def delete_account():
    u, d = current_user(), body()
    if not check_password_hash(u.password_hash, str(d.get("password") or "")):
        return err("Password is incorrect.", 403)
    for a in Application.query.filter_by(user_id=u.id).all():
        db.session.delete(a)  # ORM cascade removes events (SQLite does not enforce FK cascades)
    SavedJob.query.filter_by(user_id=u.id).delete()
    Resume.query.filter_by(user_id=u.id).delete()
    db.session.delete(u)
    db.session.commit()
    resp = jsonify({"ok": True})
    unset_jwt_cookies(resp)
    return resp
