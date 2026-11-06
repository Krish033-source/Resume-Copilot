"""Deep links to platforms that have no public API (Internshala, Unstop, Devpost ...).
These are plain search URLs built from the user's role/skills; nothing is scraped."""
from __future__ import annotations

from datetime import date
from urllib.parse import quote, quote_plus


def build_links(query: str, location: str = "") -> list[dict]:
    q, qp, qd = quote(query), quote_plus(query), "-".join(query.lower().split())
    loc = quote_plus(location or "India")
    y = date.today().year
    return [
        {"group": "Internships", "name": "Internshala", "url": f"https://internshala.com/internships/keywords-{qd}/", "note": "India's largest internship board"},
        {"group": "Internships", "name": "Unstop", "url": f"https://unstop.com/internships?searchTerm={qp}", "note": "Internships, competitions and hackathons"},
        {"group": "Internships", "name": "LinkedIn (internships)", "url": f"https://www.linkedin.com/jobs/search/?keywords={qp}%20intern&location={loc}&f_E=1", "note": "Filtered to internship level"},
        {"group": "Jobs", "name": "LinkedIn Jobs", "url": f"https://www.linkedin.com/jobs/search/?keywords={qp}&location={loc}", "note": ""},
        {"group": "Jobs", "name": "Naukri", "url": f"https://www.naukri.com/{qd}-jobs", "note": ""},
        {"group": "Jobs", "name": "Indeed India", "url": f"https://in.indeed.com/jobs?q={qp}&l={quote_plus(location)}", "note": ""},
        {"group": "Jobs", "name": "Wellfound (startups)", "url": "https://wellfound.com/jobs", "note": "Startup roles"},
        {"group": "Freelance", "name": "Upwork", "url": f"https://www.upwork.com/nx/search/jobs/?q={qp}", "note": "Browse projects (API is partner-only)"},
        {"group": "Freelance", "name": "Freelancer", "url": f"https://www.freelancer.com/jobs/?keywords={qp}", "note": ""},
        {"group": "Freelance", "name": "Contra", "url": "https://contra.com/opportunities", "note": "Commission-free freelance"},
        {"group": "Hackathons", "name": "Devpost", "url": f"https://devpost.com/hackathons?search={qp}", "note": "Online hackathons"},
        {"group": "Hackathons", "name": "MLH", "url": f"https://mlh.io/seasons/{y}/events", "note": "Student hackathons"},
        {"group": "Hackathons", "name": "Kaggle competitions", "url": "https://www.kaggle.com/competitions", "note": "For data/ML roles"},
        {"group": "Open source", "name": "GitHub good first issues", "url": f"https://github.com/search?q=label%3A%22good+first+issue%22+{qp}+state%3Aopen&type=issues", "note": "Start with a small merged PR"},
        {"group": "Open source", "name": "Up For Grabs", "url": "https://up-for-grabs.net/", "note": "Beginner friendly projects"},
        {"group": "Open source", "name": "Google Summer of Code", "url": "https://summerofcode.withgoogle.com/", "note": "Stipend program, check eligibility"},
        {"group": "Open source", "name": "Outreachy", "url": "https://www.outreachy.org/", "note": "Paid remote internships"},
    ]
