"""Evidence-based ATS / resume scoring.

The score is deterministic and explainable: each component returns a 0..1 fraction
and a list of findings that carry the evidence (original lines) and a concrete fix.
Weights adapt to the candidate's career stage so a fresher is judged on projects,
internships, open source and credentials, while an experienced candidate is judged
mostly on work history and measurable impact.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date

from .resume_parser import RANGE_RE, SINGLE_RE
from .skills import ROLES, extract_skills, normalize_role, role_weights, skill_category, CATEGORY_LABELS

WEIGHTS = {
    "fresher":     dict(parse=10, contact=6, structure=8, experience=14, projects=14, skills=16, impact=8, writing=8, education=6, certs=4, oss=4, achievements=2),
    "early":       dict(parse=10, contact=6, structure=8, experience=24, projects=8, skills=16, impact=10, writing=8, education=4, certs=3, oss=2, achievements=1),
    "experienced": dict(parse=10, contact=6, structure=8, experience=30, projects=4, skills=16, impact=12, writing=8, education=2, certs=2, oss=1, achievements=1),
}
for _w in WEIGHTS.values():
    assert sum(_w.values()) == 100

LABELS = {
    "parse": "ATS readability", "contact": "Contact & links", "structure": "Structure & dates",
    "experience": "Experience & internships", "projects": "Projects", "skills": "Role keyword match",
    "impact": "Measurable impact", "writing": "Bullet writing", "education": "Education",
    "certs": "Certifications", "oss": "Open source", "achievements": "Achievements",
}
STAGE_LABEL = {"fresher": "Fresher / student", "early": "Early career", "experienced": "Experienced"}

ACTION_VERBS = set("""
accelerated achieved acquired adapted administered advised analyzed analysed announced architected assembled
audited authored automated boosted brought built calculated captured chaired championed clarified coached collaborated
compiled completed composed conceived conducted configured consolidated constructed consulted containerized contributed
converted coordinated created curated debugged decreased defined delivered deployed derived designed detected developed
devised diagnosed directed discovered documented doubled drove edited eliminated enabled encrypted engineered enhanced
established evaluated executed expanded expedited extended extracted fabricated facilitated finalized fine-tuned finetuned
fixed forecasted formulated founded gathered generated guided handled identified implemented improved increased influenced
initiated innovated inspected installed instituted integrated interpreted introduced investigated launched led leveraged
maintained managed mapped mentored merged migrated mined minimized modeled modelled modernized monitored negotiated
operated optimised optimized orchestrated organised organized overhauled owned partnered performed pioneered planned
presented prioritized processed produced programmed prototyped provisioned published queried raised rebuilt recommended
reconciled recruited redesigned reduced refactored refined released remodeled replaced reported researched resolved
restructured retrieved revamped reviewed revised rewrote scaled scheduled scripted secured selected served shipped simplified
simulated solved spearheaded standardized streamlined strengthened submitted supervised supported surveyed synthesized
tailored taught tested tracked trained transformed translated troubleshot tuned unified upgraded validated visualized
won wrote benchmarked bootstrapped orchestrated ported profiled instrumented annotated cleaned trained evaluated demoed
organised hosted ran spoke volunteered contributed reproduced""".split())
WEAK_STARTS = {"worked", "helped", "assisted", "involved", "participated", "tasked", "responsible", "duties", "learned", "learnt", "used", "did", "made", "got"}
WEAK_PHRASES = [r"responsible for", r"worked on", r"helped (?:with|to|the)", r"assisted (?:in|with|the)", r"involved in",
                r"duties (?:included|include)", r"tasked with", r"participated in", r"familiar with", r"knowledge of",
                r"exposure to", r"various", r"\betc\.?\b", r"good understanding", r"hard[- ]?working", r"quick learner",
                r"team player", r"passionate about", r"looking for", r"seeking"]
WEAK_RE = re.compile("|".join(WEAK_PHRASES), re.I)
PRONOUN_RE = re.compile(r"\b(?:i|my|me|myself)\b", re.I)

_UNITS = (r"users|customers|requests|queries|records|rows|samples|images|documents|files|endpoints|apis?|models|tests|test cases|"
          r"students|members|participants|teams|developers|engineers|clients|downloads|stars|forks|prs|commits|resumes|tickets|"
          r"transactions|orders|sessions|visitors|datasets|pages|services|microservices|modules|features|components|screens|"
          r"pipelines|jobs|events|messages|classes|papers|articles|issues|bugs|vulnerabilities|reviews|projects|contributors|"
          r"vendors|stores|sensors|nodes|containers|alerts|dashboards|reports|assets|hosts|ports|devices|applications|apps|"
          r"classes|labels|categories|languages|countries|cities|institutions|colleges|startups")
METRIC_PATTERNS = [
    re.compile(r"\d+(?:\.\d+)?\s?%"),
    re.compile(r"[\u20b9$\u20ac\xa3]\s?\d[\d,.]*\s?(?:k|m|mn|cr|crore|lakh|lakhs|lpa|bn|b)?\b", re.I),
    re.compile(r"\b(?:rs\.?|inr|usd)\s?\d[\d,.]*", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s?[x\u00d7](?!\w)"),
    re.compile(rf"\b\d[\d,.]*\+?\s?(?:k|m|mn|million|billion)?\+?\s+(?:[\w\-/]+\s+){{0,2}}(?:{_UNITS})\b", re.I),
    re.compile(r"\b\d[\d,.]*\s?(?:ms|milliseconds|seconds|secs?|minutes|mins|hours|hrs|days|weeks|months|gb|mb|tb|kb|fps|rps|qps|tps)\b", re.I),
    re.compile(r"\b(?:accuracy|precision|recall|f1(?:-score)?|auc|map|bleu|rouge|rmse|mae|r2|r\u00b2)\b[^.\n]{0,25}\d", re.I),
    re.compile(r"\bfrom\s+\d[\d.,]*\s*(?:%|ms|s|x)?\s+to\s+\d", re.I),
    re.compile(r"\b\d[\d,]*\s?(?:\+|k\+)(?!\w)"),
]


def find_metrics(text: str) -> list[str]:
    t = RANGE_RE.sub(" ", text)
    t = SINGLE_RE.sub(" ", t)
    t = re.sub(r"\b(?:python|java|node|angular|react|vue|tls|http|ipv|c|sha|md|iso|py|es|tensorflow|pytorch)\s?\d+(?:\.\d+)*", " ", t, flags=re.I)
    out = []
    for pat in METRIC_PATTERNS:
        for m in pat.finditer(t):
            out.append(m.group(0).strip())
    return out


def F(sev, cat, title, detail="", fix="", evidence=None, points=0.0, fid=None):
    return {"id": fid or re.sub(r"\W+", "_", title.lower())[:40], "severity": sev, "category": cat, "title": title,
            "detail": detail, "fix": fix, "evidence": evidence or [], "points_at_stake": round(points, 1)}


def _clip(s: str, n=140):
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "\u2026"


# ------------------------------------------------------------------ stage
def stage_of(p: dict) -> str:
    t = p["totals"]
    eff = t["work_months"] + 0.5 * t["internship_months"]
    gy = p["education"].get("grad_year")
    today = date.today()
    if eff < 6 or (gy and gy >= today.year and eff < 12):
        return "fresher"
    if eff < 36:
        return "early"
    return "experienced"


# ------------------------------------------------------------------ components
def c_parse(p, stage):
    d = p["doc"]
    f, frac = [], 1.0
    w = WEIGHTS[stage]["parse"]
    if d["fmt"] == "pdf" and d["chars_per_page"] < 250:
        f.append(F("critical", "parse", "Little or no selectable text found",
                   "This looks like a scanned image or a PDF exported with text as pictures. ATS systems read nothing from it.",
                   "Export a text-based PDF from Word/Google Docs/LaTeX (you should be able to select and copy the text).", points=w))
        return 0.05, f
    if d["multi_column"]:
        frac -= 0.25
        f.append(F("warning", "parse", "Multi-column layout detected",
                   "Many ATS parsers read columns in the wrong order, mixing skills with experience lines.",
                   "Use a single-column layout. Keep dates right-aligned on the same line instead of using a sidebar.", points=w * 0.25))
    if d["tables"]:
        frac -= 0.2
        f.append(F("warning", "parse", f"Table structure detected ({d['tables']})",
                   "Tables are flattened unpredictably by parsers, so dates and titles can detach from their entries.",
                   "Replace tables with plain paragraphs and tab-aligned dates.", points=w * 0.2))
    if d["text_boxes"]:
        frac -= 0.25
        f.append(F("warning", "parse", "Text boxes found",
                   "Content inside Word text boxes is skipped by most ATS parsers.", "Move that content into the normal document body.", points=w * 0.25))
    hf = d.get("header_footer_text", "")
    if hf:
        frac -= 0.1
        f.append(F("warning", "parse", "Content placed in the document header/footer",
                   "Parsers often ignore headers and footers, so contact details placed there can disappear.",
                   "Put your name and contact line in the main body at the top.", evidence=[_clip(hf, 90)], points=w * 0.1))
    if d["garbled_ratio"] > 0.02:
        frac -= 0.2
        f.append(F("warning", "parse", "Garbled characters in extracted text",
                   "Some glyphs did not extract as normal text (custom fonts or symbol fonts).",
                   "Use a standard font (Calibri, Arial, Garamond, Helvetica) and standard bullets.", points=w * 0.2))
    if d["private_use_bullets"]:
        frac -= 0.05
        f.append(F("info", "parse", "Symbol-font bullets",
                   "Your bullets use a symbol font (e.g. Wingdings). They extracted fine here but can turn into odd characters elsewhere.",
                   "Use the default round bullet from Word/Docs.", points=w * 0.05))
    if d["images"] > 0:
        frac -= 0.05
        f.append(F("info", "parse", f"{d['images']} image(s) embedded",
                   "Photos, icons and skill-bar graphics are invisible to ATS and add nothing for recruiters in India/US/EU roles.",
                   "Remove the photo and replace skill bars/icons with plain text.", points=w * 0.05))
    pages, months = d["pages"], p["totals"]["experience_months"]
    max_pages = 1 if stage == "fresher" else 2
    if pages > max_pages + (1 if stage == "experienced" else 0):
        frac -= 0.15
        f.append(F("warning", "parse", f"Resume is {pages} pages",
                   f"For a {STAGE_LABEL[stage].lower()} profile recruiters expect about {max_pages} page(s).",
                   "Cut older/low-signal content; keep strongest 3-4 bullets per role.", points=w * 0.15))
    words = p["totals"]["words"]
    lo, hi = {"fresher": (250, 700), "early": (350, 900), "experienced": (450, 1100)}[stage]
    if words < lo:
        frac -= 0.1
        f.append(F("warning", "parse", f"Very short content ({words} words)",
                   f"Resumes in this range usually have {lo}-{hi} words; too little gives ATS little to match.",
                   "Add project details, tools used and outcomes.", points=w * 0.1))
    elif words > hi:
        frac -= 0.08
        f.append(F("info", "parse", f"Long content ({words} words)", "Dense resumes get skimmed, not read.", "Trim to the most relevant material.", points=w * 0.08))
    if d["fmt"] == "pdf" and not f:
        f.append(F("good", "parse", "Clean, parseable layout",
                   "Single column, selectable text and no tables/text boxes detected.", fid="parse_ok"))
    return max(0.0, frac), f


def c_contact(p, stage, role):
    c = p["contact"]
    w = WEIGHTS[stage]["contact"]
    f, frac = [], 0.0
    if c["email"]:
        frac += 0.35
        local = c["email"].split("@")[0].lower()
        if re.search(r"cool|sexy|hot|baby|lover|dude|swag|king|queen|boy|girl|\d{5,}|xx", local):
            f.append(F("info", "contact", "Email looks informal", "Recruiters filter on professionalism.", "Use name-based email, e.g. firstname.lastname@gmail.com.", evidence=[c["email"]]))
    else:
        f.append(F("critical", "contact", "No email address found", "Recruiters and ATS use the email as your unique ID.", "Add a professional email in the top block.", points=w * 0.35))
    if c["phone"]:
        frac += 0.2
    else:
        f.append(F("warning", "contact", "No phone number found", "Most Indian campus/HR workflows still call first.", "Add a phone number with country code.", points=w * 0.2))
    if c["linkedin"]:
        frac += 0.2
        if not c["linkedin_clickable"] and p["doc"]["fmt"] == "pdf" and c["links_clickable"] == 0:
            f.append(F("info", "contact", "Links are plain text, not clickable", "Recruiters click LinkedIn/GitHub straight from the PDF.", "Insert real hyperlinks (Ctrl+K in Word/Docs) before exporting."))
    else:
        f.append(F("warning", "contact", "LinkedIn profile missing", "Recruiters cross-check LinkedIn on almost every shortlist.", "Add your linkedin.com/in/... URL.", points=w * 0.2))
    tech = role not in ("UI / UX Designer",)
    if c["github"] or c["portfolio"]:
        frac += 0.15
    elif tech:
        f.append(F("warning", "contact", "No GitHub or portfolio link", "Technical recruiters want proof of work.", "Add GitHub (with pinned repos) or a portfolio URL.", points=w * 0.15))
    else:
        f.append(F("warning", "contact", "No portfolio link", "Design roles are screened on portfolio first.", "Add Behance/Dribbble/portfolio URL.", points=w * 0.15))
    if c["location"]:
        frac += 0.1
    else:
        f.append(F("info", "contact", "No city/location found", "Location filters are common in Indian hiring.", "Add 'City, State' in the header.", points=w * 0.1))
    if not c["name"]:
        f.append(F("warning", "contact", "Name not detected at the top", "ATS profile creation fails or mislabels the candidate.", "Put your full name as the first line, alone."))
    return min(1.0, frac), f


def c_structure(p, stage):
    w = WEIGHTS[stage]["structure"]
    secs = set(p["sections_found"])
    has_exp = bool(secs & {"experience", "internships"})
    expected = {"fresher": ["education", "skills", "projects", "exp"],
                "early": ["experience", "education", "skills", "projects"],
                "experienced": ["experience", "education", "skills"]}[stage]
    present, missing = 0, []
    for e in expected:
        ok = has_exp if e == "exp" else (e in secs or (e == "experience" and has_exp))
        if ok:
            present += 1
        else:
            missing.append("experience/internships" if e == "exp" else e)
    f = []
    if missing:
        f.append(F("warning" if len(missing) < 3 else "critical", "structure", "Standard sections not found: " + ", ".join(missing),
                   "ATS maps text to sections by heading. Unusual or missing headings lose that content.",
                   "Use plain headings: Experience, Education, Projects, Skills, Certifications.", points=w * 0.7 * len(missing) / len(expected)))
    exps = [e for e in p["experience"]]
    dated = [e for e in exps if e["start"]]
    dated_ratio = len(dated) / len(exps) if exps else 1.0
    if exps and dated_ratio < 1:
        f.append(F("warning", "structure", f"{len(exps) - len(dated)} experience entr{'y' if len(exps) - len(dated) == 1 else 'ies'} without parseable dates",
                   "Without dates the ATS cannot compute your years of experience.", "Use 'Mon YYYY - Mon YYYY' on every role.",
                   evidence=[_clip(e["heading"]) for e in exps if not e["start"]][:3], points=w * 0.15))
    chrono = 1.0
    starts = [(e["start"][0] * 12 + e["start"][1]) for e in dated]
    if len(starts) >= 2 and starts != sorted(starts, reverse=True):
        chrono = 0.0
        f.append(F("info", "structure", "Experience is not in reverse-chronological order",
                   "Recruiters and ATS expect the most recent role first.", "Reorder entries newest to oldest."))
    for g in p["gaps"][:2]:
        f.append(F("info", "structure", f"~{g['months']} month gap in timeline after {g['after']}", "Unexplained gaps get questions.",
                   "Add what you did (course, project, freelance, preparation) if relevant."))
    if "summary" not in secs and stage != "fresher":
        f.append(F("info", "structure", "No professional summary", "A 2-line summary helps recruiters and gives ATS extra keywords.", "Add a 2-3 line summary with role, years and top skills."))
    frac = 0.7 * present / len(expected) + 0.15 * dated_ratio + 0.15 * chrono
    if not f:
        f.append(F("good", "structure", "Standard sections and dates are well formed", "", fid="structure_ok"))
    return min(1.0, frac), f


def _entry_quality(e) -> float:
    b = e["bullets"]
    if not b:
        return 0.0
    n = min(1.0, len(b) / 3.5)
    ver = sum(1 for x in b if _starts_with_verb(x)) / len(b)
    met = sum(1 for x in b if find_metrics(x)) / len(b)
    return 0.4 * n + 0.3 * ver + 0.3 * min(1.0, met / 0.5)


def c_experience(p, stage):
    w = WEIGHTS[stage]["experience"]
    t, exps = p["totals"], p["experience"]
    f = []
    target = {"fresher": 3, "early": 24, "experienced": 60}[stage]
    eff = t["work_months"] + 0.8 * t["internship_months"]
    if not exps:
        if stage == "fresher":
            f.append(F("warning", "experience", "No internship or work experience found",
                       "Recruiters for entry-level roles weigh internships heavily, and ATS filters often require 'experience'.",
                       "Add any of: internship, freelance project for a real client, virtual experience program (e.g. Forage), research assistantship, open-source contribution with merged PRs.",
                       points=w))
        else:
            f.append(F("critical", "experience", "No work experience section detected",
                       "This is the most heavily weighted part of the resume.", "Add an 'Experience' heading with role, company, dates and bullets.", points=w))
        return 0.0, f
    top = sorted(exps, key=lambda e: -(e["months"] or 0))[:4]
    quality = sum(_entry_quality(e) for e in top) / len(top)
    frac = 0.55 * min(1.0, eff / target) + 0.45 * quality
    ints = [e for e in exps if e["kind"] == "internship"]
    if ints:
        total = t["internship_months"]
        f.append(F("good", "experience", f"{len(ints)} internship{'s' if len(ints) > 1 else ''} found ({total} month{'s' if total != 1 else ''} total)",
                   "Internships are a strong signal for early-career screening.", evidence=[_clip(e["heading"] + " " + e["date_text"]) for e in ints][:3], fid="internships_ok"))
        short = [e for e in ints if 0 < e["months"] < 2]
        if short:
            f.append(F("info", "experience", "Very short internship duration", "Under 2 months reads as a micro-internship.",
                       "Emphasise concrete outcomes and the stack you shipped.", evidence=[_clip(e["heading"] + " " + e["date_text"]) for e in short][:2]))
    elif stage == "fresher":
        f.append(F("warning", "experience", "No internship detected", "Work entries exist but none is labelled internship/trainee.", "Label internships explicitly in the title (e.g. 'Backend Intern').", points=w * 0.15))
    nobul = [e for e in exps if not e["bullets"]]
    if nobul:
        f.append(F("warning", "experience", f"{len(nobul)} role(s) without bullet points", "A title and dates alone give ATS no keywords and recruiters no proof.",
                   "Add 3-4 achievement bullets with tools and numbers.", evidence=[_clip(e["heading"]) for e in nobul][:3], points=w * 0.2))
    thin = [e for e in exps if 0 < len(e["bullets"]) < 2]
    if thin:
        f.append(F("info", "experience", "Roles with only one bullet", "Two to four bullets per role is the norm.", "Expand with scope, tools and results.", evidence=[_clip(e["heading"]) for e in thin][:3]))
    if stage != "fresher" and eff < target:
        f.append(F("info", "experience", f"~{round(eff / 12, 1)} years of detected experience", "Most mid-level job posts ask for more; make sure all dates are captured.", ""))
    return min(1.0, frac), f


def c_projects(p, stage):
    w = WEIGHTS[stage]["projects"]
    prj = p["projects"]
    target = {"fresher": 3, "early": 2, "experienced": 1}[stage]
    f = []
    if not prj:
        sev = "warning" if stage != "experienced" else "info"
        f.append(F(sev, "projects", "No projects section detected",
                   "Projects are your proof of skill when experience is limited." if stage == "fresher" else "Side projects can still back up skills you list.",
                   "Add 2-3 projects: what you built, stack, scale/result and a GitHub or live link.", points=w))
        return 0.0, f
    qs, weak = [], []
    for e in prj:
        blob = " ".join(e["bullets"])
        has_tech = bool(e["tech"]) or len(extract_skills(e["heading"] + " " + blob)) >= 2
        has_link = bool(e["urls"])
        nb = len(e["bullets"])
        has_metric = any(find_metrics(b) for b in e["bullets"])
        q = 0.3 * has_tech + 0.2 * has_link + 0.25 * min(1.0, nb / 2) + 0.25 * has_metric
        qs.append(q)
        gaps = []
        if not has_tech:
            gaps.append("tech stack")
        if not has_link:
            gaps.append("link")
        if nb < 2:
            gaps.append("2+ detail bullets")
        if not has_metric:
            gaps.append("a number/result")
        if gaps:
            weak.append(f"{_clip(e['heading'], 50)} - missing {', '.join(gaps)}")
    qs_sorted = sorted(qs, reverse=True)[:target]
    frac = 0.5 * min(1.0, len(prj) / target) + 0.5 * (sum(qs_sorted) / len(qs_sorted))
    if len(prj) < target:
        f.append(F("warning", "projects", f"{len(prj)} project(s) found, aim for {target}", "", "Add projects that match the target role's core stack.", points=w * 0.3))
    if weak:
        f.append(F("warning", "projects", "Projects missing proof points",
                   "The best project entries state stack, link, scale and result.", "Add the missing items for each project.", evidence=weak[:4], points=w * 0.3))
    else:
        f.append(F("good", "projects", f"{len(prj)} well-documented projects", "", fid="projects_ok"))
    return min(1.0, frac), f


def _credit(status):
    return {"context": 1.0, "listed": 0.6, "missing": 0.0}[status]


def role_report(p, role):
    weights = role_weights(role)
    ctx = set(p["skills"]["in_context"])
    listed = set(p["skills"]["listed"])
    anywhere = set(p["skills"]["all"])
    rows = []
    for s, wgt in sorted(weights.items(), key=lambda x: -x[1]):
        status = "context" if s in ctx else ("listed" if (s in listed or s in anywhere) else "missing")
        rows.append({"skill": s, "weight": wgt, "status": status, "category": skill_category(s)})
    tot = sum(r["weight"] for r in rows) or 1
    cov = sum(r["weight"] * _credit(r["status"]) for r in rows) / tot
    by_cat = {}
    for r in rows:
        c = CATEGORY_LABELS.get(r["category"], r["category"])
        by_cat.setdefault(c, [0, 0])
        by_cat[c][0] += r["weight"] * _credit(r["status"])
        by_cat[c][1] += r["weight"]
    return {"role": role, "coverage": round(cov, 3), "rows": rows,
            "categories": {k: round(a / b, 2) for k, (a, b) in by_cat.items() if b}}


def c_skills(p, stage, role):
    w = WEIGHTS[stage]["skills"]
    rr = role_report(p, role)
    f = []
    frac = min(1.0, rr["coverage"] / 0.8)
    core_missing = [r["skill"] for r in rr["rows"] if r["weight"] == 3 and r["status"] == "missing"]
    imp_missing = [r["skill"] for r in rr["rows"] if r["weight"] == 2 and r["status"] == "missing"]
    listed_only = [r["skill"] for r in rr["rows"] if r["status"] == "listed" and r["weight"] >= 2]
    ok_ctx = [r["skill"] for r in rr["rows"] if r["status"] == "context"]
    if core_missing:
        f.append(F("critical" if len(core_missing) >= 3 else "warning", "skills", f"Core {role} keywords missing: " + ", ".join(core_missing[:6]),
                   "These are the highest-weighted terms recruiters and ATS search for this role.",
                   "If you genuinely have them, add to Skills and show them inside a project/experience bullet. If not, learn them first and build one project.",
                   points=w * 0.5 * len(core_missing) / max(1, sum(1 for r in rr["rows"] if r["weight"] == 3))))
    if imp_missing:
        f.append(F("info", "skills", "Important skills not found: " + ", ".join(imp_missing[:6]), "", "Add those you actually use; you do not need all of them."))
    if listed_only:
        f.append(F("warning", "skills", f"{len(listed_only)} role skills are listed but never shown in use: " + ", ".join(listed_only[:6]),
                   "Skills listed without evidence are discounted by recruiters and by 'keyword in context' ATS ranking.",
                   "Mention each in a bullet: 'Built X with <skill> to achieve Y'.", points=w * 0.2))
    n_listed = len(p["skills"]["listed"])
    noctx = [s for s in p["skills"]["listed"] if s not in p["skills"]["in_context"]]
    if p["skills"]["raw_item_count"] > 45 or n_listed > 35 or (n_listed >= 14 and len(noctx) / n_listed > 0.75 and p["totals"]["bullets"] > 0):
        f.append(F("warning", "skills", "Skills list looks stuffed",
                   f"{n_listed} skills detected, {len(noctx)} with no supporting project/experience line.",
                   "Keep 12-20 skills you can defend in an interview, grouped by category.", points=w * 0.1))
    if not p["skills"]["has_section"]:
        f.append(F("critical", "skills", "No Skills section found", "ATS keyword extraction relies on a labelled skills block.", "Add 'Skills' with categories: Languages, Frameworks, Databases, Tools."))
    if ok_ctx and len(ok_ctx) >= 5:
        f.append(F("good", "skills", f"{len(ok_ctx)} role skills are backed by project/experience evidence", "", evidence=ok_ctx[:8], fid="skills_ctx_ok"))
    return frac, f, rr


def _starts_with_verb(b: str) -> bool:
    w = re.match(r"[A-Za-z\-']+", b.strip())
    if not w:
        return False
    w = w.group(0).lower()
    if w in WEAK_STARTS:
        return False
    return w in ACTION_VERBS or (w.endswith("ed") and len(w) > 4)


def c_impact(p, stage):
    w = WEIGHTS[stage]["impact"]
    bullets = [b for e in p["experience"] + p["projects"] for b in e["bullets"]]
    f = []
    if len(bullets) < 4:
        f.append(F("warning", "impact", "Too few bullets to show impact", "", "Write 3-4 outcome-focused bullets per role/project.", points=w * 0.6))
        return min(1.0, len(bullets) / 8), f
    with_m = [(b, find_metrics(b)) for b in bullets]
    hit = [x for x in with_m if x[1]]
    miss = [b for b, m in with_m if not m]
    ratio = len(hit) / len(bullets)
    target = {"fresher": 0.3, "early": 0.4, "experienced": 0.5}[stage]
    frac = min(1.0, ratio / target)
    pct = round(ratio * 100)
    if ratio < target:
        f.append(F("warning" if ratio < target * 0.6 else "info", "impact", f"Only {pct}% of bullets contain a real metric (target {round(target * 100)}%+)",
                   "Years, phone numbers and CGPA are not counted. Metrics are: %, counts of users/requests/records, latency, cost, time saved, accuracy/F1.",
                   "Rewrite as 'Action + what + tool + measurable result'. If you lack data, estimate honestly (e.g. 'served ~200 students').",
                   evidence=[_clip(b) for b in miss[:3]], points=w * (1 - frac)))
    else:
        f.append(F("good", "impact", f"{pct}% of bullets are quantified", "Strong evidence of impact.", evidence=[_clip(b) + "  [" + ", ".join(dict.fromkeys(m))[:40] + "]" for b, m in hit[:2]], fid="impact_ok"))
    return frac, f


def c_writing(p, stage):
    w = WEIGHTS[stage]["writing"]
    bullets = [b for e in p["experience"] + p["projects"] for b in e["bullets"]]
    f = []
    if not bullets:
        return 0.0, f
    n = len(bullets)
    verb = sum(1 for b in bullets if _starts_with_verb(b)) / n
    weak = [b for b in bullets if WEAK_RE.search(b) or re.match(r"(?:worked|helped|assisted|involved|participated|responsible|duties)", b.strip(), re.I)]
    pron = [b for b in bullets if PRONOUN_RE.search(b)]
    lens = [len(b.split()) for b in bullets]
    ok_len = sum(1 for x in lens if 8 <= x <= 32) / n
    toolish = sum(1 for b in bullets if extract_skills(b)) / n
    frac = 0.35 * verb + 0.25 * (1 - min(1.0, (len(weak) + len(pron)) / n * 2)) + 0.2 * ok_len + 0.2 * min(1.0, toolish / 0.6)
    if verb < 0.8:
        bad = [b for b in bullets if not _starts_with_verb(b)]
        f.append(F("warning", "writing", f"{round((1 - verb) * 100)}% of bullets don't start with a strong action verb", "Verb-first bullets scan faster and parse better.",
                   "Start with Built, Reduced, Designed, Automated, Deployed...", evidence=[_clip(b) for b in bad[:3]], points=w * 0.35 * (1 - verb)))
    if weak:
        f.append(F("warning", "writing", f"{len(weak)} bullet(s) use weak phrasing", "Phrases like 'responsible for' / 'worked on' describe duties, not results.",
                   "Replace with what you changed and the outcome.", evidence=[_clip(b) for b in weak[:3]], points=w * 0.25))
    if pron:
        f.append(F("info", "writing", "First-person pronouns in bullets", "Resume bullets conventionally omit 'I/my'.", "Drop the pronoun and start with the verb.", evidence=[_clip(b) for b in pron[:2]]))
    long_ = [b for b, x in zip(bullets, lens) if x > 32]
    short = [b for b, x in zip(bullets, lens) if x < 8]
    if long_:
        f.append(F("info", "writing", f"{len(long_)} bullet(s) over 32 words", "Long bullets get skipped.", "Split into two or cut to one idea.", evidence=[_clip(b, 110) for b in long_[:2]]))
    if short:
        f.append(F("info", "writing", f"{len(short)} bullet(s) under 8 words", "Too thin to show scope.", "Add tool and result.", evidence=[_clip(b) for b in short[:2]]))
    starts = Counter(re.match(r"[A-Za-z\-']+", b).group(0).lower() for b in bullets if re.match(r"[A-Za-z\-']+", b))
    rep = [(v, c) for v, c in starts.items() if c >= 3 and n >= 8]
    if rep:
        f.append(F("info", "writing", "Repeated opening verb: " + ", ".join(f"'{v}' x{c}" for v, c in rep[:3]), "", "Vary your verbs (Developed, Engineered, Automated, Optimised)."))
    if not f:
        f.append(F("good", "writing", "Bullets are verb-led and concise", "", fid="writing_ok"))
    return max(0.0, min(1.0, frac)), f


def c_education(p, stage):
    w = WEIGHTS[stage]["education"]
    e = p["education"]
    f = []
    if not e["has_section"]:
        f.append(F("warning", "education", "No Education section found", "ATS degree filters need it.", "Add degree, institution and graduation year.", points=w))
        return 0.0, f
    frac = 0.4 * bool(e["degree"]) + 0.2 * e["institution_found"] + 0.2 * bool(e["grad_year"]) + 0.2 * (e["cgpa"] is not None or True)
    if stage == "fresher":
        frac = 0.35 * bool(e["degree"]) + 0.2 * e["institution_found"] + 0.2 * bool(e["grad_year"]) + 0.25 * (e["cgpa"] is not None)
        if e["cgpa"] is None:
            f.append(F("info", "education", "CGPA/percentage not shown", "Many campus drives filter on CGPA cut-offs.", "Add CGPA if it meets typical cut-offs (6.0-7.5/10).", points=w * 0.25))
        elif e["cgpa_scale"] == 10 and e["cgpa"] >= 8:
            f.append(F("good", "education", f"Strong CGPA ({e['cgpa']}/10)", "", fid="cgpa_ok"))
    if not e["degree"]:
        f.append(F("warning", "education", "Degree name not recognised", "", "Write the degree in a standard form, e.g. 'B.Tech in Computer Science'.", points=w * 0.4))
    if not e["grad_year"]:
        f.append(F("info", "education", "Graduation year not found", "", "Add expected or actual graduation year."))
    return min(1.0, frac), f


def c_certs(p, stage, role):
    w = WEIGHTS[stage]["certs"]
    certs = p["certifications"]
    target = {"fresher": 2.0, "early": 1.5, "experienced": 1.0}[stage]
    f = []
    rw = role_weights(role)
    if not certs:
        sug = ROLES[role]["certs"][:3]
        f.append(F("info", "certs", "No certifications detected", "Certifications are a tie-breaker for fresher screening and can add ATS keywords.",
                   "Consider (verify current availability): " + "; ".join(sug), points=w))
        return 0.0, f
    credit = {"vendor": 1.0, "platform": 0.7, "unknown": 0.5}
    s = sum(credit[c["tier"]] for c in certs)
    frac = min(1.0, s / target)
    rel = [c for c in certs if set(extract_skills(c["name"])) & set(rw) or any(k.lower().split()[0] in c["name"].lower() for k in ROLES[role]["certs"])]
    f.append(F("good", "certs", f"{len(certs)} certification(s) found" + (f", {len(rel)} relevant to {role}" if rel else ""), "",
               evidence=[f"{c['name'][:80]} [{c['tier']}]" for c in certs[:4]], fid="certs_ok"))
    if not rel:
        f.append(F("info", "certs", f"None of your certifications clearly match {role}", "Relevant certifications carry more weight than generic ones.",
                   "Consider (verify current availability): " + "; ".join(ROLES[role]["certs"][:3])))
    unk = [c for c in certs if c["tier"] == "unknown" and not c["verifiable"]]
    if unk:
        f.append(F("info", "certs", "Some certifications have no issuer or credential link", "Unverifiable items carry little weight.", "Add issuer and a credential URL/ID.", evidence=[c["name"][:70] for c in unk[:3]]))
    old = [c for c in certs if c["year"] and c["year"] <= date.today().year - 4]
    if old and len(old) == len(certs):
        f.append(F("info", "certs", "All certifications are 4+ years old", "Tech credentials age quickly.", "Add a recent one or note renewals."))
    return frac, f


def c_oss(p, stage):
    w = WEIGHTS[stage]["oss"]
    o = p["open_source"]
    f = []
    frac = {"none": 0.0, "weak": 0.2, "moderate": 0.6, "strong": 1.0}[o["level"]]
    if o["level"] == "strong":
        f.append(F("good", "oss", "Strong open-source signal", "Merged contributions or recognised programs stand out sharply.", evidence=o["evidence"][:3], fid="oss_ok"))
    elif o["level"] == "moderate":
        f.append(F("info", "oss", "Open-source mentioned, but not verifiable", "Recruiters look for merged PRs with links.",
                   "Add repo names and PR links, e.g. 'Merged 3 PRs to scikit-learn (#1234, #1301)'.", evidence=o["evidence"][:2], points=w * 0.4))
    elif o["level"] == "weak":
        f.append(F("info", "oss", "GitHub link only, no contributions described", "A profile alone is weak evidence.",
                   "Make 2-3 small merged contributions (docs, tests, bug fixes) via 'good first issue' labels; then list them.", points=w * 0.8))
    else:
        f.append(F("info", "oss", "No open-source contributions found", "For fresher profiles this is a differentiator.",
                   "Start with 'good first issue' tickets, then apply to GSoC / Outreachy / LFX / MLH Fellowship when eligible.", points=w))
    return frac, f


def c_ach(p, stage):
    w = WEIGHTS[stage]["achievements"]
    a = p["achievements"]
    f = []
    types = {x["type"] for x in a}
    frac = min(1.0, 0.5 * min(1.0, len(a) / 3) + 0.5 * min(1.0, len(types) / 2))
    if a:
        f.append(F("good", "achievements", f"{len(a)} achievement(s) detected ({', '.join(sorted(types))})", "", evidence=[_clip(x["text"], 100) for x in a[:3]], fid="ach_ok"))
    else:
        f.append(F("info", "achievements", "No achievements, hackathons or ratings found", "", "Add hackathon results, coding ratings, ranks, scholarships or publications with numbers.", points=w))
    return frac, f


# ------------------------------------------------------------------ main
def grade(score: int) -> str:
    return "Excellent" if score >= 85 else "Strong" if score >= 70 else "Fair" if score >= 55 else "Needs work" if score >= 40 else "Weak"


def analyze(parsed: dict, role: str | None) -> dict:
    role = normalize_role(role)
    stage = stage_of(parsed)
    W = WEIGHTS[stage]
    comps, findings = {}, []

    def add(key, res):
        frac, fs = res[0], res[1]
        comps[key] = {"label": LABELS[key], "weight": W[key], "fraction": round(frac, 3), "points": round(W[key] * frac, 1)}
        findings.extend(fs)

    add("parse", c_parse(parsed, stage))
    add("contact", c_contact(parsed, stage, role))
    add("structure", c_structure(parsed, stage))
    add("experience", c_experience(parsed, stage))
    add("projects", c_projects(parsed, stage))
    sk = c_skills(parsed, stage, role)
    add("skills", sk)
    add("impact", c_impact(parsed, stage))
    add("writing", c_writing(parsed, stage))
    add("education", c_education(parsed, stage))
    add("certs", c_certs(parsed, stage, role))
    add("oss", c_oss(parsed, stage))
    add("achievements", c_ach(parsed, stage))

    raw = sum(c["points"] for c in comps.values())
    score = round(raw)
    caps = []
    if comps["parse"]["fraction"] < 0.2:
        caps.append("Text could not be read reliably")
        score = min(score, 35)
    if not parsed["contact"]["email"]:
        caps.append("No email found")
        score = min(score, 60)
    if not parsed["sections_found"]:
        caps.append("No recognisable section headings")
        score = min(score, 50)
    sev_rank = {"critical": 0, "warning": 1, "info": 2, "good": 3}
    findings.sort(key=lambda x: (sev_rank[x["severity"]], -x["points_at_stake"]))
    quick_wins = sorted([x for x in findings if x["severity"] in ("critical", "warning") and x["fix"]], key=lambda x: -x["points_at_stake"])[:5]
    return {
        "score": int(score), "raw_score": round(raw, 1), "grade": grade(int(score)), "stage": stage, "stage_label": STAGE_LABEL[stage],
        "role": role, "components": comps, "findings": findings, "caps": caps,
        "quick_wins": [{"title": q["title"], "fix": q["fix"], "points": q["points_at_stake"]} for q in quick_wins],
        "role_report": sk[2],
        "summary": {
            "internships": parsed["totals"]["internships"], "experience_months": parsed["totals"]["experience_months"],
            "projects": len(parsed["projects"]), "certifications": len(parsed["certifications"]),
            "open_source": parsed["open_source"]["level"], "achievements": len(parsed["achievements"]),
            "skills_detected": len(parsed["skills"]["all"]),
        },
    }


# ------------------------------------------------------------------ JD match
_STOP = set("""the and for with that this from will have your you our are can all not but has was were been their they them its
into out about over also more than other such any may use used using work working team teams role company candidate candidates
experience years year strong ability skills skill knowledge required requirements preferred responsibilities qualifications
including include etc good excellent great well must should able join looking seeking position job description opportunity
across within build building develop developing development""".split())


def match_jd(parsed: dict, resume_text: str, jd: str) -> dict:
    jd_skills = extract_skills(jd)
    mode = "required"
    pref: set[str] = set()
    req: set[str] = set()
    for ln in jd.splitlines():
        low = ln.lower().strip()
        if re.match(r"^[\W_]*(preferred|nice to have|good to have|bonus|plus|desirable|would be a plus)", low):
            mode = "preferred"
        elif re.match(r"^[\W_]*(requirements?|qualifications?|must have|required|what you'?ll need|responsibilit|about you|you have)", low):
            mode = "required"
        for s in extract_skills(ln):
            (pref if mode == "preferred" else req).add(s)
    pref -= req
    ctx, listed, anywhere = set(parsed["skills"]["in_context"]), set(parsed["skills"]["listed"]), set(parsed["skills"]["all"])
    rows, tot, got = [], 0.0, 0.0
    for s, cnt in jd_skills.most_common():
        wgt = (1 if s in pref else 3) + (1 if cnt >= 3 else 0)
        st = "context" if s in ctx else ("listed" if (s in listed or s in anywhere) else "missing")
        rows.append({"skill": s, "weight": wgt, "status": st, "requirement": "preferred" if s in pref else "required", "mentions": cnt})
        tot += wgt
        got += wgt * _credit(st)
    skill_cov = got / tot if tot else 0.0
    words = [w for w in re.findall(r"[a-z][a-z\-]{3,}", jd.lower()) if w not in _STOP]
    sk_tokens = {t for s in jd_skills for t in re.findall(r"[a-z]+", s)}
    freq = Counter(w for w in words if w not in sk_tokens)
    kws = [w for w, c in freq.most_common(40) if c >= 2][:15]
    rl = resume_text.lower()
    kw_rows = [{"keyword": k, "found": (k[:6] in rl)} for k in kws]
    kw_cov = (sum(1 for k in kw_rows if k["found"]) / len(kw_rows)) if kw_rows else 0.0
    m = re.search(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)[^.\n]{0,40}experience|experience[^.\n]{0,30}?(\d{1,2})\s*\+?\s*(?:years?|yrs?)", jd, re.I)
    need = int(next(g for g in m.groups() if g)) if m else None
    have = parsed["totals"]["work_months"] / 12 + parsed["totals"]["internship_months"] / 24
    exp_fit = 1.0 if need is None else min(1.0, have / need) if need else 1.0
    score = round(100 * (0.7 * skill_cov + 0.2 * kw_cov + 0.1 * exp_fit)) if (jd_skills or kw_rows) else 0
    missing = [r for r in rows if r["status"] == "missing"]
    findings = []
    if missing:
        req_m = [r["skill"] for r in missing if r["requirement"] == "required"]
        if req_m:
            findings.append({"severity": "critical" if len(req_m) >= 3 else "warning", "title": "Required skills missing: " + ", ".join(req_m[:8]),
                             "fix": "Add them only if you have real experience; otherwise address with a project or note them as 'learning'."})
    weak = [r["skill"] for r in rows if r["status"] == "listed"]
    if weak:
        findings.append({"severity": "info", "title": "Listed but not shown in context: " + ", ".join(weak[:6]), "fix": "Mention them inside a project or experience bullet."})
    if need and have < need:
        findings.append({"severity": "warning", "title": f"JD asks for ~{need}+ years; resume shows ~{round(have, 1)}",
                         "fix": "If the role allows freshers/interns, highlight projects and internships; otherwise target a more junior posting."})
    return {"score": score, "skills": rows, "keywords": kw_rows, "years_required": need, "years_have": round(have, 1), "findings": findings}
