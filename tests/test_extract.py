"""Real PDF/DOCX files: layout signals (columns, tables, header text, hyperlinks) must be detected."""
import io

import docx
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, SimpleDocTemplate

from app.services.ats import analyze
from app.services.resume_parser import extract_document, parse_resume

from .conftest import fixture_bytes

ST = getSampleStyleSheet()


def _lines():
    return fixture_bytes("fresher.txt").decode().splitlines()


def _story(lines, link=True):
    out = []
    for ln in lines:
        if not ln.strip():
            out.append(Spacer(1, 4))
            continue
        t = ln.replace("&", "&amp;").replace("<", "&lt;")
        t = t.replace("\u2022", "&bull;")
        if link and "linkedin.com/in/" in t:
            t = t.replace("linkedin.com/in/aarav-sharma-dev", '<a href="https://linkedin.com/in/aarav-sharma-dev" color="blue">linkedin.com/in/aarav-sharma-dev</a>')
        out.append(Paragraph(t, ST["BodyText"]))
    return out


def single_column_pdf():
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=30, bottomMargin=30).build(_story(_lines()))
    return buf.getvalue()


def two_column_pdf():
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4)
    w, h = A4
    gap = 24
    cw = (w - 80 - gap) / 2
    doc.addPageTemplates([PageTemplate(frames=[Frame(40, 30, cw, h - 60, id="l"), Frame(40 + cw + gap, 30, cw, h - 60, id="r")])])
    lines = _lines()
    doc.build(_story(lines * 3))
    return buf.getvalue()


def test_single_column_pdf_is_clean_and_links_are_found():
    d = extract_document(single_column_pdf(), "cv.pdf")
    assert not d.multi_column and d.tables == 0 and d.chars_per_page > 500
    assert any("linkedin.com" in l for l in d.links)
    p = parse_resume(d)
    a = analyze(p, "ML / AI Engineer")
    assert p["contact"]["linkedin_clickable"] is True
    assert p["totals"]["internships"] == 2 and a["score"] >= 70
    assert "parse_ok" in {f["id"] for f in a["findings"]}


def test_two_column_pdf_is_flagged():
    d = extract_document(two_column_pdf(), "cv.pdf")
    assert d.multi_column is True
    a = analyze(parse_resume(d), "Software Engineer")
    assert any("Multi-column" in f["title"] for f in a["findings"])


def test_scanned_pdf_gets_critical_finding_and_cap():
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.rect(50, 50, 300, 300, fill=1)  # no text at all
    c.save()
    d = extract_document(buf.getvalue(), "scan.pdf")
    a = analyze(parse_resume(d), "Software Engineer")
    assert a["findings"][0]["severity"] == "critical" and "text" in a["findings"][0]["title"].lower()
    assert a["score"] <= 35


def test_docx_table_header_and_hyperlink_detection():
    d = docx.Document()
    d.sections[0].header.paragraphs[0].text = "Aarav Sharma | aarav@gmail.com | +91 98765 43210"
    d.add_paragraph("EXPERIENCE")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "Backend Intern, Razorpay"
    t.cell(0, 1).text = "Jun 2024 - Aug 2024"
    d.add_paragraph("Built 6 REST API endpoints serving 12,000 daily requests", style="List Bullet")
    buf = io.BytesIO()
    d.save(buf)
    doc = extract_document(buf.getvalue(), "cv.docx")
    assert doc.tables == 1 and "Razorpay" in doc.text and "aarav@gmail.com" in doc.header_footer_text
    a = analyze(parse_resume(doc), "Backend Developer")
    titles = " ".join(f["title"] for f in a["findings"])
    assert "header/footer" in titles and "Table structure" in titles


def test_docx_bullets_and_roundtrip_parse():
    src = fixture_bytes("fresher.txt").decode().splitlines()
    d = docx.Document()
    for ln in src:
        if ln.startswith("\u2022"):
            d.add_paragraph(ln[1:].strip(), style="List Bullet")
        else:
            d.add_paragraph(ln)
    buf = io.BytesIO()
    d.save(buf)
    p = parse_resume(extract_document(buf.getvalue(), "cv.docx"))
    assert p["totals"]["internships"] == 2 and p["open_source"]["level"] == "strong" and len(p["certifications"]) == 3
