"""
DracoHub Careers — Main Orchestrator

Runs all scrapers with staggered requests, deduplicates across sources,
scores data quality, and inserts into Supabase. Writes a daily log file.
"""

import logging
import time
from src.database.client import get_client, insert_jobs
from src.scrapers import (
    linkedin, indeed, jobberman, myjobmag,
    hotnigeranjobs, ngcareers, company_pages,
)
from src.utils.daily_log import ScrapeLog
from src.config import REQUEST_DELAY_SECONDS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dracohub")

# Registry of all scrapers — order matters for staggering.
# LinkedIn and Indeed first (dedicated actors, most reliable),
# then web-scraper-based sources, then company pages last.
SCRAPERS = [
    ("LinkedIn", linkedin.scrape),
    ("Indeed", indeed.scrape),
    ("Jobberman", jobberman.scrape),
    ("MyJobMag", myjobmag.scrape),
    ("HotNigerianJobs", hotnigeranjobs.scrape),
    ("NgCareers", ngcareers.scrape),
    ("Company Pages", company_pages.scrape),
]


def run_pipeline():
    """Execute the full scrape-and-store pipeline."""
    logger.info("=" * 60)
    logger.info("DracoHub Careers — daily scrape starting")
    logger.info("=" * 60)

    db = get_client()
    scrape_log = ScrapeLog()

    for i, (name, scrape_fn) in enumerate(SCRAPERS):
        logger.info(f"\n--- [{i+1}/{len(SCRAPERS)}] Running {name} scraper ---")

        scraped = 0
        stats = {"inserted": 0, "updated": 0, "skipped": 0}
        error = None

        try:
            jobs = scrape_fn()
            scraped = len(jobs)
            logger.info(f"{name}: scraped {scraped} raw listings")

            if jobs:
                stats = insert_jobs(db, jobs)
                logger.info(
                    f"{name}: inserted={stats['inserted']}, "
                    f"updated={stats['updated']}, skipped={stats['skipped']}"
                )
        except Exception as e:
            error = str(e)
            logger.error(f"{name} pipeline FAILED: {e}")

        scrape_log.add_source(
            name=name,
            scraped=scraped,
            inserted=stats["inserted"],
            updated=stats["updated"],
            skipped=stats["skipped"],
            error=error,
        )

        # Stagger between sources
        if i < len(SCRAPERS) - 1:
            logger.info(f"Waiting {REQUEST_DELAY_SECONDS}s before next source...")
            time.sleep(REQUEST_DELAY_SECONDS)

    # Write daily log
    summary = scrape_log.write()
    logger.info("=" * 60)
    logger.info(
        f"DONE — Scraped: {summary['total_scraped']}, "
        f"Inserted: {summary['total_inserted']}, "
        f"Updated: {summary['total_updated']}"
    )
    logger.info(f"Log saved to {summary['started_at'][:10]}.log")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_pipeline()
