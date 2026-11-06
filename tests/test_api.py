import io

from app.extensions import db
from app.models import Job
from app.sources import registry
from app.sources.base import Source
from app.sources.base import classify_kind

from .conftest import fixture_bytes


def test_register_login_logout_and_cookie_flags(client):
    r = client.post("/api/auth/register", json={"name": "A B", "email": "a@b.com", "password": "short"})
    assert r.status_code == 400
    r = client.post("/api/auth/register", json={"name": "A B", "email": "a@b.com", "password": "longenough1"})
    assert r.status_code == 201
    cookies = " ".join(r.headers.getlist("Set-Cookie"))
    assert "HttpOnly" in cookies and "access_token_cookie" in cookies
    assert client.post("/api/auth/register", json={"name": "A B", "email": "A@B.com", "password": "longenough1"}).status_code == 409
    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "a@b.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "A@b.com", "password": "longenough1"}).status_code == 200


def test_csrf_required_for_writes(user):
    r = user.c.post("/api/applications", json={"company": "X", "role": "Y"})  # no CSRF header
    assert r.status_code == 401
    assert user.post("/api/applications", json={"company": "X", "role": "Y"}).status_code == 201


def test_resume_upload_and_isolation(user, app):
    data = fixture_bytes("fresher.txt")
    r = user.post("/api/resumes", data={"file": (io.BytesIO(data), "cv.txt"), "target_role": "ML / AI Engineer"}, content_type="multipart/form-data")
    assert r.status_code == 201, r.get_json()
    j = r.get_json()
    assert j["ats_score"] >= 70 and j["analysis"]["stage"] == "fresher"
    rid = j["id"]
    # fake pdf is rejected by magic bytes
    bad = user.post("/api/resumes", data={"file": (io.BytesIO(b"hello"), "x.pdf")}, content_type="multipart/form-data")
    assert bad.status_code == 400
    # rescore by role
    rr = user.post(f"/api/resumes/{rid}/rescore", json={"role": "UI / UX Designer"})
    assert rr.get_json()["ats_score"] < j["ats_score"]
    assert user.get(f"/api/resumes/{rid}/download").data == data
    # another user cannot see it
    other = app.test_client()
    other.post("/api/auth/register", json={"name": "Other", "email": "o@o.com", "password": "Passw0rd!x"})
    assert other.get(f"/api/resumes/{rid}").status_code == 404
    assert user.post(f"/api/resumes/{rid}/ai-review").status_code == 503  # no GROQ key in tests


def test_applications_flow_and_analytics(user):
    a = user.post("/api/applications", json={"company": "Acme", "role": "SDE Intern", "kind": "internship", "status": "applied"}).get_json()
    assert user.patch(f"/api/applications/{a['id']}", json={"status": "interview"}).get_json()["status"] == "interview"
    assert user.patch(f"/api/applications/{a['id']}", json={"status": "bogus"}).status_code == 400
    o = user.get("/api/analytics/overview").get_json()
    assert o["pipeline"]["total"] == 1 and o["pipeline"]["response_rate"] == 100
    assert len(o["pipeline"]["heatmap"]) == 182 and len(o["pipeline"]["weekly"]) == 12
    assert user.delete(f"/api/applications/{a['id']}").status_code == 200


def _fake_rows():
    R = Source.row
    return [R("1", "Python Backend Intern", "Acme", "Remote", True, "internship", "https://x.test/1", "", "", "Work with Python, FastAPI, PostgreSQL and Docker. REST APIs.", ["python"], None),
            R("2", "Senior Staff Engineer", "BigCo", "Berlin", False, "job", "https://x.test/2", "", "", "Kubernetes Terraform Go", [], None),
            R("3", "Freelance React Developer", "Studio", "Remote", True, "freelance", "https://x.test/3", "", "", "React TypeScript contract", [], None)]


def test_opportunities_upsert_dedupe_match_and_save(user, app):
    app.config["AUTO_REFRESH_SOURCES"] = False
    assert registry.upsert_jobs(_fake_rows(), "remotive") == 3
    assert registry.upsert_jobs(_fake_rows(), "remotive") == 3
    assert db.session.query(Job).count() == 3  # deduped on (source, external_id)
    user.post("/api/resumes", data={"file": (io.BytesIO(fixture_bytes("fresher.txt")), "cv.txt"), "target_role": "Backend Developer"}, content_type="multipart/form-data")
    r = user.get("/api/opportunities?kind=internship").get_json()
    assert r["total"] == 1 and r["items"][0]["match"]["score"] > 40 and "python" in r["items"][0]["match"]["matched"]
    allr = user.get("/api/opportunities").get_json()
    assert allr["items"][0]["title"] == "Python Backend Intern"  # best match first, senior role last
    assert allr["items"][-1]["title"].startswith("Senior")
    jid = r["items"][0]["id"]
    assert user.post(f"/api/opportunities/{jid}/save").get_json()["saved"]
    assert len(user.get("/api/saved").get_json()["items"]) == 1
    t = user.post("/api/applications", json={"job_id": jid, "status": "saved"}).get_json()
    assert t["company"] == "Acme" and t["kind"] == "internship"


def test_claim_prevents_double_fetch(app):
    calls = []

    class Fake(Source):
        name, label = "remotive", "Fake"
        def fetch(self):
            calls.append(1)
            return _fake_rows()

    registry.BY_NAME["remotive"] = Fake()
    assert registry.refresh_source("remotive")["status"] == "ok"
    assert registry.refresh_source("remotive")["status"] == "fresh"  # within TTL
    assert len(calls) == 1


def test_source_failure_is_contained(app):
    class Boom(Source):
        name, label = "jobicy", "Boom"
        def fetch(self):
            raise RuntimeError("upstream 500")

    registry.BY_NAME["jobicy"] = Boom()
    r = registry.refresh_source("jobicy")
    assert r["status"] == "error"


def test_classify_kind():
    assert classify_kind("Data Science Intern") == "internship"
    assert classify_kind("Backend Dev", ["contract"]) == "freelance"
    assert classify_kind("Backend Dev", ["full_time"]) == "job"


def test_tools_without_ai(user):
    assert user.get("/api/meta").get_json()["ai_enabled"] is False
    o = user.post("/api/outreach", json={"kind": "cold_email", "company": "Acme", "role": "SDE"}).get_json()
    assert o["ai"] is False and "Acme" in o["body"]
    q = user.get("/api/interview/questions").get_json()
    assert q["questions"]
    e = user.post("/api/interview/evaluate", json={"role": "Software Engineer", "question": "q", "answer": "When I built our project I had to reduce latency. I used caching and cut p95 by 40% across 3 services."}).get_json()
    assert e["heuristic"] and e["score"] >= 5
