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

SERPER_ENDPOINT = "https://google.serper.dev/jobs"
REQUEST_TIMEOUT = 30  # seconds


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


def normalise_job(raw: dict) -> dict:
    """
    Convert a Serper.dev Google Jobs result into our raw_jobs schema.
    Missing fields are set to None (we do NOT drop the row for nulls).
    """
    # detected_extensions is Serper's bag of structured metadata:
    # {"posted_at": "2 days ago", "schedule_type": "Full-time", "salary": "...",
    #  "work_from_home": true, ...}
    ext = raw.get("detected_extensions") or {}

    # Apply link: prefer apply_link; fall back to first related_link
    apply_url = _clean(raw.get("apply_link"))
    if not apply_url:
        related = raw.get("related_links") or []
        if isinstance(related, list) and related:
            first = related[0]
            if isinstance(first, dict):
                apply_url = _clean(first.get("link"))

    # "via" is Serper's source-platform field, e.g. "LinkedIn", "Indeed",
    # "Glassdoor", "via Jobberman". Strip the leading "via " if present.
    source = _clean(raw.get("via"))
    if source and source.lower().startswith("via "):
        source = source[4:].strip()
    if not source:
        source = "google_jobs"  # safe fallback so NOT NULL constraint is satisfied

    return {
        "job_title": _clean(raw.get("title")),
        "company": _clean(raw.get("company_name")),
        "location": _clean(raw.get("location")),
        "date_posted": _clean(ext.get("posted_at")),
        "description": _clean(raw.get("description")),
        "apply_url": apply_url,
        "source": source,
        "detected_extensions": ext if ext else None,
    }


# ============================================================
# SERPER API CALLS
# ============================================================

def fetch_serper_page(query: str, page: int) -> list[dict]:
    """
    POST to Serper.dev /jobs for one query and one page of results.
    Returns the raw jobs list. Raises requests.HTTPError on non-2xx.
    """
    payload = {
        "q": query,
        "gl": "ng",   # Nigeria
        "hl": "en",
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
    return data.get("jobs", []) or []


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
