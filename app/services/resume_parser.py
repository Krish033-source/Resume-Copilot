"""Resume text extraction + structured parsing.

Pipeline: bytes -> Document (text + layout signals) -> sections -> entries -> ParsedResume dict.
Everything here is deterministic and evidence based (we keep the original lines that
triggered a detection so the UI can show *why* something was found).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date

from .skills import extract_skills

BULLET_CHARS = "\u2022\u25aa\u25cf\u25e6\uf0b7\u2023\u2043\u2219\u00b7\u25a0\u2756\u27a2\u25ba\u25b6\u2013\u2014*-"
BULLET_RE = re.compile(r"^\s*(?:[" + re.escape(BULLET_CHARS) + r"]|o(?=\s)|\d{1,2}[.)])\s+")
PRIVATE_USE_RE = re.compile(r"[\ue000-\uf8ff]")


# ----------------------------------------------------------------- Document
@dataclass
class Document:
    text: str
    fmt: str
    pages: int = 1
    tables: int = 0
    multi_column: bool = False
    images: int = 0
    text_boxes: int = 0
    links: list[str] = field(default_factory=list)
    chars_per_page: float = 0.0
    header_footer_text: str = ""
    garbled_ratio: float = 0.0
    private_use_bullets: bool = False

    @property
    def lines(self) -> list[str]:
        return [ln for ln in self.text.splitlines()]


def _normalize(text: str) -> tuple[str, bool]:
    pu = bool(PRIVATE_USE_RE.search(text))
    text = PRIVATE_USE_RE.sub("\u2022", text)
    for a, b in (("\ufb01", "fi"), ("\ufb02", "fl"), ("\ufb00", "ff"), ("\u00a0", " "), ("\u200b", ""),
                 ("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'), ("\t", "  ")):
        text = text.replace(a, b)
    text = re.sub(r"[ ]{3,}", "  ", text)
    text = "\n".join(ln.rstrip() for ln in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(), pu


def _garbled(text: str) -> float:
    if not text:
        return 1.0
    bad = text.count("\ufffd") + len(re.findall(r"[^\x00-\x7f\u0900-\u097f\u2000-\u206f\u20a0-\u20cf\u2190-\u21ff\u25a0-\u25ff\u00a0-\u024f]", text))
    return bad / max(1, len(text))


def _detect_gutter(page) -> float | None:
    """Return x of a vertical gutter if the page is laid out in columns, else None."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if len(words) < 60:
        return None
    w = float(page.width)
    total = len(words)
    best = None
    for pct in range(22, 78):
        x = w * pct / 100
        band_lo, band_hi = x, x + w * 0.02
        if any(wd["x0"] < band_hi and wd["x1"] > band_lo for wd in words):
            continue
        left = [wd for wd in words if wd["x1"] <= band_lo]
        right = [wd for wd in words if wd["x0"] >= band_hi]
        if len(left) / total < 0.12 or len(right) / total < 0.12:
            continue
        def rows(ws):
            r = {}
            for wd in ws:
                k = round(wd["top"] / 3)
                r[k] = min(r.get(k, 1e9), wd["x0"])
            return r
        rl, rr = rows(left), rows(right)
        if len(rl) < 8 or len(rr) < 8:
            continue
        lt, lb = min(rl), max(rl)
        rt, rb = min(rr), max(rr)
        overlap = (min(lb, rb) - max(lt, rt)) / max(1, min(lb - lt, rb - rt))
        starts = sorted(rr.values())
        med = starts[len(starts) // 2]
        consistent = sum(1 for x in starts if abs(x - med) < 6) / len(starts)
        if overlap < 0.5 or consistent < 0.6:
            continue
        best = (band_lo + band_hi) / 2
        break
    return best


def extract_pdf(data: bytes) -> Document:
    import pdfplumber
    parts, tables, images, links, multi = [], 0, 0, [], False
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = len(pdf.pages)
        for page in pdf.pages:
            try:
                tables += len(page.find_tables())
            except Exception:
                pass
            images += len(page.images or [])
            for h in (page.hyperlinks or []):
                uri = h.get("uri")
                if uri:
                    links.append(uri)
            gutter = _detect_gutter(page)
            if gutter:
                multi = True
                try:
                    left = page.crop((0, 0, gutter, page.height)).extract_text() or ""
                    right = page.crop((gutter, 0, page.width, page.height)).extract_text() or ""
                    parts.append(left + "\n" + right)
                    continue
                except Exception:
                    pass
            parts.append(page.extract_text() or "")
    raw = "\n".join(parts)
    text, pu = _normalize(raw)
    return Document(text=text, fmt="pdf", pages=pages, tables=tables, multi_column=multi, images=images,
                    links=list(dict.fromkeys(links)), chars_per_page=len(text) / max(1, pages),
                    garbled_ratio=_garbled(text), private_use_bullets=pu)


def extract_docx(data: bytes) -> Document:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    d = docx.Document(io.BytesIO(data))
    lines, tables = [], 0
    for child in d.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, d)
            t = p.text.strip()
            if t:
                num = child.find(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}numPr")
                lines.append(("\u2022 " + t) if num is not None and not BULLET_RE.match(t) else t)
        elif tag == "tbl":
            tables += 1
            seen = set()
            for row in Table(child, d).rows:
                cells = []
                for c in row.cells:
                    if id(c._tc) in seen:
                        continue
                    seen.add(id(c._tc))
                    ct = " ".join(p.text.strip() for p in c.paragraphs if p.text.strip())
                    if ct:
                        cells.append(ct)
                if cells:
                    lines.append("  ".join(cells))
    links = [r.target_ref for r in d.part.rels.values() if r.reltype.endswith("/hyperlink")]
    hf = []
    for s in d.sections:
        for part in (s.header, s.footer):
            try:
                hf.extend(p.text.strip() for p in part.paragraphs if p.text.strip())
            except Exception:
                pass
    xml = d.element.xml
    text_boxes = xml.count("txbxContent") // 2 if "txbxContent" in xml else 0
    text, pu = _normalize("\n".join(lines))
    pages = max(1, round(len(text.split()) / 520))
    return Document(text=text, fmt="docx", pages=pages, tables=tables, images=len(d.inline_shapes),
                    text_boxes=text_boxes, links=list(dict.fromkeys(links)), chars_per_page=len(text) / pages,
                    header_footer_text="\n".join(hf), garbled_ratio=_garbled(text), private_use_bullets=pu)


def extract_text_file(data: bytes) -> Document:
    text, pu = _normalize(data.decode("utf-8", errors="ignore"))
    pages = max(1, round(len(text.split()) / 520))
    return Document(text=text, fmt="txt", pages=pages, chars_per_page=len(text) / pages,
                    garbled_ratio=_garbled(text), private_use_bullets=pu)


def extract_document(data: bytes, filename: str) -> Document:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        return extract_pdf(data)
    if ext == "docx":
        return extract_docx(data)
    if ext == "txt":
        return extract_text_file(data)
    raise ValueError("Unsupported file type. Upload PDF, DOCX or TXT.")


# ----------------------------------------------------------------- sections
SECTION_ALIASES = {
    "summary": ["summary", "professional summary", "profile", "objective", "career objective", "about me", "about",
                "career summary", "professional profile"],
    "experience": ["experience", "work experience", "professional experience", "employment", "employment history",
                   "work history", "career history", "industry experience", "relevant experience"],
    "internships": ["internships", "internship", "internship experience", "trainings", "training and internships"],
    "education": ["education", "academic background", "academics", "educational qualification", "qualifications",
                  "academic qualifications", "education & qualifications", "educational background"],
    "projects": ["projects", "personal projects", "academic projects", "key projects", "project work",
                 "technical projects", "selected projects", "project experience"],
    "skills": ["skills", "technical skills", "core competencies", "key skills", "technologies", "tech stack",
               "skills & tools", "skills and tools", "technical expertise", "areas of expertise", "technical proficiency",
               "skills summary", "tools & technologies", "tools and technologies"],
    "certifications": ["certifications", "certificates", "certification", "licenses", "licenses & certifications",
                       "licenses and certifications", "courses", "courses & certifications", "online courses",
                       "certifications & courses", "training & certifications", "courses and certifications"],
    "achievements": ["achievements", "awards", "honors", "honours", "accomplishments", "awards & achievements",
                     "awards and honors", "awards and achievements", "scholarships", "honors & awards", "achievement"],
    "open_source": ["open source", "open-source", "open source contributions", "open source experience"],
    "publications": ["publications", "research", "research experience", "papers", "research papers", "patents",
                     "research & publications", "research and publications"],
    "extracurricular": ["extracurricular", "extra-curricular", "extracurricular activities", "activities", "leadership",
                        "volunteering", "positions of responsibility", "co-curricular", "community", "clubs",
                        "leadership & activities", "leadership and activities"],
    "other": ["languages", "interests", "hobbies", "references", "declaration", "personal details", "personal information"],
}
_ALIAS_TO_SECTION = {a: s for s, al in SECTION_ALIASES.items() for a in al}


def _heading_key(line: str) -> str | None:
    s = line.strip()
    if not s or len(s) > 48 or len(s.split()) > 6:
        return None
    s = BULLET_RE.sub("", s)
    s = re.sub(r"[:\-–—_|]+$", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    key = s.lower().replace(" and ", " & ") if s.lower() not in _ALIAS_TO_SECTION else s.lower()
    if key in _ALIAS_TO_SECTION:
        return _ALIAS_TO_SECTION[key]
    key2 = s.lower()
    if key2 in _ALIAS_TO_SECTION:
        return _ALIAS_TO_SECTION[key2]
    return None


def segment_sections(lines: list[str]) -> tuple[list[str], dict[str, list[str]], list[str]]:
    header: list[str] = []
    sections: dict[str, list[str]] = {}
    order: list[str] = []
    current = None
    for ln in lines:
        key = _heading_key(ln)
        if key:
            current = key
            if key not in sections:
                sections[key] = []
                order.append(key)
            continue
        if current is None:
            header.append(ln)
        else:
            sections[current].append(ln)
    return header, sections, order


# ----------------------------------------------------------------- dates
_MONTHS = "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
_DATE = rf"(?:(?:{_MONTHS})\.?,?\s*['\u2019]?\s*(?:\d{{4}}|\d{{2}})|(?:0?[1-9]|1[0-2])\s*[/.]\s*(?:19|20)\d{{2}}|(?:19|20)\d{{2}})"
_PRESENT = r"(?:present|current|till date|to date|ongoing|now|today|till now)"
RANGE_RE = re.compile(rf"({_DATE})\s*(?:-|\u2013|\u2014|to|until|till)\s*({_DATE}|{_PRESENT})", re.I)
SINGLE_RE = re.compile(rf"\b({_DATE})\b", re.I)
_MONTH_NUM = {m[:3]: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_ym(s: str, end: bool = False, today: date | None = None) -> tuple[int, int] | None:
    today = today or date.today()
    s = s.strip().lower()
    if re.fullmatch(_PRESENT, s):
        return today.year, today.month
    m = re.match(rf"({_MONTHS})\.?,?\s*['\u2019]?\s*(\d{{4}}|\d{{2}})", s)
    if m:
        y = int(m.group(2))
        y = y + 2000 if y < 100 else y
        return y, _MONTH_NUM[m.group(1)[:3]]
    m = re.match(r"(\d{1,2})\s*[/.]\s*((?:19|20)\d{2})", s)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.match(r"((?:19|20)\d{2})$", s)
    if m:
        return int(m.group(1)), 12 if end else 1
    return None


def months_between(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (b[0] * 12 + b[1]) - (a[0] * 12 + a[1]) + 1


def find_range(text: str):
    m = RANGE_RE.search(text)
    if m:
        a, b = parse_ym(m.group(1)), parse_ym(m.group(2), end=True)
        if a and b:
            today = date.today()
            if b > (today.year, today.month):
                b = (today.year, today.month) if re.fullmatch(_PRESENT, m.group(2).strip().lower()) else b
            return a, b, m.group(0)
    m = SINGLE_RE.search(text)
    if m:
        a = parse_ym(m.group(1))
        if a and not re.fullmatch(r"(?:19|20)\d{2}", m.group(1).strip()):
            return a, a, m.group(0)
    return None


def merge_months(intervals: list[tuple[tuple[int, int], tuple[int, int]]]) -> int:
    if not intervals:
        return 0
    ivs = sorted(((a[0] * 12 + a[1], b[0] * 12 + b[1]) for a, b in intervals if a <= b))
    total, cs, ce = 0, None, None
    for s, e in ivs:
        if cs is None:
            cs, ce = s, e
        elif s <= ce + 1:
            ce = max(ce, e)
        else:
            total += ce - cs + 1
            cs, ce = s, e
    if cs is not None:
        total += ce - cs + 1
    return total


# ----------------------------------------------------------------- entries
URL_RE = re.compile(r"(?:https?://|www\.)[^\s)\]>,;]+|(?:github\.com|gitlab\.com|linkedin\.com|[\w-]+\.(?:vercel\.app|netlify\.app|herokuapp\.com|onrender\.com|github\.io|streamlit\.app|hf\.space))/[^\s)\]>,;]*", re.I)
TECH_LINE_RE = re.compile(r"^\s*(?:tech(?:nologies)?(?:\s+(?:stack|used))?|stack|tools(?:\s+used)?|built\s+with|environment|tech\s*stack)\s*[:\-\u2013]\s*(.+)$", re.I)
ROLE_WORDS = r"engineer|developer|intern|analyst|scientist|designer|manager|lead|associate|consultant|trainee|researcher|assistant|architect|administrator|officer|executive|specialist|tester|sde|programmer|fellow|apprentice|contributor|mentor|head|founder|freelanc\w*"
INTERN_RE = re.compile(r"\bintern(?:ship)?s?\b|\btrainee\b|\bapprentice(?:ship)?\b|\bsummer analyst\b", re.I)
FREELANCE_RE = re.compile(r"freelanc|contract(?:or)?\b|consultant|self[- ]employed|upwork|fiverr", re.I)


def _strip_bullet(s: str) -> str:
    return BULLET_RE.sub("", s).strip()


def _is_continuation(prev: str, line: str) -> bool:
    if not prev:
        return False
    if find_range(line) and RANGE_RE.search(line):
        return False
    first = line.strip()[:1]
    if first.islower() or first in "(%$\u20b9&+,;:.0123456789":
        return True
    if not re.search(r"[.!?:;]$", prev.strip()) and (len(line.split()) > 8 or line.strip().endswith(".")):
        return True
    return False


def split_blocks(lines: list[str]) -> list[dict]:
    """Group lines into {header:[...], bullets:[...]} blocks."""
    blocks: list[dict] = []
    cur = None
    for raw in lines:
        if not raw.strip():
            continue
        is_b = bool(BULLET_RE.match(raw))
        if is_b:
            if cur is None:
                cur = {"header": [], "bullets": []}
                blocks.append(cur)
            cur["bullets"].append(_strip_bullet(raw))
            continue
        line = raw.strip()
        if cur is not None and cur["bullets"] and TECH_LINE_RE.match(line):
            cur["bullets"].append(line)  # "Technologies: ..." belongs to the current entry
            continue
        if cur is not None and cur["bullets"] and _is_continuation(cur["bullets"][-1], line):
            cur["bullets"][-1] += " " + line
            continue
        if cur is None or cur["bullets"] or (cur["header"] and find_range(line) is None and find_range(" ".join(cur["header"])) is not None):
            cur = {"header": [line], "bullets": []}
            blocks.append(cur)
        else:
            cur["header"].append(line)
    merged: list[dict] = []
    for b in blocks:
        prev = merged[-1] if merged else None
        if (prev and not b["bullets"] and len(b["header"]) == 1 and not find_range(b["header"][0])
                and not prev["bullets"] and find_range(" ".join(prev["header"])) and len(b["header"][0].split()) <= 8):
            prev["header"].append(b["header"][0])
        else:
            merged.append(b)
    return merged


def _role_org(heading: str) -> tuple[str, str]:
    h = re.sub(r"\s+", " ", heading).strip(" |-\u2013\u2014,")
    parts = [p.strip() for p in re.split(r"\s+[|\u2022\u2013\u2014-]\s+|\s+at\s+|\s*\|\s*|,\s+(?=[A-Z])", h) if p.strip()]
    if not parts:
        return "", ""
    role_idx = next((i for i, p in enumerate(parts) if re.search(rf"\b(?:{ROLE_WORDS})\b", p, re.I)), 0)
    role = parts[role_idx]
    org = next((p for i, p in enumerate(parts) if i != role_idx), "")
    return role, org


def _split_tech(txt: str) -> list[str]:
    txt = URL_RE.sub(" ", txt)
    return [t.strip(" .") for t in re.split(r"[,|;]", txt) if t.strip(" .")]


def parse_entries(lines: list[str], default_kind: str, allow_desc: bool = False) -> list[dict]:
    entries = []
    for blk in split_blocks(lines):
        header_text = " ".join(blk["header"])
        rng = find_range(header_text)
        bullets = list(blk["bullets"])
        tech: list[str] = []
        hdr_clean = header_text
        # inline tech in header: "Project | Tech: A, B"
        m = re.search(r"(?:tech(?:nologies)?(?: stack)?|stack|built with)\s*[:\-\u2013]\s*(.+)$", header_text, re.I)
        if m:
            tech += _split_tech(m.group(1))
            hdr_clean = header_text[:m.start()]
        keep = []
        for b in bullets:
            mt = TECH_LINE_RE.match(b)
            if mt:
                tech += _split_tech(mt.group(1))
            else:
                keep.append(b)
        bullets = keep
        if not bullets and len(blk["header"]) > 1 and allow_desc:
            desc = blk["header"][1:]
            hdr_clean = blk["header"][0]
            bullets = [d for d in desc if len(d.split()) >= 5]
            for d in desc:
                mt = TECH_LINE_RE.match(d)
                if mt:
                    tech += _split_tech(mt.group(1))
        elif not bullets and not rng and len(header_text.split()) < 4:
            continue
        if rng:
            hdr_clean = hdr_clean.replace(rng[2], " ")
        hdr_clean = re.sub(r"\s{2,}", " ", URL_RE.sub(" ", hdr_clean)).strip(" |-\u2013\u2014,")
        pm = re.search(r"\(([^()]*)\)\s*$", hdr_clean)
        if pm and extract_skills(pm.group(1)):
            tech += _split_tech(pm.group(1))
            hdr_clean = hdr_clean[:pm.start()].strip(" |-\u2013\u2014,")
        role, org = _role_org(hdr_clean)
        full = " ".join([header_text] + bullets)
        kind = default_kind
        if default_kind in ("work", "internship"):
            if INTERN_RE.search(header_text):
                kind = "internship"
            elif FREELANCE_RE.search(header_text):
                kind = "freelance"
        urls = [u.rstrip(".") for u in URL_RE.findall(full)]
        entries.append({
            "heading": hdr_clean, "role": role, "org": org, "kind": kind,
            "start": list(rng[0]) if rng else None, "end": list(rng[1]) if rng else None,
            "date_text": rng[2] if rng else "",
            "months": months_between(rng[0], rng[1]) if rng else 0,
            "bullets": bullets, "tech": tech, "urls": urls,
            "skills": dict(extract_skills(full + "\n" + ", ".join(tech))),
        })
    return entries


# ----------------------------------------------------------------- contact
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<![\d/])(?:\+?\d{1,3}[\s\-.]?)?(?:\(?\d{2,5}\)?[\s\-.]?)?\d{3,5}[\s\-.]?\d{4,5}(?!\d)")


def parse_contact(header_lines: list[str], text: str, links: list[str]) -> dict:
    head = "\n".join(header_lines[:12]) or "\n".join(text.splitlines()[:12])
    scan = head + "\n" + "\n".join(links)
    email = (EMAIL_RE.search(head) or EMAIL_RE.search(text) or EMAIL_RE.search("\n".join(links)))
    mailto = next((l for l in links if l.lower().startswith("mailto:")), "")
    email_v = email.group(0) if email else (mailto[7:].split("?")[0] if mailto else "")
    phone = ""
    for m in PHONE_RE.finditer(head):
        digits = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits) <= 13 and not RANGE_RE.search(m.group(0)):
            phone = m.group(0).strip()
            break
    full_scan = scan + "\n" + text
    li = re.search(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[\w\-%]+", full_scan, re.I)
    gh = re.search(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9\-]+)(?![\w\-/]*/[\w.\-]+)", full_scan, re.I)
    other = [u for u in URL_RE.findall(scan) if not re.search(r"linkedin|github|mailto", u, re.I)]
    portfolio = other[0] if other else ""
    linkedin_hyper = bool(li and any("linkedin.com" in l.lower() for l in links))
    linkedin_text = bool(li and not linkedin_hyper) or bool(re.search(r"linkedin\.com", head, re.I))
    name = ""
    for ln in header_lines[:6]:
        s = ln.strip()
        if not s or "@" in s or re.search(r"\d{5,}|http|www\.|linkedin|github", s, re.I):
            continue
        words = re.findall(r"[A-Za-z][A-Za-z.'\-]*", s)
        if 2 <= len(words) <= 4 and len(words) == len(s.split()):
            name = " ".join(w.capitalize() if w.isupper() and len(w) > 1 else w for w in words)
            break
    loc = ""
    for ln in header_lines[:8]:
        for part in re.split(r"\s*[|\u2022\u00b7]\s*", ln):
            if "@" in part or re.search(r"\d{4,}|http|www\.|\.com", part):
                continue
            m = re.search(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)?),\s*([A-Z][a-z]+(?: [A-Z][a-z]+)?|[A-Z]{2})\b", part)
            if m and not re.search(rf"\b(?:{ROLE_WORDS})\b", m.group(0), re.I):
                loc = m.group(0)
                break
        if loc:
            break
    return {
        "name": name, "email": email_v, "phone": phone,
        "linkedin": li.group(0) if li else "", "github": ("github.com/" + gh.group(1)) if gh else "",
        "portfolio": portfolio, "location": loc,
        "linkedin_clickable": linkedin_hyper, "links_clickable": len(links),
    }


# ----------------------------------------------------------------- education
DEGREE_RE = re.compile(
    r"\b(b\.?\s?tech|b\.?\s?e\b|b\.?\s?sc|b\.?\s?c\.?a\b|b\.?\s?com|b\.?\s?a\b|bachelor(?:'s)?(?: of [A-Za-z ]+)?|"
    r"m\.?\s?tech|m\.?\s?e\b|m\.?\s?sc|m\.?\s?c\.?a\b|mba|pgdm|master(?:'s)?(?: of [A-Za-z ]+)?|ph\.?\s?d|doctorate|"
    r"diploma|polytechnic|integrated m\.?tech|dual degree)\b", re.I)
INSTITUTE_RE = re.compile(r"\b(university|college|institute|iit|nit|iiit|iim|bits|school|academy|vit|srm|manipal|polytechnic)\b", re.I)
CGPA_RE = re.compile(r"(?:cgpa|gpa|cpi|sgpa)\s*[:\-]?\s*(\d{1,2}(?:\.\d{1,2})?)\s*(?:/\s*(10|4(?:\.0)?|5|100))?", re.I)
CGPA_ALT_RE = re.compile(r"\b(\d(?:\.\d{1,2})?)\s*/\s*(10|4(?:\.0)?)\b")
PCT_RE = re.compile(r"\b(\d{2}(?:\.\d{1,2})?)\s*%")


def parse_education(lines: list[str], all_text: str) -> dict:
    items = []
    for blk in split_blocks(lines):
        txt = " ".join(blk["header"] + blk["bullets"])
        deg = DEGREE_RE.search(txt)
        inst = INSTITUTE_RE.search(txt)
        rng = find_range(txt)
        cg = CGPA_RE.search(txt) or CGPA_ALT_RE.search(txt)
        cgpa, scale = None, None
        if cg:
            try:
                cgpa = float(cg.group(1))
                scale = float(cg.group(2)) if cg.lastindex and cg.lastindex >= 2 and cg.group(2) else (10.0 if cgpa > 4.0 else 4.0)
                if scale == 100:
                    cgpa, scale = cgpa / 10, 10.0
            except ValueError:
                cgpa = None
        pct = PCT_RE.search(txt)
        items.append({
            "text": txt[:240], "degree": deg.group(0) if deg else "", "has_institute": bool(inst),
            "start_year": rng[0][0] if rng else None, "end_year": rng[1][0] if rng else None,
            "cgpa": cgpa, "cgpa_scale": scale, "percentage": float(pct.group(1)) if pct else None,
        })
    # Education often is not bulleted; fall back to line scan
    if not any(i["degree"] for i in items):
        for ln in lines:
            deg = DEGREE_RE.search(ln)
            if deg:
                rng = find_range(ln)
                items.append({"text": ln[:240], "degree": deg.group(0), "has_institute": bool(INSTITUTE_RE.search(ln)),
                              "start_year": rng[0][0] if rng else None, "end_year": rng[1][0] if rng else None,
                              "cgpa": None, "cgpa_scale": None, "percentage": None})
    degree_items = [i for i in items if i["degree"]]
    best = degree_items[0] if degree_items else (items[0] if items else None)
    cgpa_item = next((i for i in items if i["cgpa"] is not None), None)
    if not cgpa_item:
        m = CGPA_RE.search(all_text)
        if m:
            try:
                v = float(m.group(1))
                cgpa_item = {"cgpa": v, "cgpa_scale": 10.0 if v > 4 else 4.0}
            except ValueError:
                pass
    years = [i["end_year"] for i in degree_items if i["end_year"]]
    return {
        "items": items[:6], "degree": best["degree"] if best else "",
        "institution_found": any(i["has_institute"] for i in items),
        "grad_year": max(years) if years else (best["end_year"] if best else None),
        "cgpa": cgpa_item["cgpa"] if cgpa_item else None,
        "cgpa_scale": cgpa_item["cgpa_scale"] if cgpa_item else None,
        "has_section": bool(lines),
    }


# ----------------------------------------------------------------- certifications
VENDOR_CERT = r"aws|amazon|microsoft|azure|google|gcp|oracle|cisco|ibm|meta|red hat|comptia|hashicorp|databricks|salesforce|istqb|pmi|ec-council|offensive security|linux foundation|cncf|cka|ckad|nvidia|snowflake|tableau|mongodb|deeplearning\.ai|stanford|nptel|iit|isc2|isaca|servicenow|scrum\.org|scrum alliance"
PLATFORM_CERT = r"coursera|udemy|edx|udacity|linkedin learning|freecodecamp|hackerrank|great learning|simplilearn|infosys springboard|skillshare|kaggle|datacamp|codecademy|geeksforgeeks|gfg|cs50|harvard|upgrad|internshala|letsupgrade|coding ninjas|scaler"
CERT_WORD_RE = re.compile(r"certif|certificate|specialization|professional certificate|nanodegree|credential|licen[cs]e", re.I)
VENDOR_RE = re.compile(rf"\b(?:{VENDOR_CERT})\b", re.I)
PLATFORM_RE = re.compile(rf"\b(?:{PLATFORM_CERT})\b", re.I)


def parse_certifications(section_lines: list[str], all_lines: list[str], skip_sections: set[int]) -> list[dict]:
    items, seen = [], set()

    def add(text: str):
        t = _strip_bullet(text)
        if len(t) < 6 or len(t.split()) > 30:
            return
        key = re.sub(r"\W+", "", t.lower())[:60]
        if key in seen:
            return
        seen.add(key)
        vendor = VENDOR_RE.search(t)
        platform = PLATFORM_RE.search(t)
        yr = re.search(r"\b(20\d{2}|19\d{2})\b", t)
        items.append({
            "name": t[:160],
            "issuer": (vendor or platform).group(0) if (vendor or platform) else "",
            "tier": "vendor" if vendor else ("platform" if platform else "unknown"),
            "year": int(yr.group(1)) if yr else None,
            "verifiable": bool(re.search(r"credential|id\s*[:#]|verify|credly|http|www\.", t, re.I)),
        })

    merged = []
    for ln in section_lines:
        if not ln.strip():
            continue
        if merged and _is_continuation(merged[-1], ln) and not BULLET_RE.match(ln):
            merged[-1] += " " + ln.strip()
        else:
            merged.append(ln.strip())
    for ln in merged:
        add(ln)
    for i, ln in enumerate(all_lines):
        if i in skip_sections or BULLET_RE.match(ln) and re.search(r"\b(built|developed|implemented|designed|created)\b", ln, re.I):
            continue
        if CERT_WORD_RE.search(ln) and (VENDOR_RE.search(ln) or PLATFORM_RE.search(ln) or re.search(r"certified", ln, re.I)):
            add(ln)
    return items[:12]


# ----------------------------------------------------------------- open source & achievements
OSS_STRONG = re.compile(r"gsoc|google summer of code|outreachy|lfx mentorship|mlh fellowship|season of docs|\bmaintainer\b|core contributor|\bcommitter\b|"
                        r"merged\s+(?:\d+\+?\s*)?(?:pull requests?|prs?)|(?:\d+\+?\s*)?(?:pull requests?|prs?)\s+(?:were\s+)?(?:merged|accepted)", re.I)
OSS_MOD = re.compile(r"open[- ]?source|contribut(?:ed|or|ion|ions|ing)\s+to|upstream|hacktoberfest|pull requests?|\bprs?\b|good first issue|oss\b|forked", re.I)


def detect_open_source(lines: list[str], oss_section: list[str], contact: dict, text: str) -> dict:
    ev_strong, ev_mod = [], []
    for ln in lines:
        s = _strip_bullet(ln)
        if len(s.split()) < 4:
            continue
        if OSS_STRONG.search(s):
            ev_strong.append(s[:200])
        elif OSS_MOD.search(s) and not (len(re.findall(r"[,|;]", s)) >= 3 and len(s.split()) < 14):
            ev_mod.append(s[:200])
    ev_sec = [_strip_bullet(l)[:200] for l in oss_section if len(_strip_bullet(l).split()) >= 4]
    repos = sorted(set(re.findall(r"github\.com/([\w\-]+/[\w.\-]+)", text, re.I)))[:10]
    if ev_strong:
        level = "strong"
    elif ev_mod or ev_sec:
        level = "moderate"
    elif contact.get("github") or repos:
        level = "weak"
    else:
        level = "none"
    return {"level": level, "evidence": list(dict.fromkeys(ev_strong + ev_sec + ev_mod))[:6], "repos": repos}


ACH_PATTERNS = [
    ("hackathon", re.compile(r"hackathon|hack\w*\b|codefest|buildathon|ideathon|datathon|smart india|\bsih\b", re.I),
     re.compile(r"win|won|finalist|1st|first|2nd|second|3rd|third|runner|top\s*\d+|rank|prize|award|selected|shortlisted|champion", re.I)),
    ("competitive_programming", re.compile(r"codeforces|codechef|leetcode|atcoder|hackerrank|icpc|kick\s?start|code jam|topcoder|gfg|geeksforgeeks", re.I),
     re.compile(r"rating|rank|knight|guardian|expert|specialist|candidate master|stars?|\d{3,4}\+?|solved|problems|badge|top\s*\d", re.I)),
    ("rank", re.compile(r"\bair\b|all india rank|percentile|\brank\b|top\s*\d+\s*%|gold medal|medalist|topper", re.I), re.compile(r".")),
    ("kaggle", re.compile(r"kaggle", re.I), re.compile(r"medal|expert|master|grandmaster|top\s*\d+|rank|competition", re.I)),
    ("scholarship", re.compile(r"scholarship|fellowship|stipend|merit", re.I), re.compile(r".")),
    ("publication", re.compile(r"\bpublished\b|ieee|springer|\bacm\b|elsevier|arxiv|journal|conference paper|\bpatent\b|research paper|paper accepted|\bicml\b|\bneurips\b|\bacl\b|\bcvpr\b", re.I), re.compile(r".")),
    ("leadership", re.compile(r"\b(?:president|vice[- ]president|captain|founder|co-?founder|secretary|head of|team lead|organi[sz]er|coordinator|chair)\b", re.I), re.compile(r".")),
]


def detect_achievements(lines: list[str], ach_section: list[str]) -> list[dict]:
    out, seen = [], set()

    def add(kind, text):
        t = _strip_bullet(text)[:200]
        k = re.sub(r"\W+", "", t.lower())[:50]
        if k in seen or len(t) < 8:
            return
        seen.add(k)
        out.append({"type": kind, "text": t})

    for ln in lines:
        s = _strip_bullet(ln)
        if len(s.split()) < 3:
            continue
        for kind, main, support in ACH_PATTERNS:
            if main.search(s) and support.search(s):
                if kind == "leadership" and (len(s.split()) > 40 or not re.search(r"club|team|society|chapter|committee|community|event|fest|students|members", s, re.I)):
                    continue
                add(kind, s)
                break
    for ln in ach_section:
        s = _strip_bullet(ln)
        if len(s.split()) >= 3:
            add("general", s)
    return out[:14]


# ----------------------------------------------------------------- orchestrator
def parse_resume(doc: Document) -> dict:
    lines = doc.lines
    header, sections, order = segment_sections(lines)
    contact = parse_contact(header, doc.text, doc.links)

    work = parse_entries(sections.get("experience", []), "work")
    interns = parse_entries(sections.get("internships", []), "internship")
    for e in interns:
        e["kind"] = "internship"
    experience = work + interns
    projects = parse_entries(sections.get("projects", []), "project", allow_desc=True)
    projects = [p for p in projects if p["heading"] or p["bullets"]]
    education = parse_education(sections.get("education", []), doc.text)

    # skills section
    skill_lines = sections.get("skills", [])
    skills_text = "\n".join(skill_lines)
    listed = extract_skills(skills_text)
    raw_items = []
    for ln in skill_lines:
        body = re.sub(r"^[^:]{1,40}:\s*", "", _strip_bullet(ln))
        raw_items += [x.strip() for x in re.split(r"[,|;\u2022/]", body) if x.strip()]
    ctx_text = "\n".join(b for e in experience + projects for b in e["bullets"] + e["tech"])
    in_context = extract_skills(ctx_text)
    all_skills = extract_skills(doc.text)

    cert_lines = sections.get("certifications", [])
    skip_idx = set()
    certs = parse_certifications(cert_lines, lines, skip_idx)
    oss = detect_open_source(lines, sections.get("open_source", []), contact, doc.text)
    ach = detect_achievements(lines, sections.get("achievements", []))

    iv_all = [(tuple(e["start"]), tuple(e["end"])) for e in experience if e["start"] and e["end"]]
    iv_int = [(tuple(e["start"]), tuple(e["end"])) for e in experience if e["start"] and e["end"] and e["kind"] == "internship"]
    iv_work = [(tuple(e["start"]), tuple(e["end"])) for e in experience if e["start"] and e["end"] and e["kind"] != "internship"]

    # gaps between consecutive intervals (> 6 months)
    gaps = []
    ivs = sorted(((a[0] * 12 + a[1], b[0] * 12 + b[1]) for a, b in iv_all))
    for (s1, e1), (s2, e2) in zip(ivs, ivs[1:]):
        if s2 - e1 > 7 and e1 < date.today().year * 12 + date.today().month - 1:
            gaps.append({"months": s2 - e1 - 1, "after": f"{e1 // 12}-{e1 % 12 or 12:02d}"})

    bullets_all = [b for e in experience + projects for b in e["bullets"]]
    words = len(doc.text.split())
    return {
        "contact": contact,
        "sections_found": order,
        "has_summary": "summary" in sections,
        "experience": experience,
        "projects": projects,
        "education": education,
        "skills": {
            "listed": sorted(listed), "raw_item_count": len(raw_items), "in_context": dict(in_context),
            "all": dict(all_skills), "has_section": bool(skill_lines),
        },
        "certifications": certs,
        "open_source": oss,
        "achievements": ach,
        "totals": {
            "experience_months": merge_months(iv_all), "work_months": merge_months(iv_work),
            "internship_months": merge_months(iv_int),
            "internships": sum(1 for e in experience if e["kind"] == "internship"),
            "jobs": sum(1 for e in experience if e["kind"] == "work"),
            "freelance": sum(1 for e in experience if e["kind"] == "freelance"),
            "bullets": len(bullets_all), "words": words, "pages": doc.pages,
        },
        "gaps": gaps,
        "doc": {
            "fmt": doc.fmt, "pages": doc.pages, "tables": doc.tables, "multi_column": doc.multi_column,
            "images": doc.images, "text_boxes": doc.text_boxes, "links": doc.links[:20],
            "chars_per_page": round(doc.chars_per_page), "header_footer_text": doc.header_footer_text[:300],
            "garbled_ratio": round(doc.garbled_ratio, 4), "private_use_bullets": doc.private_use_bullets,
        },
    }
