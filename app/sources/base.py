"""Shared helpers for job sources."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

import requests
from flask import current_app

INTERN_RE = re.compile(r"\bintern(?:ship)?s?\b|\btrainee\b|\bapprentice(?:ship)?\b|\bwerkstudent\b|\bworking student\b|\bpraktikum\b|\bgraduate program", re.I)
FREELANCE_RE = re.compile(r"\bfreelanc\w*|\bcontract(?:or)?\b|\bgig\b|\bconsultant\b|\bproject[- ]based\b", re.I)


def user_agent() -> str:
    mail = current_app.config.get("CONTACT_EMAIL", "")
    return "ResumeCopilot/2.0 (+https://github.com/Krish033-source/Resume-Copilot" + (f"; {mail})" if mail else ")")


def get_json(url: str, params=None, timeout=15, headers=None):
    h = {"User-Agent": user_agent(), "Accept": "application/json"}
    h.update(headers or {})
    r = requests.get(url, params=params, headers=h, timeout=timeout)
    r.raise_for_status()
    return r.json()


def strip_html(s: str | None, limit: int = 6000) -> str:
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "\u2022 ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s).strip()
    return s[:limit]


def classify_kind(title: str, types: list[str] | None = None, tags: list[str] | None = None) -> str:
    blob_t = title or ""
    types_s = " ".join(types or []).lower()
    if "intern" in types_s or INTERN_RE.search(blob_t):
        return "internship"
    if any(x in types_s for x in ("freelance", "contract")) or FREELANCE_RE.search(blob_t) or "freelance" in " ".join(tags or []).lower():
        return "freelance"
    return "job"


def parse_dt(v) -> datetime | None:
    if v in (None, ""):
        return None
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
        s = str(v).strip().replace("Z", "+00:00")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", s):
            s = s.replace(" ", "T")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def salary_text(lo=None, hi=None, cur="", period="") -> str:
    try:
        lo = int(lo) if lo else 0
        hi = int(hi) if hi else 0
    except (TypeError, ValueError):
        return ""
    if not lo and not hi:
        return ""
    fmt = lambda n: f"{n:,}"
    rng = f"{fmt(lo)}-{fmt(hi)}" if lo and hi and lo != hi else fmt(lo or hi)
    return " ".join(x for x in (cur, rng, period) if x).strip()


class Source:
    name = "base"
    label = "Base"
    homepage = ""
    attribution = ""
    needs_key = False

    def available(self) -> bool:
        return True

    def fetch(self) -> list[dict]:  # pragma: no cover - interface
        raise NotImplementedError

    @staticmethod
    def row(external_id, title, company="", location="", remote=False, kind="job", url="", salary="", logo="",
            description="", tags=None, posted_at=None) -> dict:
        return {"external_id": str(external_id), "title": (title or "").strip()[:300], "company": (company or "").strip()[:200],
                "location": (location or "").strip()[:200], "remote": bool(remote), "kind": kind, "url": (url or "").strip()[:1000],
                "salary": (salary or "")[:120], "logo": (logo or "")[:500], "description": description or "",
                "tags": [str(t)[:40] for t in (tags or [])][:12], "posted_at": posted_at}
