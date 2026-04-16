#!/usr/bin/env python3
"""
DracoHub Careers — unified pipeline orchestrator.

Daily run  (--daily):   Indeed + Jobberman + MyJobMag
Weekly run (--weekly):  Company career pages only

Usage:
    python -m src.main --daily
    python -m src.main --weekly
    python -m src.main --daily --dry-run    # scrape only, no DB writes
"""

import argparse
import logging

from src.database.client import get_client, insert_jobs  # noqa: F401 (insert_jobs used in _insert_and_log)
from src.utils.daily_log import ScrapeLog
from src.scrapers import indeed_scraper, jobberman_scraper, myjobmag_scraper, company_pages_scraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dracohub.main")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_scraper(label: str, fn) -> tuple[list[dict], list[str], str | None]:
    """Call a scraper fn(), return (jobs, failed_queries, top_error_or_None)."""
    try:
        jobs, failed = fn()
        return jobs, failed, None
    except Exception as exc:
        logger.exception("%s: top-level error", label)
        return [], [], str(exc)


def _insert_and_log(
    db,
    log: ScrapeLog,
    label: str,
    jobs: list[dict],
    failed: list[str],
    top_error: str | None,
    source: str | None = None,
    dry_run: bool = False,
) -> None:
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    error_msg = top_error

    if jobs and not dry_run:
        try:
            stats = insert_jobs(db, jobs, source=source)
        except Exception as exc:
            logger.exception("%s: insert error", label)
            error_msg = str(exc)
    elif dry_run and jobs:
        logger.info("%s: dry-run — %d jobs not written to DB", label, len(jobs))

    error_parts = [p for p in [error_msg, f"{len(failed)} failed queries" if failed else None] if p]
    log.add_source(
        name=label,
        scraped=len(jobs),
        inserted=stats["inserted"],
        updated=stats["updated"],
        skipped=stats["skipped"],
        error="; ".join(error_parts) if error_parts else None,
    )
    logger.info(
        "%s: scraped=%d inserted=%d updated=%d skipped=%d",
        label, len(jobs), stats["inserted"], stats["updated"], stats["skipped"],
    )


# ---------------------------------------------------------------------------
# Daily pipeline
# ---------------------------------------------------------------------------

def run_daily(dry_run: bool = False) -> None:
    logger.info("=" * 60)
    logger.info("DracoHub Careers — DAILY pipeline")
    logger.info("Sources: Indeed, Jobberman, MyJobMag")
    if dry_run:
        logger.info("DRY RUN — no database writes")
    logger.info("=" * 60)

    db = None if dry_run else get_client()
    log = ScrapeLog()

    # 1. Indeed via python-jobspy
    logger.info("\n[1/3] Indeed (python-jobspy)")
    jobs, failed, error = _run_scraper("indeed", indeed_scraper.run)
    _insert_and_log(db, log, "indeed", jobs, failed, error, source="indeed", dry_run=dry_run)

    # 2. Jobberman
    logger.info("\n[2/3] Jobberman")
    jobs, failed, error = _run_scraper("jobberman", jobberman_scraper.run)
    _insert_and_log(db, log, "jobberman", jobs, failed, error, source="jobberman", dry_run=dry_run)

    # 3. MyJobMag
    logger.info("\n[3/3] MyJobMag")
    jobs, failed, error = _run_scraper("myjobmag", myjobmag_scraper.run)
    _insert_and_log(db, log, "myjobmag", jobs, failed, error, source="myjobmag", dry_run=dry_run)

    summary = log.write()
    logger.info("=" * 60)
    logger.info(
        "DAILY DONE — scraped=%d inserted=%d updated=%d",
        summary["total_scraped"], summary["total_inserted"], summary["total_updated"],
    )
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Weekly pipeline
# ---------------------------------------------------------------------------

def run_weekly(dry_run: bool = False) -> None:
    logger.info("=" * 60)
    logger.info("DracoHub Careers — WEEKLY pipeline")
    logger.info("Source: Company career pages")
    if dry_run:
        logger.info("DRY RUN — no database writes")
    logger.info("=" * 60)

    db = None if dry_run else get_client()
    log = ScrapeLog()

    jobs, failed, error = _run_scraper("company_pages", company_pages_scraper.run)
    _insert_and_log(db, log, "company_pages", jobs, failed, error, source="company_pages", dry_run=dry_run)

    summary = log.write()
    logger.info("=" * 60)
    logger.info(
        "WEEKLY DONE — scraped=%d inserted=%d updated=%d",
        summary["total_scraped"], summary["total_inserted"], summary["total_updated"],
    )
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="DracoHub job scraping pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--daily", action="store_true", help="Run daily pipeline")
    group.add_argument("--weekly", action="store_true", help="Run weekly pipeline (company pages)")
    parser.add_argument("--dry-run", action="store_true", help="Scrape only — no DB writes")
    args = parser.parse_args()

    if args.daily:
        run_daily(dry_run=args.dry_run)
    else:
        run_weekly(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
