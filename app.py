"""
Resume Copilot — AI Career Assistant Platform
Single-file Flask backend: auth, resume parsing, ATS scoring, skill-gap analysis,
job matching, cover letter / cold email generation, application tracking,
interview prep, and career roadmaps.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://localhost:5000
"""

import os
import re
import io
import json
import sqlite3
import datetime
from functools import wraps

import jwt
from flask import Flask, request, jsonify, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Optional: python-docx / pdfplumber for parsing uploaded resumes
import pdfplumber
import docx

# Optional AI enhancement (Groq). If no key is set, we fall back to solid
# rule-based generation everywhere, so the app is 100% functional either way.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID", "").strip()
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "").strip()
ADZUNA_COUNTRY = os.environ.get("ADZUNA_COUNTRY", "in").strip().lower()
ADZUNA_URL = f"https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "resume_copilot.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "instance", "uploads")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me-in-prod")
ALLOWED_EXT = {"pdf", "docx"}

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB uploads


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            phone TEXT, college TEXT, branch TEXT, degree TEXT, grad_year TEXT,
            bio TEXT, linkedin TEXT, github TEXT, portfolio TEXT, cgpa TEXT,
            target_role TEXT DEFAULT 'AI Engineer',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            filename TEXT,
            raw_text TEXT,
            parsed_json TEXT,
            analysis_json TEXT,
            ats_score INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS saved_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            job_id TEXT NOT NULL,
            job_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, job_id)
        );

        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            job_id TEXT,
            status TEXT DEFAULT 'Applied',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    db.commit()
    db.close()


# --------------------------------------------------------------------------
# Auth helpers
# --------------------------------------------------------------------------

def make_token(user_id):
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "user_id": user_id,
        "exp": now + datetime.timedelta(days=7),
        "iat": now,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def auth_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        token = auth.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Session expired, please log in again"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        g.user_id = payload["user_id"]
        return f(*args, **kwargs)

    return wrapper


def current_user():
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (g.user_id,)).fetchone()
    return row


# --------------------------------------------------------------------------
# Domain knowledge: skills, role requirements, job dataset, question bank
# --------------------------------------------------------------------------

SKILL_KEYWORDS = [
    "python", "java", "c++", "c#", "javascript", "typescript", "sql", "nosql",
    "html", "css", "react", "angular", "vue", "node.js", "node", "express",
    "django", "flask", "fastapi", "spring", "pandas", "numpy", "scikit-learn",
    "sklearn", "tensorflow", "pytorch", "keras", "opencv", "nlp", "llm",
    "langchain", "machine learning", "deep learning", "data analysis",
    "data science", "data engineering", "power bi", "tableau", "excel",
    "aws", "azure", "gcp", "docker", "kubernetes", "ci/cd", "git", "github",
    "linux", "rest api", "graphql", "mongodb", "postgresql", "mysql", "redis",
    "kafka", "spark", "hadoop", "airflow", "microservices", "system design",
    "unit testing", "agile", "scrum", "figma", "ui/ux", "android", "ios",
    "swift", "kotlin", "go", "golang", "rust", "php", "ruby", "r",
    "computer vision", "statistics", "a/b testing", "etl", "dbt", "terraform",
    "jenkins", "cybersecurity", "networking", "blockchain", "solidity",
]

ACTION_VERBS = [
    "led", "built", "designed", "developed", "implemented", "created",
    "improved", "optimized", "managed", "launched", "automated", "reduced",
    "increased", "achieved", "delivered", "architected", "deployed",
    "streamlined", "spearheaded", "engineered", "analyzed", "collaborated",
    "mentored", "researched", "presented", "migrated",
]

ROLE_SKILL_MAP = {
    "AI Engineer": ["python", "machine learning", "deep learning", "pytorch",
                    "tensorflow", "nlp", "llm", "langchain", "sql", "docker",
                    "aws", "git", "system design"],
    "Backend Developer": ["python", "java", "sql", "rest api", "django",
                           "flask", "docker", "kubernetes", "postgresql",
                           "redis", "git", "system design", "microservices"],
    "Frontend Developer": ["javascript", "typescript", "react", "html",
                            "css", "vue", "git", "ui/ux", "figma", "rest api"],
    "Full Stack Developer": ["javascript", "react", "node.js", "sql",
                              "html", "css", "git", "docker", "rest api",
                              "mongodb", "system design"],
    "Data Scientist": ["python", "sql", "pandas", "numpy", "scikit-learn",
                        "machine learning", "statistics", "data analysis",
                        "tableau", "power bi", "a/b testing"],
    "Data Analyst": ["sql", "excel", "power bi", "tableau", "python",
                      "statistics", "data analysis", "etl"],
    "Data Engineer": ["python", "sql", "spark", "airflow", "kafka", "etl",
                       "aws", "docker", "hadoop", "dbt", "postgresql"],
    "DevOps Engineer": ["docker", "kubernetes", "ci/cd", "aws", "azure",
                         "terraform", "jenkins", "linux", "git", "networking"],
    "ML Engineer": ["python", "machine learning", "deep learning", "pytorch",
                     "tensorflow", "docker", "kubernetes", "aws", "sql",
                     "system design", "ci/cd"],
    "Product Manager": ["agile", "scrum", "figma", "sql", "data analysis",
                          "a/b testing", "ui/ux"],
}

JOBS = [
    {"id": "j1", "title": "AI Engineer", "company": "Northwind Labs", "location": "Bengaluru, IN", "remote": "Hybrid", "salary": "₹18-28 LPA", "experience": "1-3 yrs", "rating": 4.4,
     "skills": ["python", "machine learning", "pytorch", "nlp", "llm", "docker", "aws"], "apply_link": "https://example.com/jobs/j1"},
    {"id": "j2", "title": "Machine Learning Engineer", "company": "Vertex Analytics", "location": "Remote", "remote": "Remote", "salary": "$70k-95k", "experience": "2-4 yrs", "rating": 4.2,
     "skills": ["python", "tensorflow", "machine learning", "sql", "docker", "kubernetes"], "apply_link": "https://example.com/jobs/j2"},
    {"id": "j3", "title": "Backend Developer", "company": "Fenwick Systems", "location": "Pune, IN", "remote": "On-site", "salary": "₹10-16 LPA", "experience": "0-2 yrs", "rating": 4.0,
     "skills": ["python", "django", "sql", "rest api", "postgresql", "git"], "apply_link": "https://example.com/jobs/j3"},
    {"id": "j4", "title": "Python Developer", "company": "Cobalt Softworks", "location": "Remote", "remote": "Remote", "salary": "₹8-14 LPA", "experience": "0-2 yrs", "rating": 3.9,
     "skills": ["python", "flask", "sql", "git", "rest api"], "apply_link": "https://example.com/jobs/j4"},
    {"id": "j5", "title": "Data Scientist", "company": "Harborlight Analytics", "location": "Hyderabad, IN", "remote": "Hybrid", "salary": "₹14-22 LPA", "experience": "1-3 yrs", "rating": 4.3,
     "skills": ["python", "pandas", "numpy", "scikit-learn", "statistics", "sql"], "apply_link": "https://example.com/jobs/j5"},
    {"id": "j6", "title": "Data Analyst", "company": "Bluepeak Retail", "location": "Remote", "remote": "Remote", "salary": "₹7-11 LPA", "experience": "0-2 yrs", "rating": 3.8,
     "skills": ["sql", "excel", "power bi", "tableau", "data analysis"], "apply_link": "https://example.com/jobs/j6"},
    {"id": "j7", "title": "Full Stack Developer", "company": "Ridgeline Apps", "location": "Gurugram, IN", "remote": "Hybrid", "salary": "₹12-20 LPA", "experience": "1-3 yrs", "rating": 4.1,
     "skills": ["javascript", "react", "node.js", "sql", "mongodb", "git"], "apply_link": "https://example.com/jobs/j7"},
    {"id": "j8", "title": "Frontend Developer", "company": "Lumen Studio", "location": "Remote", "remote": "Remote", "salary": "₹9-15 LPA", "experience": "0-2 yrs", "rating": 4.0,
     "skills": ["javascript", "react", "html", "css", "figma", "git"], "apply_link": "https://example.com/jobs/j8"},
    {"id": "j9", "title": "Data Engineer", "company": "Ironbridge Cloud", "location": "Remote", "remote": "Remote", "salary": "$80k-110k", "experience": "2-5 yrs", "rating": 4.2,
     "skills": ["python", "sql", "spark", "airflow", "aws", "etl"], "apply_link": "https://example.com/jobs/j9"},
    {"id": "j10", "title": "DevOps Engineer", "company": "Sterling Cloud Co", "location": "Chennai, IN", "remote": "Hybrid", "salary": "₹15-24 LPA", "experience": "2-4 yrs", "rating": 4.1,
     "skills": ["docker", "kubernetes", "aws", "terraform", "ci/cd", "linux"], "apply_link": "https://example.com/jobs/j10"},
    {"id": "j11", "title": "NLP Engineer", "company": "Verbatim AI", "location": "Remote", "remote": "Remote", "salary": "$85k-120k", "experience": "1-4 yrs", "rating": 4.5,
     "skills": ["python", "nlp", "llm", "langchain", "pytorch", "machine learning"], "apply_link": "https://example.com/jobs/j11"},
    {"id": "j12", "title": "Software Engineer Intern", "company": "Cascade Systems", "location": "Remote", "remote": "Remote", "salary": "₹25k-40k/mo", "experience": "0-1 yrs", "rating": 3.9,
     "skills": ["python", "git", "sql", "rest api"], "apply_link": "https://example.com/jobs/j12"},
    {"id": "j13", "title": "Product Manager", "company": "Northstar Products", "location": "Mumbai, IN", "remote": "Hybrid", "salary": "₹18-30 LPA", "experience": "2-5 yrs", "rating": 4.3,
     "skills": ["agile", "scrum", "sql", "data analysis", "figma"], "apply_link": "https://example.com/jobs/j13"},
    {"id": "j14", "title": "Cloud/ML Ops Engineer", "company": "Vantage Cloud", "location": "Remote", "remote": "Remote", "salary": "$90k-125k", "experience": "2-5 yrs", "rating": 4.2,
     "skills": ["docker", "kubernetes", "aws", "python", "ci/cd", "machine learning"], "apply_link": "https://example.com/jobs/j14"},
    {"id": "j15", "title": "Junior Data Scientist", "company": "Kepler Insights", "location": "Remote", "remote": "Remote", "salary": "₹9-13 LPA", "experience": "0-1 yrs", "rating": 3.9,
     "skills": ["python", "pandas", "sql", "statistics", "machine learning"], "apply_link": "https://example.com/jobs/j15"},
]

INTERVIEW_BANK = {
    "Technical": {
        "Easy": ["What is the difference between a list and a tuple in Python?",
                 "Explain the difference between SQL JOIN types.",
                 "What is a REST API and why is it stateless?"],
        "Medium": ["How would you design a rate limiter?",
                   "Explain how indexing improves SQL query performance.",
                   "Walk through how gradient descent works."],
        "Hard": ["Design a scalable URL shortener handling 100M requests/day.",
                 "How would you architect a real-time recommendation system?",
                 "Explain how transformer attention mechanisms work end to end."],
    },
    "HR": {
        "Easy": ["Tell me about yourself.", "Why do you want to work here?",
                  "What are your strengths and weaknesses?"],
        "Medium": ["Where do you see yourself in 5 years?",
                   "Why did you choose this career path?",
                   "How do you handle criticism?"],
        "Hard": ["Why should we hire you over other candidates?",
                  "Describe a time you disagreed with your manager and how you handled it.",
                  "What would you do if you found a critical bug right before a launch?"],
    },
    "Behavioral": {
        "Easy": ["Describe a time you worked in a team.",
                  "Tell me about a project you're proud of."],
        "Medium": ["Tell me about a time you missed a deadline. What happened?",
                   "Describe a conflict with a teammate and how you resolved it."],
        "Hard": ["Tell me about a time you had to make a decision with incomplete information.",
                  "Describe the hardest technical problem you've solved and your process."],
    },
    "Coding": {
        "Easy": ["Reverse a string without using built-in reverse functions.",
                  "Find the maximum element in an array."],
        "Medium": ["Given an array, find two numbers that sum to a target (two-sum).",
                   "Detect a cycle in a linked list."],
        "Hard": ["Find the shortest path in a weighted graph (Dijkstra's).",
                  "Implement an LRU cache with O(1) get/put."],
    },
    "System Design": {
        "Easy": ["What is horizontal vs vertical scaling?",
                  "What is a load balancer and why is it used?"],
        "Medium": ["Design a basic notification system.",
                   "How would you design a URL shortening service?"],
        "Hard": ["Design a distributed job scheduler.",
                  "Design the backend for a live chat application at scale."],
    },
}


# --------------------------------------------------------------------------
# Resume parsing & analysis
# --------------------------------------------------------------------------

def extract_text(filepath, ext):
    if ext == "pdf":
        text = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                text.append(t)
        return "\n".join(text)
    elif ext == "docx":
        d = docx.Document(filepath)
        return "\n".join(p.text for p in d.paragraphs)
    return ""


_SKILL_PATTERN_CACHE = {}


def skill_present(skill, lower_text):
    """Match a skill keyword as a whole word/phrase, not as a loose substring
    (avoids e.g. the single letter "r" matching inside "career")."""
    pattern = _SKILL_PATTERN_CACHE.get(skill)
    if pattern is None:
        escaped = re.escape(skill)
        # Lookaround word boundaries that also work for tokens with symbols
        # like "c++", "c#", "node.js".
        pattern = re.compile(r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])")
        _SKILL_PATTERN_CACHE[skill] = pattern
    return bool(pattern.search(lower_text))


def parse_resume(text):
    lower = text.lower()

    email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\d{10}", text)
    linkedin_match = re.search(r"(https?://)?(www\.)?linkedin\.com/\S+", text, re.I)
    github_match = re.search(r"(https?://)?(www\.)?github\.com/\S+", text, re.I)

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    name = lines[0][:60] if lines else "Unknown"
    # avoid picking up an email/heading as name
    if email_match and email_match.group(0) in name:
        name = lines[1][:60] if len(lines) > 1 else "Unknown"

    found_skills = sorted({s for s in SKILL_KEYWORDS if skill_present(s, lower)})

    education_kw = ["b.tech", "btech", "bachelor", "m.tech", "mtech", "master",
                     "b.sc", "bsc", "m.sc", "msc", "mba", "phd", "university", "college"]
    has_education = any(k in lower for k in education_kw)

    experience_kw = ["experience", "internship", "intern", "work history"]
    has_experience = any(k in lower for k in experience_kw)

    projects_kw = ["project", "projects"]
    has_projects = any(k in lower for k in projects_kw)

    achievements_kw = ["achievement", "award", "certification", "certificate"]
    has_achievements = any(k in lower for k in achievements_kw)

    return {
        "name": name,
        "email": email_match.group(0) if email_match else None,
        "phone": phone_match.group(0) if phone_match else None,
        "linkedin": linkedin_match.group(0) if linkedin_match else None,
        "github": github_match.group(0) if github_match else None,
        "skills": found_skills,
        "has_education": has_education,
        "has_experience": has_experience,
        "has_projects": has_projects,
        "has_achievements": has_achievements,
        "word_count": len(text.split()),
    }


def analyze_resume(text, parsed):
    lower = text.lower()
    breakdown = {}
    suggestions = []

    # Contact info — 10 pts
    contact_score = 0
    if parsed["email"]:
        contact_score += 5
    if parsed["phone"]:
        contact_score += 5
    if contact_score < 10:
        suggestions.append("Add a professional email and phone number near the top of your resume.")
    breakdown["contact_info"] = contact_score

    # Skills — 20 pts
    n_skills = len(parsed["skills"])
    skills_score = min(20, n_skills * 2)
    if n_skills < 6:
        suggestions.append("List more relevant technical skills — aim for at least 8-10 keyword matches for your target role.")
    breakdown["skills"] = skills_score

    # Action verbs — 15 pts
    verb_count = sum(1 for v in ACTION_VERBS if re.search(r"\b" + re.escape(v) + r"\b", lower))
    verbs_score = min(15, verb_count * 2)
    if verb_count < 5:
        suggestions.append("Use stronger action verbs (e.g. 'built', 'optimized', 'led') to start your bullet points.")
    breakdown["action_verbs"] = verbs_score

    # Quantifiable achievements — 15 pts
    numbers = re.findall(r"\d+%|\$\d+|\d+x|\b\d{2,}\b", text)
    metrics_score = min(15, len(numbers) * 2)
    if len(numbers) < 3:
        suggestions.append("Add measurable impact — numbers, percentages, or metrics (e.g. 'reduced load time by 30%').")
    breakdown["quantifiable_impact"] = metrics_score

    # Section completeness — 20 pts
    section_score = 0
    if parsed["has_education"]:
        section_score += 5
    else:
        suggestions.append("Add an Education section.")
    if parsed["has_experience"]:
        section_score += 5
    else:
        suggestions.append("Add a Work Experience / Internship section.")
    if parsed["has_projects"]:
        section_score += 5
    else:
        suggestions.append("Add a Projects section — recruiters weigh this heavily for early-career roles.")
    if parsed["has_achievements"]:
        section_score += 5
    else:
        suggestions.append("Add an Achievements/Certifications section if you have any.")
    breakdown["sections"] = section_score

    # Length — 10 pts
    wc = parsed["word_count"]
    if 300 <= wc <= 900:
        length_score = 10
    elif 200 <= wc < 300 or 900 < wc <= 1100:
        length_score = 6
        suggestions.append("Adjust resume length — aim for roughly 350-800 words (about one page).")
    else:
        length_score = 3
        suggestions.append("Your resume is too short or too long — aim for roughly 350-800 words (about one page).")
    breakdown["length"] = length_score

    # Readability / grammar heuristic — 10 pts
    sentences = re.split(r"[.\n]", text)
    long_sentences = [s for s in sentences if len(s.split()) > 35]
    readability_score = 10 if len(long_sentences) <= 2 else max(0, 10 - len(long_sentences))
    if len(long_sentences) > 2:
        suggestions.append("Break up long, run-on lines into concise bullet points for readability.")
    breakdown["readability"] = readability_score

    total = sum(breakdown.values())

    # Predicted role: best match against ROLE_SKILL_MAP
    best_role, best_overlap = None, -1
    for role, req_skills in ROLE_SKILL_MAP.items():
        overlap = len(set(parsed["skills"]) & set(req_skills))
        if overlap > best_overlap:
            best_role, best_overlap = role, overlap

    strengths = []
    if skills_score >= 14:
        strengths.append("Strong, relevant technical skill set")
    if verbs_score >= 10:
        strengths.append("Good use of action-oriented language")
    if metrics_score >= 10:
        strengths.append("Includes quantifiable achievements")
    if section_score >= 15:
        strengths.append("Well-structured with clear sections")
    if not strengths:
        strengths.append("Resume has a base structure to build on")

    weaknesses = suggestions[:5] if suggestions else ["No major weaknesses detected — nice work!"]

    summary = (
        f"This resume shows strongest alignment with a {best_role} role, with "
        f"{n_skills} relevant skills detected. Overall ATS readiness is "
        f"{'excellent' if total >= 85 else 'good' if total >= 65 else 'needs improvement'}."
    )

    return {
        "ats_score": total,
        "breakdown": breakdown,
        "predicted_role": best_role,
        "summary": summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "suggestions": suggestions,
    }


def rule_based_optimize(text, parsed, analysis):
    """Produces an improved resume draft using rule-based rewriting."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    improved_lines = []
    for line in lines:
        new_line = line
        # Add a leading action verb hint to bullet-like lines lacking one
        if len(line.split()) > 3 and not any(line.lower().startswith(v) for v in ACTION_VERBS):
            if line.startswith(("-", "•", "*")):
                content = line.lstrip("-•* ").strip()
                if content and content[0].islower():
                    new_line = f"- Built {content}"
        improved_lines.append(new_line)

    header_suggestions = []
    if analysis["breakdown"]["quantifiable_impact"] < 10:
        header_suggestions.append("Consider adding metrics to your bullet points, e.g. '...improving performance by 25%'.")
    if analysis["breakdown"]["skills"] < 16:
        missing_common = [s for s in ["docker", "git", "sql", "aws"] if s not in parsed["skills"]]
        if missing_common:
            header_suggestions.append(f"Consider adding widely-requested skills you may already have exposure to: {', '.join(missing_common)}.")

    optimized_text = "\n".join(improved_lines)
    return {
        "optimized_text": optimized_text,
        "notes": header_suggestions or ["Your resume structure is solid — mainly focus on quantifying impact further."],
    }


def skill_gap(parsed_skills, target_role):
    required = ROLE_SKILL_MAP.get(target_role, ROLE_SKILL_MAP["AI Engineer"])
    have = set(parsed_skills)
    missing = [s for s in required if s not in have]
    return {
        "target_role": target_role,
        "current_skills": sorted(have),
        "missing_skills": missing,
        "matched_skills": [s for s in required if s in have],
    }


def build_roadmap(target_role, missing_skills):
    weeks = []
    skills_to_learn = missing_skills or ROLE_SKILL_MAP.get(target_role, [])[:6]
    idx = 0
    for week in range(1, 9):
        if idx < len(skills_to_learn):
            topic = skills_to_learn[idx]
            weeks.append({"week": week, "focus": topic.title(),
                           "goal": f"Learn the fundamentals of {topic} and build one small project using it."})
            idx += 1
        else:
            break
    weeks.append({"week": len(weeks) + 1, "focus": "Portfolio Projects",
                   "goal": f"Build 1-2 projects that combine your {target_role} skills end to end."})
    weeks.append({"week": len(weeks) + 1, "focus": "Resume & Applications",
                   "goal": "Update your resume with new skills/projects and start applying."})
    weeks.append({"week": len(weeks) + 1, "focus": "Interview Preparation",
                   "goal": f"Practice technical and behavioral interview questions for {target_role} roles."})
    return weeks


def match_jobs_local(user_skills, top_n=5):
    """Match against the built-in sample dataset (used when no Adzuna keys are set,
    or as a fallback if the live API call fails)."""
    have = set(user_skills)
    results = []
    for job in JOBS:
        req = set(job["skills"])
        if not req:
            continue
        overlap = have & req
        score = round(100 * len(overlap) / len(req), 1)
        missing = sorted(req - have)
        results.append({
            **job,
            "match_score": score,
            "matching_skills": sorted(overlap),
            "missing_skills": missing,
        })
    results.sort(key=lambda j: j["match_score"], reverse=True)
    return results[:top_n]


def fetch_live_jobs(user_skills, target_role=None, location=None, top_n=5):
    """Fetch real, current listings from the Adzuna API and score them against
    the user's skills. Returns None (so callers fall back to the local sample
    dataset) if Adzuna keys aren't configured or the request fails."""
    if not (ADZUNA_APP_ID and ADZUNA_APP_KEY):
        return None

    query = target_role or (user_skills[0] if user_skills else "software developer")
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": 20,
        "what": query,
        "content-type": "application/json",
    }
    if location:
        params["where"] = location

    try:
        resp = requests.get(ADZUNA_URL, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    have = set(user_skills)
    results = []
    for r in data.get("results", []):
        description = (r.get("description") or "")
        title = r.get("title") or "Untitled role"
        desc_lower = description.lower()
        # Adzuna doesn't return a structured skills list, so we derive it by
        # scanning the job description for the same skill keywords we use to
        # parse resumes — keeps matching logic consistent across both sources.
        req_skills = sorted({s for s in SKILL_KEYWORDS if skill_present(s, desc_lower)})
        overlap = have & set(req_skills)
        score = round(100 * len(overlap) / len(req_skills), 1) if req_skills else 0.0

        salary_min, salary_max = r.get("salary_min"), r.get("salary_max")
        if salary_min and salary_max:
            salary = f"₹{int(salary_min):,} - ₹{int(salary_max):,}" if ADZUNA_COUNTRY == "in" else f"${int(salary_min):,} - ${int(salary_max):,}"
        else:
            salary = "Not disclosed"

        location_name = (r.get("location") or {}).get("display_name", "Not specified")

        results.append({
            "id": str(r.get("id")),
            "title": title,
            "company": (r.get("company") or {}).get("display_name", "Unknown company"),
            "location": location_name,
            "remote": "Not specified",
            "salary": salary,
            "experience": "Not specified",
            "rating": None,
            "skills": req_skills,
            "apply_link": r.get("redirect_url", "#"),
            "match_score": score,
            "matching_skills": sorted(overlap),
            "missing_skills": sorted(set(req_skills) - have),
        })

    results.sort(key=lambda j: j["match_score"], reverse=True)
    return results[:top_n]


def match_jobs(user_skills, target_role=None, location=None, top_n=5):
    """Live Adzuna results if configured, else the local sample dataset."""
    live = fetch_live_jobs(user_skills, target_role=target_role, location=location, top_n=top_n)
    if live is not None:
        return live
    return match_jobs_local(user_skills, top_n=top_n)


def call_groq(prompt, system="You are a professional career writing assistant."):
    """Optional AI enhancement. Returns None if no key configured or on failure."""
    if not GROQ_API_KEY:
        return None
    try:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.6,
                "max_tokens": 700,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def generate_cover_letter(user_row, parsed, job):
    name = user_row["name"]
    role = job["title"]
    company = job["company"]
    matching = ", ".join(job.get("matching_skills") or parsed.get("skills", [])[:5])

    ai_prompt = (
        f"Write a concise, professional cover letter (under 300 words) for {name} applying to the "
        f"{role} role at {company}. Their key skills: {matching}. Do not use placeholders."
    )
    ai_text = call_groq(ai_prompt)
    if ai_text:
        return ai_text

    return (
        f"Dear {company} Hiring Team,\n\n"
        f"I'm excited to apply for the {role} position at {company}. With hands-on experience in "
        f"{matching or 'relevant technologies'}, I'm confident I can contribute meaningfully to your team from day one.\n\n"
        f"In my recent projects, I've applied these skills to build practical, real-world solutions, and I'm "
        f"particularly drawn to {company}'s work in this space. I'd welcome the opportunity to bring my "
        f"technical skills and problem-solving mindset to your team.\n\n"
        f"Thank you for considering my application — I'd love the chance to discuss how I can contribute.\n\n"
        f"Best regards,\n{name}"
    )


def generate_cold_email(user_row, parsed, job):
    name = user_row["name"]
    role = job["title"]
    company = job["company"]
    matching = ", ".join(job.get("matching_skills") or parsed.get("skills", [])[:5])

    ai_prompt = (
        f"Write a short, professional cold outreach email (under 150 words) from {name} to a recruiter at "
        f"{company} about the {role} role, mentioning skills: {matching}. Include a subject line."
    )
    ai_text = call_groq(ai_prompt)
    if ai_text:
        return ai_text

    subject = f"Subject: Interest in the {role} role at {company}\n\n"
    body = (
        f"Hi there,\n\n"
        f"I came across the {role} opening at {company} and wanted to reach out directly. "
        f"I have hands-on experience with {matching or 'relevant tools for this role'} and I think there could be "
        f"a strong fit with your team.\n\n"
        f"I've attached my resume and cover letter — I'd love the chance for a quick conversation "
        f"about how I can contribute.\n\n"
        f"Best,\n{name}"
    )
    return subject + body


# --------------------------------------------------------------------------
# Routes: static frontend
# --------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


# --------------------------------------------------------------------------
# Routes: auth & profile
# --------------------------------------------------------------------------

@app.post("/api/register")
def register():
    data = request.get_json(force=True) or {}
    required = ["name", "email", "password"]
    if not all(data.get(f) for f in required):
        return jsonify({"error": "Name, email and password are required"}), 400

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (data["email"].lower(),)).fetchone()
    if existing:
        return jsonify({"error": "An account with this email already exists"}), 409

    pw_hash = generate_password_hash(data["password"])
    cur = db.execute(
        """INSERT INTO users (name, email, password_hash, phone, college, branch, degree, grad_year)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (data["name"], data["email"].lower(), pw_hash, data.get("phone"),
         data.get("college"), data.get("branch"), data.get("degree"), data.get("grad_year")),
    )
    db.commit()
    user_id = cur.lastrowid
    token = make_token(user_id)
    return jsonify({"token": token, "user": {"id": user_id, "name": data["name"], "email": data["email"]}}), 201


@app.post("/api/login")
def login():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").lower()
    password = data.get("password") or ""
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "Invalid email or password"}), 401
    token = make_token(row["id"])
    return jsonify({"token": token, "user": {"id": row["id"], "name": row["name"], "email": row["email"]}})


@app.get("/api/profile")
@auth_required
def get_profile():
    row = current_user()
    if not row:
        return jsonify({"error": "User not found"}), 404
    user = dict(row)
    user.pop("password_hash", None)
    return jsonify(user)


@app.put("/api/profile")
@auth_required
def update_profile():
    data = request.get_json(force=True) or {}
    fields = ["name", "phone", "college", "branch", "degree", "grad_year",
              "bio", "linkedin", "github", "portfolio", "cgpa", "target_role"]
    updates = {k: data[k] for k in fields if k in data}
    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400
    db = get_db()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    db.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*updates.values(), g.user_id))
    db.commit()
    return jsonify({"message": "Profile updated"})


# --------------------------------------------------------------------------
# Routes: resume upload / parsing / analysis / optimization
# --------------------------------------------------------------------------

@app.post("/api/resume/upload")
@auth_required
def upload_resume():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        return jsonify({"error": "Only PDF and DOCX files are supported"}), 400

    filename = secure_filename(f"{g.user_id}_{datetime.datetime.utcnow().timestamp()}.{ext}")
    filepath = os.path.join(UPLOAD_DIR, filename)
    file.save(filepath)

    try:
        text = extract_text(filepath, ext)
        if not text or not text.strip():
            return jsonify({"error": "Could not extract text from this file. Try a different export of your resume."}), 422
        parsed = parse_resume(text)
        analysis = analyze_resume(text, parsed)
    except Exception as e:
        return jsonify({"error": f"Failed to process resume: {e}"}), 500

    db = get_db()
    cur = db.execute(
        """INSERT INTO resumes (user_id, filename, raw_text, parsed_json, analysis_json, ats_score)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (g.user_id, file.filename, text, json.dumps(parsed), json.dumps(analysis), analysis["ats_score"]),
    )
    db.commit()
    resume_id = cur.lastrowid

    return jsonify({"resume_id": resume_id, "parsed": parsed, "analysis": analysis}), 201


@app.get("/api/resume/history")
@auth_required
def resume_history():
    db = get_db()
    rows = db.execute(
        "SELECT id, filename, ats_score, created_at FROM resumes WHERE user_id = ? ORDER BY created_at DESC",
        (g.user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/resume/<int:resume_id>")
@auth_required
def get_resume(resume_id):
    db = get_db()
    row = db.execute("SELECT * FROM resumes WHERE id = ? AND user_id = ?", (resume_id, g.user_id)).fetchone()
    if not row:
        return jsonify({"error": "Resume not found"}), 404
    result = dict(row)
    result["parsed_json"] = json.loads(result["parsed_json"])
    result["analysis_json"] = json.loads(result["analysis_json"])
    return jsonify(result)


@app.post("/api/resume/<int:resume_id>/optimize")
@auth_required
def optimize_resume(resume_id):
    db = get_db()
    row = db.execute("SELECT * FROM resumes WHERE id = ? AND user_id = ?", (resume_id, g.user_id)).fetchone()
    if not row:
        return jsonify({"error": "Resume not found"}), 404
    parsed = json.loads(row["parsed_json"])
    analysis = json.loads(row["analysis_json"])

    ai_prompt = (
        "Rewrite the following resume text to be more ATS-friendly: use strong action verbs, "
        "add measurable impact where plausible, and keep the same facts (do not invent employers "
        "or dates). Return only the improved resume text.\n\n" + row["raw_text"][:4000]
    )
    ai_text = call_groq(ai_prompt, system="You are an expert resume writer and ATS optimization specialist.")
    if ai_text:
        result = {"optimized_text": ai_text, "notes": ["Rewritten with AI for stronger phrasing and ATS keyword alignment."]}
    else:
        result = rule_based_optimize(row["raw_text"], parsed, analysis)

    return jsonify({"original_text": row["raw_text"], **result})


@app.post("/api/resume/<int:resume_id>/skill-gap")
@auth_required
def resume_skill_gap(resume_id):
    data = request.get_json(force=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM resumes WHERE id = ? AND user_id = ?", (resume_id, g.user_id)).fetchone()
    if not row:
        return jsonify({"error": "Resume not found"}), 404
    parsed = json.loads(row["parsed_json"])
    target_role = data.get("target_role") or "AI Engineer"
    gap = skill_gap(parsed["skills"], target_role)
    roadmap = build_roadmap(target_role, gap["missing_skills"])
    return jsonify({"skill_gap": gap, "roadmap": roadmap})


# --------------------------------------------------------------------------
# Routes: jobs
# --------------------------------------------------------------------------

@app.post("/api/jobs/recommend")
@auth_required
def jobs_recommend():
    data = request.get_json(force=True) or {}
    resume_id = data.get("resume_id")
    db = get_db()
    user = current_user()
    if resume_id:
        row = db.execute("SELECT * FROM resumes WHERE id = ? AND user_id = ?", (resume_id, g.user_id)).fetchone()
        if not row:
            return jsonify({"error": "Resume not found"}), 404
        parsed = json.loads(row["parsed_json"])
        skills = parsed["skills"]
    else:
        skills = data.get("skills", [])
    target_role = data.get("target_role") or (user["target_role"] if user else None)
    location = data.get("location")
    matches = match_jobs(skills, target_role=target_role, location=location)
    return jsonify(matches)


@app.post("/api/jobs/save")
@auth_required
def save_job():
    """Saves a job the client already has (from /jobs/recommend results),
    since live Adzuna jobs aren't in our local dataset to look up by id."""
    job = request.get_json(force=True) or {}
    job_id = job.get("id")
    if not job_id:
        return jsonify({"error": "Job data with an id is required"}), 400
    db = get_db()
    try:
        db.execute("INSERT INTO saved_jobs (user_id, job_id, job_json) VALUES (?, ?, ?)",
                   (g.user_id, job_id, json.dumps(job)))
        db.commit()
    except sqlite3.IntegrityError:
        pass
    return jsonify({"message": "Job saved"})


@app.delete("/api/jobs/save/<job_id>")
@auth_required
def unsave_job(job_id):
    db = get_db()
    db.execute("DELETE FROM saved_jobs WHERE user_id = ? AND job_id = ?", (g.user_id, job_id))
    db.commit()
    return jsonify({"message": "Job removed"})


@app.get("/api/jobs/saved")
@auth_required
def saved_jobs():
    db = get_db()
    rows = db.execute("SELECT job_json FROM saved_jobs WHERE user_id = ? ORDER BY created_at DESC", (g.user_id,)).fetchall()
    return jsonify([json.loads(r["job_json"]) for r in rows])


# --------------------------------------------------------------------------
# Routes: cover letters, cold emails
# --------------------------------------------------------------------------

@app.post("/api/coverletter")
@auth_required
def cover_letter():
    data = request.get_json(force=True) or {}
    resume_id = data.get("resume_id")
    db = get_db()
    user_row = current_user()
    resume_row = db.execute("SELECT * FROM resumes WHERE id = ? AND user_id = ?", (resume_id, g.user_id)).fetchone()
    if not resume_row:
        return jsonify({"error": "Resume not found"}), 404
    parsed = json.loads(resume_row["parsed_json"])

    # The frontend passes the full job object it already has from
    # /jobs/recommend (works whether that came from live Adzuna results or
    # the local sample dataset) — falls back to local JOBS by id for
    # backwards compatibility, then to plain role/company text.
    job = data.get("job")
    if not job and data.get("job_id"):
        job = next((j for j in JOBS if j["id"] == data["job_id"]), None)
    if not job:
        job = {"title": data.get("role", "the role"), "company": data.get("company", "your company"), "skills": []}
    job = {**job, "matching_skills": [s for s in job.get("skills", []) if s in parsed["skills"]]}

    letter = generate_cover_letter(user_row, parsed, job)
    return jsonify({"cover_letter": letter})


@app.post("/api/coldemail")
@auth_required
def cold_email():
    data = request.get_json(force=True) or {}
    resume_id = data.get("resume_id")
    db = get_db()
    user_row = current_user()
    resume_row = db.execute("SELECT * FROM resumes WHERE id = ? AND user_id = ?", (resume_id, g.user_id)).fetchone()
    if not resume_row:
        return jsonify({"error": "Resume not found"}), 404
    parsed = json.loads(resume_row["parsed_json"])

    job = data.get("job")
    if not job and data.get("job_id"):
        job = next((j for j in JOBS if j["id"] == data["job_id"]), None)
    if not job:
        job = {"title": data.get("role", "the role"), "company": data.get("company", "your company"), "skills": []}
    job = {**job, "matching_skills": [s for s in job.get("skills", []) if s in parsed["skills"]]}

    email_text = generate_cold_email(user_row, parsed, job)
    return jsonify({"cold_email": email_text})


# --------------------------------------------------------------------------
# Routes: application tracker
# --------------------------------------------------------------------------

@app.post("/api/applications")
@auth_required
def create_application():
    data = request.get_json(force=True) or {}
    if not data.get("company") or not data.get("role"):
        return jsonify({"error": "Company and role are required"}), 400
    db = get_db()
    cur = db.execute(
        "INSERT INTO applications (user_id, company, role, job_id, status, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (g.user_id, data["company"], data["role"], data.get("job_id"), data.get("status", "Applied"), data.get("notes", "")),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "message": "Application tracked"}), 201


@app.get("/api/applications")
@auth_required
def list_applications():
    db = get_db()
    rows = db.execute("SELECT * FROM applications WHERE user_id = ? ORDER BY created_at DESC", (g.user_id,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.put("/api/applications/<int:app_id>")
@auth_required
def update_application(app_id):
    data = request.get_json(force=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM applications WHERE id = ? AND user_id = ?", (app_id, g.user_id)).fetchone()
    if not row:
        return jsonify({"error": "Application not found"}), 404
    status = data.get("status", row["status"])
    notes = data.get("notes", row["notes"])
    db.execute(
        "UPDATE applications SET status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, notes, app_id),
    )
    db.commit()
    return jsonify({"message": "Application updated"})


@app.delete("/api/applications/<int:app_id>")
@auth_required
def delete_application(app_id):
    db = get_db()
    db.execute("DELETE FROM applications WHERE id = ? AND user_id = ?", (app_id, g.user_id))
    db.commit()
    return jsonify({"message": "Application deleted"})


# --------------------------------------------------------------------------
# Routes: interview prep & roadmap
# --------------------------------------------------------------------------

@app.get("/api/interview/questions")
@auth_required
def interview_questions():
    category = request.args.get("category", "Technical")
    difficulty = request.args.get("difficulty", "Medium")
    bank = INTERVIEW_BANK.get(category, INTERVIEW_BANK["Technical"])
    questions = bank.get(difficulty, bank["Medium"])
    return jsonify({"category": category, "difficulty": difficulty, "questions": questions})


@app.get("/api/roadmap/<role>")
@auth_required
def roadmap(role):
    db = get_db()
    latest = db.execute(
        "SELECT parsed_json FROM resumes WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (g.user_id,)
    ).fetchone()
    user_skills = json.loads(latest["parsed_json"])["skills"] if latest else []
    gap = skill_gap(user_skills, role)
    weeks = build_roadmap(role, gap["missing_skills"])
    return jsonify({"target_role": role, "skill_gap": gap, "roadmap": weeks})


# --------------------------------------------------------------------------
# Routes: dashboard
# --------------------------------------------------------------------------

@app.get("/api/dashboard")
@auth_required
def dashboard():
    db = get_db()
    user = current_user()

    resumes = db.execute("SELECT ats_score, created_at FROM resumes WHERE user_id = ? ORDER BY created_at", (g.user_id,)).fetchall()
    latest_resume = db.execute(
        "SELECT id, parsed_json, analysis_json, ats_score FROM resumes WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
        (g.user_id,),
    ).fetchone()

    applications = db.execute("SELECT status FROM applications WHERE user_id = ?", (g.user_id,)).fetchall()
    saved = db.execute("SELECT COUNT(*) c FROM saved_jobs WHERE user_id = ?", (g.user_id,)).fetchone()

    status_counts = {}
    for a in applications:
        status_counts[a["status"]] = status_counts.get(a["status"], 0) + 1

    avg_ats = round(sum(r["ats_score"] for r in resumes) / len(resumes), 1) if resumes else 0

    top_skills, missing_skills, recommendations = [], [], []
    if latest_resume:
        parsed = json.loads(latest_resume["parsed_json"])
        analysis = json.loads(latest_resume["analysis_json"])
        top_skills = parsed["skills"][:8]
        target_role = user["target_role"] or analysis.get("predicted_role") or "AI Engineer"
        gap = skill_gap(parsed["skills"], target_role)
        missing_skills = gap["missing_skills"][:6]
        recommendations = analysis.get("suggestions", [])[:4]

    return jsonify({
        "name": user["name"],
        "average_ats": avg_ats,
        "resume_score_trend": [{"date": r["created_at"], "score": r["ats_score"]} for r in resumes],
        "total_applications": len(applications),
        "applications_by_status": status_counts,
        "saved_jobs_count": saved["c"],
        "top_skills": top_skills,
        "missing_skills": missing_skills,
        "ai_suggestions": recommendations,
        "has_resume": latest_resume is not None,
        "latest_ats_score": latest_resume["ats_score"] if latest_resume else None,
    })


# --------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
else:
    init_db()
