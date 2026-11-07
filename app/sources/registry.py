"""Fetch, normalise, dedupe and cache jobs in PostgreSQL.

Respect for upstream rate limits: each source has a TTL and refreshes are *claimed*
atomically in the DB (UPDATE ... WHERE last_run_at < cutoff) so several gunicorn
workers never fetch the same source at once.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Job, SavedJob, SourceSync, Application
from ..services.skills import extract_skills
from .providers import ADZUNA, BY_NAME, FEED_SOURCES

log = logging.getLogger("rc.sources")
_ADZ_CACHE: dict = {}


def _now():
    return datetime.now(timezone.utc)


def ttl_hours(name: str) -> int:
    c = current_app.config
    return c["SOURCE_TTL_HOURS"].get(name, c["SOURCE_DEFAULT_TTL_HOURS"])


def upsert_jobs(rows: list[dict], source: str) -> int:
    if not rows:
        return 0
    ids = [r["external_id"] for r in rows if r["external_id"]]
    existing = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for j in db.session.execute(select(Job).where(Job.source == source, Job.external_id.in_(chunk))).scalars():
            existing[j.external_id] = j
    n = 0
    for r in rows:
        if not r["external_id"] or not r["title"] or not r["url"]:
            continue
        sk = [s for s, _ in extract_skills(r["title"] + "\n" + r["description"]).most_common(15)]
        job = existing.get(r["external_id"])
        if job is None:
            job = Job(source=source, external_id=r["external_id"])
            db.session.add(job)
            existing[r["external_id"]] = job
        for f in ("title", "company", "location", "remote", "kind", "url", "salary", "logo", "description", "tags", "posted_at"):
            setattr(job, f, r[f])
        job.skills = sk
        job.fetched_at = _now()
        n += 1
    db.session.commit()
    return n


def _claim(name: str, force: bool) -> bool:
    row = db.session.get(SourceSync, name)
    if row is None:
        try:
            db.session.add(SourceSync(source=name, last_status="never"))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    cutoff = _now() - timedelta(hours=ttl_hours(name))
    cond = SourceSync.source == name
    if not force:
        cond = cond & ((SourceSync.last_run_at.is_(None)) | (SourceSync.last_run_at < cutoff))
    res = db.session.execute(update(SourceSync).where(cond).values(last_run_at=_now(), last_status="running"),
                            execution_options={"synchronize_session": False})
    db.session.commit()
    return res.rowcount == 1


def refresh_source(name: str, force: bool = False) -> dict:
    src = BY_NAME[name]
    if not src.available():
        return {"source": name, "status": "skipped", "reason": "not configured"}
    if not _claim(name, force):
        return {"source": name, "status": "fresh"}
    try:
        rows = src.fetch()
        n = upsert_jobs(rows, name)
        db.session.execute(update(SourceSync).where(SourceSync.source == name).values(last_status="ok", last_count=n, error=""))
        db.session.commit()
        return {"source": name, "status": "ok", "count": n}
    except Exception as e:  # network/JSON errors must never break the app
        db.session.rollback()
        retry_soon = _now() - timedelta(hours=max(0, ttl_hours(name) - 0.5))
        db.session.execute(update(SourceSync).where(SourceSync.source == name).values(last_status="error", error=str(e)[:480], last_run_at=retry_soon))
        db.session.commit()
        log.warning("source %s failed: %s", name, e)
        return {"source": name, "status": "error", "error": str(e)[:200]}


def refresh_all(force: bool = False, parallel: bool = True) -> list[dict]:
    app = current_app._get_current_object()

    def run(src):
        with app.app_context():
            try:
                return refresh_source(src.name, force)
            finally:
                db.session.remove()

    if parallel:
        with ThreadPoolExecutor(max_workers=len(FEED_SOURCES)) as ex:
            res = list(ex.map(run, FEED_SOURCES))
    else:
        res = [run(s) for s in FEED_SOURCES]
    prune()
    return res


def prune(days: int = 45):
    cutoff = _now() - timedelta(days=days)
    keep = select(SavedJob.job_id).union(select(Application.job_id).where(Application.job_id.isnot(None)))
    db.session.query(Job).filter(Job.fetched_at < cutoff, ~Job.id.in_(keep)).delete(synchronize_session=False)
    db.session.commit()


_BG_LOCK = threading.Lock()
_BG_ACTIVE = False


def refreshing() -> bool:
    return _BG_ACTIVE


def start_background_refresh() -> bool:
    """Start (at most one) background thread that fetches every feed source. Never blocks the request."""
    global _BG_ACTIVE
    with _BG_LOCK:
        if _BG_ACTIVE:
            return False
        _BG_ACTIVE = True
    app = current_app._get_current_object()

    def bg():
        global _BG_ACTIVE
        try:
            with app.app_context():
                try:
                    refresh_all()
                finally:
                    db.session.remove()
        except Exception:
            log.exception("background refresh crashed")
        finally:
            _BG_ACTIVE = False

    threading.Thread(target=bg, daemon=True, name="job-refresh").start()
    return True


def ensure_fresh() -> str:
    """Never blocks. Returns 'fresh' or 'refreshing' (a background fetch is running or was just started)."""
    if not current_app.config.get("AUTO_REFRESH_SOURCES"):
        return "disabled"
    if _BG_ACTIVE:
        return "refreshing"
    cutoff_any = _now() - timedelta(hours=min(ttl_hours(s.name) for s in FEED_SOURCES))
    empty = db.session.query(Job.id).limit(1).first() is None
    stale = db.session.query(SourceSync.source).filter((SourceSync.last_run_at.is_(None)) | (SourceSync.last_run_at < cutoff_any)).first()
    unseen = db.session.query(SourceSync).count() < len(FEED_SOURCES)
    if empty or stale or unseen:
        start_background_refresh()
        return "refreshing"
    return "fresh"


def adzuna_search(what: str, where: str = "", page: int = 1) -> int:
    """Query-driven fetch (cached 30 min per query). Returns number upserted."""
    if not ADZUNA.available():
        return 0
    key = (what.lower(), where.lower(), page)
    hit = _ADZ_CACHE.get(key)
    if hit and time.time() - hit < 1800:
        return 0
    try:
        rows = ADZUNA.fetch(what=what, where=where, page=page, timeout=7)
        _ADZ_CACHE[key] = time.time()
        return upsert_jobs(rows, "adzuna")
    except Exception as e:
        db.session.rollback()
        log.warning("adzuna failed: %s", e)
        return 0


def status() -> list[dict]:
    rows = {r.source: r for r in db.session.query(SourceSync).all()}
    out = []
    for s in FEED_SOURCES + [ADZUNA]:
        r = rows.get(s.name)
        out.append({"source": s.name, "label": s.label, "homepage": s.homepage, "attribution": s.attribution, "configured": s.available(),
                    "last_run_at": r.last_run_at.isoformat() if r and r.last_run_at else None,
                    "last_status": r.last_status if r else "never", "last_count": r.last_count if r else 0})
    return out
