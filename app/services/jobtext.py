"""Understand a pasted job description (no AI needed) and build a personalised message from resume evidence."""
from __future__ import annotations

import re

from .ats import find_metrics
from .resume_parser import EMAIL_RE
from .skills import ROLES, extract_skills

_ROLE_WORD = re.compile(r"\b(engineer|developer|intern(?:ship)?|analyst|scientist|designer|manager|architect|consultant|tester|sde|programmer|"
                        r"specialist|associate|trainee|researcher|administrator|lead|devops|sre|qa)\b", re.I)
_NOISE = re.compile(r"we are|we're|looking for|responsib|requirement|qualif|about the|apply|posted|job description|who you|what you|benefit", re.I)
_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)[^.\n]{0,40}experience|experience[^.\n]{0,30}?(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I)


def _label(lines, names):
    pat = re.compile(rf"^(?:{names})\s*[:\-\u2013]\s*(.+)$", re.I)
    for ln in lines[:40]:
        m = pat.match(ln)
        if m:
            return m.group(1).strip(" .|")[:90]
    return ""


def analyze_jd(text: str) -> dict:
    text = (text or "").strip()
    lines = [re.sub(r"^[\s\u2022\-\u2013|*#]+", "", ln).strip() for ln in text.splitlines() if ln.strip()]
    role = _label(lines, r"job\s*title|position|role|designation|title|opening")
    company = _label(lines, r"company|organi[sz]ation|employer|hiring company|client")
    location = _label(lines, r"location|work location|city|place")
    if not role:
        for ln in lines[:8]:
            if _ROLE_WORD.search(ln) and len(ln.split()) <= 12 and not _NOISE.search(ln):
                role = ln.split(" at ")[0].split(" | ")[0].split(" - ")[0].strip(" -|")[:90]
                break
    if not role:
        m = re.search(r"hiring (?:a|an)?\s*([A-Za-z/&+ .-]{3,50}?)(?: at |,|\.|\n| to )", text[:800], re.I)
        role = m.group(1).strip() if m else ""
    if not company:
        for pat in (r"\b(?:join|about)\s+([A-Z][\w&.\-]*(?: [A-Z][\w&.\-]*){0,3})", r"^([A-Z][\w&.\-]*(?: [A-Z][\w&.\-]*){0,3}) (?:is|are) (?:hiring|looking|seeking)",
                    r"\bat\s+([A-Z][\w&.\-]*(?: [A-Z][\w&.\-]*){0,3})(?=[,.\n]| is | are | and | to |$)"):
            m = re.search(pat, text[:900], re.M)
            if m:
                company = m.group(1).strip()
                break
        if not company and " at " in (lines[0] if lines else ""):
            company = lines[0].split(" at ", 1)[1].strip()[:60]
    skills = [s for s, _ in extract_skills(text).most_common(20)]
    ym = _YEARS.search(text)
    head = (role + " " + text[:300]).lower()
    kind = "internship" if re.search(r"\bintern(?:ship)?\b|\btrainee\b", head) else "freelance" if re.search(r"freelanc|contract", head) else "job"
    em = EMAIL_RE.search(text)
    remote = bool(re.search(r"\bremote\b", text, re.I))
    return {"role": role, "company": company, "location": location or ("Remote" if remote else ""), "skills": skills,
            "years": int(next(g for g in ym.groups() if g)) if ym else None, "contact_email": em.group(0) if em else "", "kind": kind,
            "remote": remote, "words": len(text.split())}


def fit_summary(parsed: dict, jd_skills: list[str]) -> dict:
    ctx, anyw = set(parsed["skills"]["in_context"]), set(parsed["skills"]["all"])
    matched = [s for s in jd_skills if s in ctx]
    listed = [s for s in jd_skills if s in anyw and s not in ctx]
    missing = [s for s in jd_skills if s not in anyw]
    pct = round(100 * (len(matched) + 0.6 * len(listed)) / len(jd_skills)) if jd_skills else None
    return {"matched": matched, "listed_only": listed, "missing": missing, "score": pct}


def proof_points(parsed: dict, jd_skills: list[str], limit: int = 3) -> list[dict]:
    """Best resume lines to quote: share JD skills, contain real metrics, come from internships/work first."""
    want = set(jd_skills)
    cands = []
    for group, entries in (("experience", parsed["experience"]), ("project", parsed["projects"])):
        for e in entries:
            label = e.get("org") or e.get("heading") or ""
            kind = "internship" if e.get("kind") == "internship" else ("job" if group == "experience" else "project")
            for b in e["bullets"]:
                hit = sorted(set(extract_skills(b)) & want)
                metric = bool(find_metrics(b))
                if not hit and not metric:
                    continue
                score = 2 * len(hit) + (1.5 if metric else 0) + (1.0 if kind in ("internship", "job") else 0.3)
                cands.append((score, {"text": b.strip().rstrip("."), "source": label[:60], "kind": kind, "skills": hit, "has_metric": metric}))
    cands.sort(key=lambda x: -x[0])
    out, per = [], {}
    for _, c in cands:
        if per.get(c["source"], 0) >= 2:
            continue
        per[c["source"]] = per.get(c["source"], 0) + 1
        out.append(c)
        if len(out) >= limit:
            break
    return out


def credentials(parsed: dict, jd_skills: list[str]) -> list[str]:
    want = set(jd_skills)
    order = {"vendor": 0, "platform": 1, "unknown": 2}
    certs = sorted(parsed["certifications"], key=lambda c: order[c["tier"]])
    rel = [c["name"] for c in certs if set(extract_skills(c["name"])) & want]
    return (rel or [c["name"] for c in certs if c["tier"] == "vendor"])[:2]


# ------------------------------------------------------------------ template (non-AI) writer
TONES = {"concise": ("Hi,", "Thanks,"), "friendly": ("Hi there,", "Thanks so much,"), "formal": ("Dear Hiring Manager,", "Sincerely,")}


def _first_clause(t: str, n: int = 190) -> str:
    t = t.strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "\u2026"


def compose_template(kind: str, tone: str, user, role: str, company: str, matched: list[str], proof: list[dict], creds: list[str]) -> dict:
    greet, close = TONES.get(tone, TONES["concise"])
    name = user.name
    comp = company or "your team"
    role = role or "the open role"
    sk = ", ".join(matched[:4])
    who = name + (f", {user.degree} at {user.college}" if user.degree and user.college else "")
    links = " | ".join(x for x in (user.linkedin, user.github, user.portfolio) if x)
    pp = [f"\u2022 {_first_clause(p['text'])}" + (f" ({p['source']})" if p["source"] else "") for p in proof]
    if kind == "linkedin_dm":
        proofs = f" Recently: {_first_clause(proof[0]['text'], 110)}." if proof else ""
        return {"subject": "", "body": f"Hi, I'm {name}. I'm applying for {role} at {comp} and work with {sk or 'the same stack'}.{proofs} Could you point me to the right person or share a referral? Thank you!"[:300]}
    if kind == "referral":
        return {"subject": "", "body": f"{greet}\n\nI'm {who}. I'm interested in the {role} opening at {comp}. " + (f"My experience with {sk} lines up well" if sk else "My background lines up well") +
                (f", for example:\n" + "\n".join(pp[:2]) if pp else ".") + f"\n\nWould you be open to referring me or telling me what the team values? Happy to send my resume.\n\n{close}\n{name}"}
    if kind == "cover_letter":
        return {"subject": "", "body": f"Dear Hiring Team at {comp},\n\nI am applying for the {role} position. " + (f"The role's focus on {sk} matches the work I have done.\n\n" if sk else "\n\n") +
                ("\n".join(pp) + "\n\n" if pp else "") + (f"I also hold {creds[0]}.\n\n" if creds else "") + f"I would welcome a conversation about how I can contribute.\n\nSincerely,\n{name}" + (f"\n{links}" if links else "")}
    subject = f"{role} \u2013 {name}" + (f" ({', '.join(matched[:2])})" if matched else "")
    body = f"{greet}\n\nI'm {who}. I saw the {role} opening at {comp} and it matches my work in {sk or 'this area'}.\n\n" + ("\n".join(pp) + "\n\n" if pp else "") + \
           (f"I also hold {creds[0]}.\n\n" if creds and tone != "concise" else "") + "Could we have a short call, or could you point me to the right person? My resume is attached." + \
           f"\n\n{close}\n{name}" + (f"\n{links}" if links else "")
    return {"subject": subject[:160], "body": body}
