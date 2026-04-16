"""
DracoHub Careers — Serper.dev Google Jobs scraper.

Hits Serper's /search endpoint and parses the structured `jobs` panel
(Google's own job cards — distinct from organic search links). Each card
contains company name, location, description, and detected_extensions
(schedule type, posted date, etc.), making it the highest-quality source
in the pipeline.

Free tier: 2,500 credits/month. At 30 queries × 2 pages = 60 credits/run,
30-day daily schedule uses ~1,800 credits — safely within the free tier.

Returns: (jobs: list[dict], failed_queries: list[str])
"""
import logging
import time

import requests

from src.config import SERPER_API_KEY, SEARCH_QUERIES, REQUEST_DELAY_SECONDS

logger = logging.getLogger(__name__)

SERPER_ENDPOINT = "https://google.serper.dev/search"
REQUEST_TIMEOUT = 20   # seconds per HTTP call
MAX_PAGES = 2          # pages per query (10 jobs/page → up to 20 per query)

# Map "via <Platform>" text → source label
_VIA_TO_SOURCE = {
    "linkedin":    "linkedin",
    "indeed":      "indeed",
    "jobberman":   "jobberman",
    "myjobmag":    "myjobmag",
    "glassdoor":   "glassdoor",
    "ziprecruiter":"ziprecruiter",
    "ngcareers":   "ngcareers",
    "hotnigerianjobs": "hotnigerianjobs",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _source_from_via(via: str | None) -> str:
    """Infer source from Serper's 'via' string (e.g. 'via LinkedIn')."""
    if not via:
        return "google_jobs"
    via_lower = via.lower()
    for keyword, source in _VIA_TO_SOURCE.items():
        if keyword in via_lower:
            return source
    return "google_jobs"


def _clean(val) -> str | None:
    """Trim strings; return None if empty or missing."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _normalise(raw: dict) -> dict | None:
    """
    Convert one Serper jobs-panel entry into our raw_jobs schema.
    Returns None if no title (required NOT NULL).

    Serper `jobs` entry keys:
        title, companyName, location, via, description,
        jobHighlights, detectedExtensions, link, thumbnail
    """
    title = _clean(raw.get("title"))
    if not title:
        return None

    detected = raw.get("detectedExtensions") or {}

    return {
        "job_title":   title,
        "company":     _clean(raw.get("companyName")),
        "location":    _clean(raw.get("location")),
        "date_posted": _clean(detected.get("postedAt")),
        "description": _clean(raw.get("description")),
        "apply_url":   _clean(raw.get("link")),
        "source":      _source_from_via(raw.get("via")),
        "detected_extensions": detected if detected else None,
    }


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def _fetch_page(query: str, page: int) -> list[dict]:
    """
    POST one page to Serper. Returns the `jobs` list (may be empty).
    Raises requests.HTTPError on non-2xx.
    """
    resp = requests.post(
        SERPER_ENDPOINT,
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "gl": "ng", "hl": "en", "num": 10, "page": page},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("jobs") or []


def _scrape_query(query: str) -> list[dict]:
    """
    Fetch up to MAX_PAGES pages of Google Jobs results for one query.
    Stops early on empty page. HTTP errors on page 1 are re-raised;
    errors on later pages truncate pagination gracefully.
    """
    all_jobs: list[dict] = []

    for page in range(1, MAX_PAGES + 1):
        try:
            raw_jobs = _fetch_page(query, page)
        except requests.HTTPError as exc:
            if page == 1:
                raise
            logger.warning("serper page %d HTTP error (%s) — stopping", page, exc)
            break

        if not raw_jobs:
            logger.debug("serper page %d empty — stopping", page)
            break

        logger.debug("serper page %d: %d jobs", page, len(raw_jobs))
        for raw in raw_jobs:
            job = _normalise(raw)
            if job:
                all_jobs.append(job)

    return all_jobs


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run() -> tuple[list[dict], list[str]]:
    """
    Run all configured queries and return (all_jobs, failed_queries).
    Never raises — errors per query are caught and logged.
    """
    if not SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY is not set — check .env or GitHub secret")

    all_jobs: list[dict] = []
    seen_urls: set[str] = set()
    failed: list[str] = []

    logger.info("serper_scraper: starting %d queries", len(SEARCH_QUERIES))

    for i, query in enumerate(SEARCH_QUERIES, 1):
        logger.info("serper [%d/%d]: %s", i, len(SEARCH_QUERIES), query)

        try:
            results = _scrape_query(query)
        except Exception as exc:
            logger.error("serper [%d/%d] failed: %s", i, len(SEARCH_QUERIES), exc)
            failed.append(query)
            if i < len(SEARCH_QUERIES):
                time.sleep(REQUEST_DELAY_SECONDS)
            continue

        new_count = 0
        for job in results:
            url = job.get("apply_url") or ""
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            all_jobs.append(job)
            new_count += 1

        logger.info(
            "serper [%d/%d]: %d new jobs (total: %d)",
            i, len(SEARCH_QUERIES), new_count, len(all_jobs),
        )

        if i < len(SEARCH_QUERIES):
            time.sleep(REQUEST_DELAY_SECONDS)

    logger.info(
        "serper_scraper: done — %d jobs, %d failed queries",
        len(all_jobs), len(failed),
    )
    return all_jobs, failed
