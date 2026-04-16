"""
Indeed scraper via python-jobspy.

Runs 30 targeted queries for oil & gas roles in Nigeria,
3-second delay between queries, returns a flat list of job dicts.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import pandas as pd
from jobspy import scrape_jobs

logger = logging.getLogger(__name__)

SOURCE = "indeed"

QUERIES = [
    "supply chain procurement oil and gas Nigeria",
    "logistics materials management upstream Nigeria",
    "vendor management contracts oil and gas Nigeria",
    "drilling reservoir production engineer Nigeria",
    "facilities subsurface engineer upstream Nigeria",
    "geoscience geophysics petroleum engineer Nigeria",
    "instrumentation automation control oil and gas Nigeria",
    "oil and gas finance commercial analyst Nigeria",
    "petroleum economics project finance upstream Nigeria",
    "trading commodity analyst energy Nigeria",
    "project manager engineer oil and gas Nigeria",
    "contracts administrator legal counsel upstream Nigeria",
    "HSE QHSE safety officer oil and gas Nigeria",
    "community relations sustainability environment oil and gas Nigeria",
    "HR human resources talent management oil and gas Nigeria",
    "learning development organisational development upstream Nigeria",
    "IT digital SAP data analytics oil and gas Nigeria",
    "technology systems engineer upstream Nigeria",
    "marine offshore operations engineer Nigeria",
    "oil and gas graduate trainee programme Nigeria",
    "upstream internship entry level petroleum Nigeria",
    "graduate engineer analyst oil and gas Nigeria",
    "NNPC TotalEnergies Shell Chevron ExxonMobil Dangote Nigeria careers",
    "Seplat Oando Sahara Heirs Energies Aradel Nigeria jobs",
    "Eroton Neconde Aiteo Renaissance Midwestern Nigeria oil gas jobs",
    "NPDC Belemaoil Platform Petroleum Famfa Pan Ocean Nigeria careers",
    "SLB Halliburton Baker Hughes Saipem Weatherford Nigeria jobs",
    "Bell Oil Gas Dakotelin Sinopec NAOC NLNG Nigeria careers",
    "oil and gas jobs Port Harcourt Rivers State Nigeria",
    "oil and gas jobs Lagos Victoria Island Nigeria",
]

DELAY_SECONDS = 3
RESULTS_PER_QUERY = 25
QUERY_TIMEOUT = 90  # seconds per query before we give up and move on


def _fetch(query: str) -> pd.DataFrame:
    """Thin wrapper so we can run scrape_jobs in a thread with a timeout."""
    return scrape_jobs(
        site_name=["indeed"],
        search_term=query,
        location="Nigeria",
        results_wanted=RESULTS_PER_QUERY,
        country_indeed="Nigeria",
        verbose=0,
    )


def _scrape_query(query: str) -> list[dict]:
    """Run a single JobSpy query and return a list of normalised job dicts."""
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_fetch, query)
            df: pd.DataFrame = future.result(timeout=QUERY_TIMEOUT)
    except FutureTimeoutError:
        logger.warning("indeed query timed out after %ds [%s]", QUERY_TIMEOUT, query)
        return []
    except Exception as exc:
        logger.error("indeed query failed [%s]: %s", query, exc)
        return []

    if df is None or df.empty:
        logger.info("indeed: 0 results for query: %s", query)
        return []

    jobs = []
    for _, row in df.iterrows():
        jobs.append({
            "title": row.get("title"),
            "company": row.get("company"),
            "location": row.get("location"),
            "date_posted": row.get("date_posted"),
            "description": row.get("description"),
            "job_url": row.get("job_url"),
            "source_query": query,
        })
    return jobs


def run() -> list[dict]:
    """
    Execute all 30 queries sequentially with a delay between each.
    Returns a deduplicated list of job dicts (deduped by job_url within this run).
    """
    all_jobs: list[dict] = []
    seen_urls: set[str] = set()
    failed_queries: list[str] = []

    logger.info("indeed_scraper: starting %d queries", len(QUERIES))

    for i, query in enumerate(QUERIES, 1):
        logger.info("indeed [%d/%d]: %s", i, len(QUERIES), query)
        results = _scrape_query(query)

        new_count = 0
        for job in results:
            url = job.get("job_url") or ""
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            all_jobs.append(job)
            new_count += 1

        if not results:
            failed_queries.append(query)

        logger.info(
            "indeed [%d/%d]: %d new (running total: %d)",
            i, len(QUERIES), new_count, len(all_jobs),
        )

        if i < len(QUERIES):
            time.sleep(DELAY_SECONDS)

    logger.info(
        "indeed_scraper: finished — %d jobs collected, %d failed queries",
        len(all_jobs), len(failed_queries),
    )
    if failed_queries:
        logger.warning("indeed: failed queries: %s", failed_queries)

    return all_jobs, failed_queries
