import logging
import secrets

from flask import Flask, jsonify, render_template, request
from flask_jwt_extended.exceptions import CSRFError
from werkzeug.exceptions import HTTPException

from .config import Config
from .extensions import db, jwt, limiter, migrate

log = logging.getLogger("rc")

CSP = ("default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(config or Config)

    if not app.config.get("SECRET_KEY"):
        if app.config["ENV"] == "production":
            raise RuntimeError("SECRET_KEY must be set in production (use: python -c 'import secrets;print(secrets.token_urlsafe(48))')")
        app.config["SECRET_KEY"] = secrets.token_urlsafe(48)
        app.config["JWT_SECRET_KEY"] = app.config["SECRET_KEY"]
        log.warning("SECRET_KEY not set; using an ephemeral dev key (sessions reset on restart).")
    elif app.config["ENV"] == "production" and len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("SECRET_KEY is too short (min 32 chars).")

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)

    from .blueprints import analytics, applications, auth, opportunities, resumes, tools
    for m in (auth, resumes, opportunities, applications, analytics, tools):
        app.register_blueprint(m.bp)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/healthz")
    def health():
        try:
            db.session.execute(db.text("SELECT 1"))
            return {"status": "ok"}
        except Exception:
            return {"status": "db_error"}, 503

    @app.after_request
    def headers(resp):
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if app.config["ENV"] == "production":
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    def api_err(msg, status, **extra):
        return jsonify({"error": msg, **extra}), status

    @app.errorhandler(HTTPException)
    def http_err(e):
        if request.path.startswith("/api/") or request.path == "/healthz":
            msg = {413: "File too large (max 8 MB).", 429: "Too many requests. Please slow down."}.get(e.code, e.description)
            return api_err(msg, e.code)
        return e

    @app.errorhandler(CSRFError)
    def csrf_err(e):
        return api_err("Session check failed. Please refresh and try again.", 401, code="csrf")

    @app.errorhandler(Exception)
    def unhandled(e):
        db.session.rollback()
        log.exception("Unhandled error on %s", request.path)
        if request.path.startswith("/api/"):
            return api_err("Something went wrong on our side.", 500)
        raise e

    @jwt.unauthorized_loader
    def _unauth(reason):
        return api_err("Please sign in.", 401, code="unauthorized")

    @jwt.invalid_token_loader
    def _invalid(reason):
        return api_err("Your session is invalid. Please sign in again.", 401, code="invalid")

    @jwt.expired_token_loader
    def _expired(h, p):
        return api_err("Session expired.", 401, code="token_expired")

    @app.cli.command("refresh-jobs")
    def refresh_jobs_cmd():
        """Fetch all job sources now (use with cron)."""
        from .sources.registry import refresh_all
        for r in refresh_all(force=True):
            print(r)

    @app.cli.command("init-db")
    def init_db_cmd():
        """Create tables without migrations (dev convenience)."""
        db.create_all()
        print("tables created")

    import os
    if app.config["TESTING"] or os.getenv("AUTO_CREATE_DB", "1" if app.config["ENV"] == "development" else "0") == "1":
        with app.app_context():
            db.create_all()
    return app
