#!/usr/bin/env python3
"""
DracoHub Careers — Serper.dev Google Jobs Scraper

Runs all configured search queries through Serper.dev's Google Jobs API,
normalises results, and inserts them into the Supabase raw_jobs table
using existing deduplication and quality-scoring logic.

Usage:
    python scraper.py
"""

import logging
import time
from typing import Any

import requests

from src.config import (
    SERPER_API_KEY,
    SEARCH_QUERIES,
    REQUEST_DELAY_SECONDS,
    MAX_PAGES_PER_QUERY,
)
from src.database.client import get_client, insert_jobs
from src.utils.daily_log import ScrapeLog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dracohub.scraper")

SERPER_ENDPOINT = "https://google.serper.dev/search"
REQUEST_TIMEOUT = 30  # seconds

# Domains we recognise as job platforms — used to infer source from URL
_DOMAIN_TO_SOURCE = {
    "linkedin.com":     "linkedin",
    "indeed.com":       "indeed",
    "jobberman.com":    "jobberman",
    "myjobmag.com":     "myjobmag",
    "glassdoor.com":    "glassdoor",
    "hotnigerianjobs.com": "hotnigerianjobs",
    "ngcareers.com":    "ngcareers",
    "careers.nnpcgroup.com": "nnpc",
    "shell.com":        "shell",
    "totalenergies.com":"totalenergies",
    "careers.chevron.com": "chevron",
    "jobs.exxonmobil.com": "exxonmobil",
    "seplatenergy.com": "seplat",
    "oandoplc.com":     "oando",
    "sahara-group.com": "sahara",
    "myworkdayjobs.com":"workday",
    "ziprecruiter.com": "ziprecruiter",
    "jobgurus.com.ng":  "jobgurus",
    "naijahotjobs.com": "naijahotjobs",
}


# ============================================================
# HELPERS
# ============================================================

def _clean(value: Any) -> Any:
    """Trim strings and return None if empty/missing."""
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        return v if v else None
    return value


def _source_from_url(url: str) -> str:
    """Infer source platform from a URL domain."""
    if not url:
        return "google_jobs"
    url_lower = url.lower()
    for domain, source in _DOMAIN_TO_SOURCE.items():
        if domain in url_lower:
            return source
    return "google_jobs"


def _clean_title(raw_title: str) -> str:
    """
    Google organic titles for job results often look like:
      "Drilling Engineer at Shell Nigeria | LinkedIn"
      "HSE Manager - Lagos - Jobberman"
      "Production Engineer - NNPC | Indeed.com"
    Strip the trailing platform badge (everything after the last | or last -Platform).
    """
    if not raw_title:
        return raw_title
    # Strip " | Platform" suffix
    if " | " in raw_title:
        raw_title = raw_title.rsplit(" | ", 1)[0].strip()
    # Strip trailing " - Platform" only if the part after the dash looks like
    # a platform name (no spaces, or known platform name)
    if " - " in raw_title:
        parts = raw_title.rsplit(" - ", 1)
        suffix = parts[1].strip()
        # Remove if suffix is a single word (platform name) with no spaces
        # or is a known platform — but keep if it's a location like "Port Harcourt"
        known_platforms = {
            "linkedin", "indeed", "jobberman", "myjobmag", "glassdoor",
            "ziprecruiter", "monster", "careerjet",
        }
        if suffix.lower() in known_platforms or (len(suffix.split()) == 1 and len(suffix) < 20):
            raw_title = parts[0].strip()
    return raw_title


def normalise_job(raw: dict) -> dict:
    """
    Convert a Serper.dev /search organic result into our raw_jobs schema.
    Serper organic result fields: title, link, snippet, sitelinks, position.
    Missing fields are set to None — rows are never dropped for missing fields.
    """
    apply_url = _clean(raw.get("link"))
    source = _source_from_url(apply_url or "")
    job_title = _clean_title(_clean(raw.get("title")) or "")

    return {
        "job_title": job_title if job_title else None,
        "company":   None,           # not available from organic results
        "location":  None,           # not available from organic results
        "date_posted": _clean(raw.get("date")),   # Serper sometimes includes date
        "description": _clean(raw.get("snippet")),
        "apply_url": apply_url,
        "source":    source,
        "detected_extensions": None,
    }


# ============================================================
# SERPER API CALLS
# ============================================================

def fetch_serper_page(query: str, page: int) -> list[dict]:
    """
    POST to Serper.dev /search for one query and page.
    Returns the organic results list. Raises requests.HTTPError on non-2xx.
    """
    payload = {
        "q": query,
        "gl": "ng",   # Nigeria
        "hl": "en",
        "num": 10,    # results per page
        "page": page,
    }
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    response = requests.post(
        SERPER_ENDPOINT,
        headers=headers,
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("organic", []) or []


def scrape_query(query: str) -> list[dict]:
    """
    Pull up to MAX_PAGES_PER_QUERY pages from Serper for one query.
    Returns a normalised list of jobs.

    Pagination stops early when an empty page is returned. HTTP errors on
    the first page are raised so the caller can log them; errors on later
    pages just truncate pagination (we keep whatever we got).
    """
    all_jobs: list[dict] = []
    for page in range(1, MAX_PAGES_PER_QUERY + 1):
        try:
            raw_jobs = fetch_serper_page(query, page)
        except requests.HTTPError as e:
            if page == 1:
                raise
            logger.warning(f"  page {page} HTTP error ({e}) — stopping pagination")
            break

        if not raw_jobs:
            logger.info(f"  page {page}: empty — stopping pagination")
            break

        logger.info(f"  page {page}: {len(raw_jobs)} raw results")
        all_jobs.extend(normalise_job(j) for j in raw_jobs)

    return all_jobs


# ============================================================
# PIPELINE
# ============================================================

def run_pipeline():
    """Execute the full Serper scrape-and-store pipeline."""
    if not SERPER_API_KEY:
        raise RuntimeError(
            "SERPER_API_KEY is not set. Check .env locally or the GitHub secret."
        )

    logger.info("=" * 60)
    logger.info("DracoHub Careers — Serper.dev Google Jobs scrape")
    logger.info(
        f"{len(SEARCH_QUERIES)} queries × up to {MAX_PAGES_PER_QUERY} pages"
    )
    logger.info("=" * 60)

    db = get_client()
    scrape_log = ScrapeLog()

    for i, query in enumerate(SEARCH_QUERIES, start=1):
        logger.info(f"\n--- [{i}/{len(SEARCH_QUERIES)}] {query}")

        scraped = 0
        stats = {"inserted": 0, "updated": 0, "skipped": 0}
        error = None

        try:
            jobs = scrape_query(query)
            scraped = len(jobs)
            logger.info(f"  total pulled: {scraped}")

            if jobs:
                stats = insert_jobs(db, jobs)
                logger.info(
                    f"  inserted={stats['inserted']}, "
                    f"updated={stats['updated']}, "
                    f"skipped={stats['skipped']}"
                )
        except Exception as e:
            error = str(e)
            logger.error(f"  FAILED: {e}")
            # Continue to next query — never stop the whole pipeline

        scrape_log.add_source(
            name=query,
            scraped=scraped,
            inserted=stats["inserted"],
            updated=stats["updated"],
            skipped=stats["skipped"],
            error=error,
        )

        # Rate-limit stagger between queries (skip after the last one)
        if i < len(SEARCH_QUERIES):
            time.sleep(REQUEST_DELAY_SECONDS)

    # --- Write daily log ---
    summary = scrape_log.write()
    failed_count = sum(1 for s in scrape_log.sources if s.get("error"))

    logger.info("=" * 60)
    logger.info(
        f"DONE — pulled: {summary['total_scraped']}, "
        f"inserted: {summary['total_inserted']}, "
        f"duplicates updated: {summary['total_updated']}, "
        f"queries failed: {failed_count}"
    )
    logger.info(f"Log saved to logs/{summary['started_at'][:10]}.log")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_pipeline()
