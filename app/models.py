"""SQLAlchemy models (PostgreSQL first, SQLite compatible for tests)."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import deferred

from .extensions import db

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(40), default="")
    college = db.Column(db.String(200), default="")
    degree = db.Column(db.String(120), default="")
    grad_year = db.Column(db.Integer)
    target_role = db.Column(db.String(80), default="Software Engineer")
    location = db.Column(db.String(120), default="")
    linkedin = db.Column(db.String(255), default="")
    github = db.Column(db.String(255), default="")
    portfolio = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True))

    __table_args__ = (Index("uq_users_email_lower", func.lower(email), unique=True),)

    def public(self):
        return {c: getattr(self, c) for c in (
            "id", "name", "email", "phone", "college", "degree", "grad_year", "target_role",
            "location", "linkedin", "github", "portfolio")}


class Resume(db.Model):
    __tablename__ = "resumes"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    mime = db.Column(db.String(100), default="")
    size = db.Column(db.Integer, default=0)
    file_bytes = deferred(db.Column(db.LargeBinary))
    raw_text = deferred(db.Column(db.Text, default=""))
    target_role = db.Column(db.String(80), default="")
    parsed = db.Column(JSONType, default=dict)
    analysis = db.Column(JSONType, default=dict)
    ai_review = db.Column(JSONType)
    ats_score = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class Job(db.Model):
    __tablename__ = "jobs"
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(30), nullable=False)
    external_id = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    company = db.Column(db.String(200), default="")
    location = db.Column(db.String(200), default="")
    remote = db.Column(db.Boolean, default=False)
    kind = db.Column(db.String(20), default="job", index=True)  # job | internship | freelance
    url = db.Column(db.String(1000), default="")
    salary = db.Column(db.String(120), default="")
    logo = db.Column(db.String(500), default="")
    description = db.Column(db.Text, default="")
    skills = db.Column(JSONType, default=list)
    tags = db.Column(JSONType, default=list)
    posted_at = db.Column(db.DateTime(timezone=True), index=True)
    fetched_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_job_source_ext"),)


class SourceSync(db.Model):
    __tablename__ = "source_sync"
    source = db.Column(db.String(30), primary_key=True)
    last_run_at = db.Column(db.DateTime(timezone=True))
    last_status = db.Column(db.String(20), default="never")
    last_count = db.Column(db.Integer, default=0)
    error = db.Column(db.String(500), default="")


class SavedJob(db.Model):
    __tablename__ = "saved_jobs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    job = db.relationship("Job")
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_saved_user_job"),)


APP_STATUSES = ["saved", "applied", "oa", "interview", "offer", "rejected"]


class Application(db.Model):
    __tablename__ = "applications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id", ondelete="SET NULL"))
    company = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(20), default="job")
    status = db.Column(db.String(20), default="applied", nullable=False)
    url = db.Column(db.String(1000), default="")
    notes = db.Column(db.Text, default="")
    applied_on = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    events = db.relationship("ApplicationEvent", cascade="all, delete-orphan", order_by="ApplicationEvent.at")


class ApplicationEvent(db.Model):
    __tablename__ = "application_events"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = db.Column(db.String(20))
    to_status = db.Column(db.String(20), nullable=False)
    at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
