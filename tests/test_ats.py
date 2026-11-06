from app.services.ats import analyze, find_metrics, match_jd, stage_of, WEIGHTS
from app.services.resume_parser import extract_document, parse_resume

from .conftest import fixture_bytes


def _run(name, role):
    doc = extract_document(fixture_bytes(name), name)
    p = parse_resume(doc)
    return p, analyze(p, role)


def test_weights_sum_to_100():
    for w in WEIGHTS.values():
        assert sum(w.values()) == 100


def test_metrics_ignore_years_phones_cgpa():
    assert find_metrics("Built app in 2023, phone 9876543210, CGPA 8.7, python 3.11, 2021 - 2025") == []
    assert find_metrics("Cut latency by 38% and served 12,000 daily requests")
    assert find_metrics("Fine-tuned BERT improving F1 from 0.71 to 0.84")
    assert find_metrics("Saved Rs 40000 per month and 3x faster builds")


def test_strong_fresher_resume_findings():
    p, a = _run("fresher.txt", "ML / AI Engineer")
    assert a["stage"] == "fresher"
    assert p["totals"]["internships"] == 2 and p["totals"]["internship_months"] == 6
    assert p["open_source"]["level"] == "strong"
    assert len(p["certifications"]) == 3 and {c["tier"] for c in p["certifications"]} >= {"vendor", "platform"}
    assert any(x["type"] == "hackathon" for x in p["achievements"])
    assert p["education"]["cgpa"] == 8.7 and p["education"]["grad_year"] == 2025
    assert a["score"] >= 75
    ids = {f["id"] for f in a["findings"]}
    assert "internships_ok" in ids and "oss_ok" in ids


def test_weak_resume_scores_low_with_actionable_findings():
    p, a = _run("weak.txt", "Software Engineer")
    assert a["score"] < 55
    titles = " ".join(f["title"] for f in a["findings"])
    assert "No internship" in titles or "No work experience" in titles
    assert "stuffed" in titles
    assert any("Email looks informal" in f["title"] for f in a["findings"])
    assert any(f["category"] == "oss" for f in a["findings"])
    assert a["quick_wins"]


def test_score_is_deterministic_and_role_sensitive():
    _, a1 = _run("fresher.txt", "ML / AI Engineer")
    _, a2 = _run("fresher.txt", "ML / AI Engineer")
    _, a3 = _run("fresher.txt", "UI / UX Designer")
    assert a1["score"] == a2["score"]
    assert a3["components"]["skills"]["points"] < a1["components"]["skills"]["points"]


def test_jd_match():
    p, _ = _run("fresher.txt", "Backend Developer")
    jd = """Backend Engineer Intern
Requirements:
- Strong Python and FastAPI experience, PostgreSQL, Docker
- Experience with Kubernetes and Terraform
Preferred:
- Redis, GraphQL
2+ years of experience preferred."""
    r = match_jd(p, "python fastapi", jd * 2)
    skills = {s["skill"]: s for s in r["skills"]}
    assert skills["python"]["status"] == "context"
    assert skills["kubernetes"]["status"] == "missing"
    assert skills["graphql"]["requirement"] == "preferred"
    assert 0 < r["score"] < 100


def test_experienced_resume_entries_and_stage():
    p, a = _run("experienced.txt", "Backend Developer")
    assert a["stage"] == "experienced" and a["score"] >= 75
    jobs = [e for e in p["experience"] if e["kind"] == "work"]
    assert [e["org"] for e in jobs] == ["Flipkart", "Zoho Corporation"] or [e["org"].split(",")[0] for e in jobs] == ["Flipkart", "Zoho Corporation"]
    assert "Kafka" in jobs[0]["tech"] and "Kafka" not in " ".join(jobs[1]["tech"])  # tech line stays with its own job
    assert p["totals"]["internships"] == 1 and p["totals"]["work_months"] > 90
    assert all(c["tier"] == "vendor" for c in p["certifications"])
