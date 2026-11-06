"""Resume <-> job matching with explainable reasons."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .skills import ROLES, extract_skills, role_weights

SENIOR_RE = re.compile(r"\b(senior|sr\.?|lead|principal|staff|head|director|manager|architect|vp)\b", re.I)
JUNIOR_RE = re.compile(r"\b(junior|jr\.?|entry|graduate|fresher|trainee|associate|intern(?:ship)?|apprentice)\b", re.I)


def resume_profile(parsed: dict) -> dict:
    return {"all": set(parsed["skills"]["all"]), "ctx": set(parsed["skills"]["in_context"])}


def match_job(job, profile: dict, role: str, stage: str) -> dict:
    jskills = list(job.skills or [])
    text = (job.title + " " + (job.description or "")[:1500]).lower()
    title_l = job.title.lower()
    cnt = extract_skills(job.title + "\n" + (job.description or "")[:3000])
    matched, missing, tot, got = [], [], 0.0, 0.0
    for s in jskills:
        w = min(3, cnt.get(s, 1)) * (2 if s in title_l else 1)
        tot += w
        if s in profile["ctx"]:
            got += w
            matched.append(s)
        elif s in profile["all"]:
            got += 0.75 * w
            matched.append(s)
        else:
            missing.append((w, s))
    skill_score = (got / tot) if tot else 0.0
    if len(jskills) < 3:
        skill_score = 0.5 * skill_score + 0.5 * 0.35
    rp = ROLES[role]
    role_hit = 1.0 if any(t in title_l for t in rp["titles"]) else 0.0
    rw = role_weights(role)
    overlap = len(set(jskills) & {s for s, w in rw.items() if w >= 2})
    role_score = max(role_hit, min(0.8, overlap / 4))
    senior, junior = bool(SENIOR_RE.search(job.title)), bool(JUNIOR_RE.search(job.title)) or job.kind == "internship"
    if stage == "fresher":
        level = 1.0 if junior else (0.15 if senior else 0.55)
    elif stage == "early":
        level = 0.2 if senior and "lead" in title_l else (0.6 if job.kind == "internship" else 0.9)
    else:
        level = 0.2 if job.kind == "internship" else (1.0 if senior else 0.8)
    recency = 0.4
    if job.posted_at:
        pa = job.posted_at if job.posted_at.tzinfo else job.posted_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - pa).days
        recency = 1.0 if age <= 14 else 0.7 if age <= 30 else 0.4
    score = round(100 * (0.55 * skill_score + 0.25 * role_score + 0.15 * level + 0.05 * recency))
    reasons = []
    if role_hit:
        reasons.append(f"Title fits {role}")
    if matched:
        reasons.append(f"{len(matched)} skill match" + ("es" if len(matched) != 1 else ""))
    if stage == "fresher" and junior:
        reasons.append("Entry-level friendly")
    if stage == "fresher" and senior:
        reasons.append("Senior role, likely too advanced")
    return {"score": max(0, min(100, score)), "matched": matched[:8], "missing": [s for _, s in sorted(missing, reverse=True)][:6], "reasons": reasons}
