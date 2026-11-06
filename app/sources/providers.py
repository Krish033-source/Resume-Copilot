"""Concrete job sources. Free/public endpoints first; Adzuna needs keys.
Each provider returns normalized dicts (see Source.row)."""
from __future__ import annotations

from flask import current_app

from .base import Source, classify_kind, get_json, parse_dt, salary_text, strip_html


class Remotive(Source):
    name, label = "remotive", "Remotive"
    homepage = "https://remotive.com"
    attribution = "Jobs via Remotive"

    def fetch(self):
        data = get_json("https://remotive.com/api/remote-jobs", params={"limit": 200})
        out = []
        for j in data.get("jobs", []):
            title = j.get("title", "")
            out.append(self.row(j["id"], title, j.get("company_name"), j.get("candidate_required_location") or "Remote", True,
                                classify_kind(title, [j.get("job_type", "")], j.get("tags")), j.get("url"), j.get("salary", ""),
                                j.get("company_logo", ""), strip_html(j.get("description")), (j.get("tags") or []) + [j.get("category", "")],
                                parse_dt(j.get("publication_date"))))
        return out


class Arbeitnow(Source):
    name, label = "arbeitnow", "Arbeitnow"
    homepage = "https://www.arbeitnow.com"
    attribution = "Jobs via Arbeitnow"

    def fetch(self):
        out = []
        for page in (1, 2):
            data = get_json("https://www.arbeitnow.com/api/job-board-api", params={"page": page})
            for j in data.get("data", []):
                title = j.get("title", "")
                out.append(self.row(j.get("slug"), title, j.get("company_name"), j.get("location"), j.get("remote"),
                                    classify_kind(title, j.get("job_types"), j.get("tags")), j.get("url"), "", "",
                                    strip_html(j.get("description")), j.get("tags"), parse_dt(j.get("created_at"))))
        return out


class RemoteOK(Source):
    name, label = "remoteok", "Remote OK"
    homepage = "https://remoteok.com"
    attribution = "Jobs via Remote OK (remoteok.com)"

    def fetch(self):
        data = get_json("https://remoteok.com/api")
        out = []
        for j in data:
            if not isinstance(j, dict) or not j.get("position"):
                continue  # first element is a legal notice
            title = j["position"]
            out.append(self.row(j.get("id") or j.get("slug"), title, j.get("company"), j.get("location") or "Remote", True,
                                classify_kind(title, [], j.get("tags")), j.get("url") or j.get("apply_url"),
                                salary_text(j.get("salary_min"), j.get("salary_max"), "USD", "/yr"), j.get("company_logo") or j.get("logo", ""),
                                strip_html(j.get("description")), j.get("tags"), parse_dt(j.get("epoch") or j.get("date"))))
        return out


class Jobicy(Source):
    name, label = "jobicy", "Jobicy"
    homepage = "https://jobicy.com"
    attribution = "Jobs via Jobicy"

    def fetch(self):
        data = get_json("https://jobicy.com/api/v2/remote-jobs", params={"count": 50})
        out = []
        for j in data.get("jobs", []):
            title = j.get("jobTitle", "")
            types = j.get("jobType") if isinstance(j.get("jobType"), list) else [j.get("jobType", "")]
            out.append(self.row(j.get("id"), title, j.get("companyName"), j.get("jobGeo") or "Anywhere", True,
                                classify_kind(title, types, j.get("jobIndustry") if isinstance(j.get("jobIndustry"), list) else []),
                                j.get("url"), salary_text(j.get("salaryMin") or j.get("annualSalaryMin"), j.get("salaryMax") or j.get("annualSalaryMax"), j.get("salaryCurrency") or "", ""),
                                j.get("companyLogo", ""), strip_html(j.get("jobDescription") or j.get("jobExcerpt")),
                                (j.get("jobIndustry") if isinstance(j.get("jobIndustry"), list) else []), parse_dt(j.get("pubDate"))))
        return out


class TheMuse(Source):
    name, label = "themuse", "The Muse"
    homepage = "https://www.themuse.com"
    attribution = "Jobs via The Muse"

    def fetch(self):
        out = []
        for level, pages in (("Internship", (1, 2)), ("Entry Level", (1,))):
            for page in pages:
                data = get_json("https://www.themuse.com/api/public/jobs", params={"page": page, "level": level})
                for j in data.get("results", []):
                    title = j.get("name", "")
                    locs = [l.get("name", "") for l in j.get("locations", [])]
                    levels = [l.get("name", "") for l in j.get("levels", [])]
                    kind = "internship" if any("intern" in l.lower() for l in levels) else classify_kind(title)
                    out.append(self.row(j.get("id"), title, (j.get("company") or {}).get("name"), ", ".join(locs[:2]),
                                        any("remote" in l.lower() or "flexible" in l.lower() for l in locs), kind,
                                        (j.get("refs") or {}).get("landing_page"), "", "", strip_html(j.get("contents")),
                                        [c.get("name", "") for c in j.get("categories", [])], parse_dt(j.get("publication_date"))))
        return out


class Adzuna(Source):
    name, label = "adzuna", "Adzuna"
    homepage = "https://www.adzuna.com"
    attribution = "Jobs by Adzuna"
    needs_key = True

    def available(self):
        c = current_app.config
        return bool(c.get("ADZUNA_APP_ID") and c.get("ADZUNA_APP_KEY"))

    def fetch(self, what: str = "software developer", where: str = "", page: int = 1, per_page: int = 30):
        c = current_app.config
        params = {"app_id": c["ADZUNA_APP_ID"], "app_key": c["ADZUNA_APP_KEY"], "results_per_page": per_page, "what": what,
                  "content-type": "application/json"}
        if where:
            params["where"] = where
        data = get_json(f"https://api.adzuna.com/v1/api/jobs/{c['ADZUNA_COUNTRY']}/search/{page}", params=params)
        out = []
        for j in data.get("results", []):
            title = j.get("title", "")
            out.append(self.row(j.get("id"), strip_html(title), (j.get("company") or {}).get("display_name"),
                                (j.get("location") or {}).get("display_name"), "remote" in (title + " " + j.get("description", "")).lower()[:400],
                                classify_kind(title, [j.get("contract_type", ""), j.get("contract_time", "")]), j.get("redirect_url"),
                                salary_text(j.get("salary_min"), j.get("salary_max"), c["ADZUNA_COUNTRY"].upper()), "",
                                strip_html(j.get("description")), [(j.get("category") or {}).get("label", "")], parse_dt(j.get("created"))))
        return out


FEED_SOURCES = [Remotive(), Arbeitnow(), RemoteOK(), Jobicy(), TheMuse()]
ADZUNA = Adzuna()
BY_NAME = {s.name: s for s in FEED_SOURCES + [ADZUNA]}
