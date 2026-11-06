"""Research paper search: arXiv + OpenAlex (free, no key). Results are cached in memory."""
from __future__ import annotations

import threading
import time
import xml.etree.ElementTree as ET

import requests
from flask import current_app

from .base import strip_html, user_agent

_CACHE: dict = {}
_ARXIV_LOCK = threading.Lock()
_ARXIV_LAST = [0.0]
TTL = 3600


def _cached(key):
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    return None


def arxiv_search(q: str, limit: int = 10, start: int = 0) -> list[dict]:
    key = ("arxiv", q, limit, start)
    if (c := _cached(key)) is not None:
        return c
    with _ARXIV_LOCK:  # arXiv asks for at most one request every ~3 seconds
        wait = 3.1 - (time.time() - _ARXIV_LAST[0])
        if wait > 0:
            time.sleep(wait)
        r = requests.get("https://export.arxiv.org/api/query", headers={"User-Agent": user_agent()}, timeout=15,
                         params={"search_query": f"all:{q}", "start": start, "max_results": limit, "sortBy": "relevance"})
        _ARXIV_LAST[0] = time.time()
    r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(r.content)
    out = []
    for e in root.findall("a:entry", ns):
        absu = (e.findtext("a:id", "", ns) or "").strip()
        pdf = ""
        for l in e.findall("a:link", ns):
            if l.get("title") == "pdf":
                pdf = l.get("href", "")
        out.append({
            "source": "arxiv", "title": " ".join((e.findtext("a:title", "", ns) or "").split()),
            "authors": [a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)][:6],
            "year": int((e.findtext("a:published", "0000", ns) or "0000")[:4]), "abstract": " ".join((e.findtext("a:summary", "", ns) or "").split())[:700],
            "url": absu, "pdf_url": pdf, "venue": "arXiv", "citations": None,
        })
    _CACHE[key] = (time.time(), out)
    return out


def _inverted_to_text(inv: dict | None) -> str:
    if not inv:
        return ""
    pos = {}
    for w, idxs in inv.items():
        for i in idxs:
            pos[i] = w
    return " ".join(pos[i] for i in sorted(pos))[:700]


def openalex_search(q: str, limit: int = 10, page: int = 1, since_year: int | None = None) -> list[dict]:
    key = ("openalex", q, limit, page, since_year)
    if (c := _cached(key)) is not None:
        return c
    params = {"search": q, "per-page": limit, "page": page, "sort": "relevance_score:desc",
              "select": "id,title,publication_year,authorships,abstract_inverted_index,cited_by_count,primary_location,open_access,doi"}
    if since_year:
        params["filter"] = f"from_publication_date:{since_year}-01-01"
    mail = current_app.config.get("CONTACT_EMAIL")
    if mail:
        params["mailto"] = mail
    r = requests.get("https://api.openalex.org/works", params=params, headers={"User-Agent": user_agent()}, timeout=15)
    r.raise_for_status()
    out = []
    for w in r.json().get("results", []):
        loc = w.get("primary_location") or {}
        src = (loc.get("source") or {}).get("display_name") or ""
        out.append({
            "source": "openalex", "title": strip_html(w.get("title") or "", 300),
            "authors": [((a.get("author") or {}).get("display_name") or "") for a in (w.get("authorships") or [])][:6],
            "year": w.get("publication_year"), "abstract": _inverted_to_text(w.get("abstract_inverted_index")),
            "url": w.get("doi") or loc.get("landing_page_url") or w.get("id"), "pdf_url": (w.get("open_access") or {}).get("oa_url") or loc.get("pdf_url") or "",
            "venue": src, "citations": w.get("cited_by_count"),
        })
    _CACHE[key] = (time.time(), out)
    return out


def search(q: str, source: str = "openalex", limit: int = 10, page: int = 1) -> list[dict]:
    limit = max(1, min(25, limit))
    if source == "arxiv":
        return arxiv_search(q, limit, (page - 1) * limit)
    return openalex_search(q, limit, page)
