#!/usr/bin/env python3
"""
Batch-tag all existing raw_jobs rows that have no tags yet.

Usage:
    python scripts/batch_tag.py            # tag all untagged rows
    python scripts/batch_tag.py --all      # re-tag every row (overwrite)
    python scripts/batch_tag.py --dry-run  # preview only, no writes

Safe to run multiple times — skips already-tagged rows unless --all.
"""

import argparse
import logging
import os
import sys

import requests
from dotenv import load_dotenv

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()
from src.tagger import tag_job  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("batch_tag")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PAGE_SIZE = 200
PATCH_BATCH = 50   # rows per PATCH call


def get_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def fetch_all_jobs(retag_all: bool) -> list[dict]:
    """Fetch all jobs (or only untagged ones) from Supabase."""
    jobs = []
    offset = 0
    while True:
        params = {
            "select": "id,job_title,company,location,description",
            "order": "id.asc",
            "offset": offset,
            "limit": PAGE_SIZE,
        }
        if not retag_all:
            params["tags"] = "is.null"

        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/raw_jobs",
            headers=get_headers(),
            params=params,
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error("Fetch failed: %s %s", resp.status_code, resp.text[:200])
            break

        page = resp.json()
        jobs.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    return jobs


def patch_tags(updates: list[dict], dry_run: bool) -> int:
    """
    PATCH tags for a batch of rows. Each update is {"id": int, "tags": dict}.
    Returns the number of successfully patched rows.
    """
    patched = 0
    for item in updates:
        if dry_run:
            patched += 1
            continue
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/raw_jobs",
            headers=get_headers(),
            params={"id": f"eq.{item['id']}"},
            json={"tags": item["tags"]},
            timeout=15,
        )
        if resp.status_code in (200, 201, 204):
            patched += 1
        else:
            logger.warning("Patch failed for id=%s: %s", item["id"], resp.text[:100])
    return patched


def main():
    parser = argparse.ArgumentParser(description="Batch-tag raw_jobs")
    parser.add_argument("--all", action="store_true", help="Re-tag all rows, not just untagged")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
    args = parser.parse_args()

    logger.info("=" * 55)
    logger.info("DracoHub — Batch Job Tagger")
    if args.dry_run:
        logger.info("DRY RUN — no writes")
    if args.all:
        logger.info("Mode: re-tag ALL rows")
    else:
        logger.info("Mode: tag untagged rows only")
    logger.info("=" * 55)

    jobs = fetch_all_jobs(retag_all=args.all)
    logger.info("Fetched %d jobs to tag", len(jobs))

    if not jobs:
        logger.info("Nothing to do.")
        return

    # Tag all rows
    updates = []
    category_counts: dict[str, int] = {}
    for job in jobs:
        tags = tag_job(job)
        updates.append({"id": job["id"], "tags": tags})
        cat = tags.get("category", "Other")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Preview
    logger.info("\nTagging preview:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        logger.info("  %-25s %d", cat, count)

    # Write in batches
    total_patched = 0
    for i in range(0, len(updates), PATCH_BATCH):
        batch = updates[i: i + PATCH_BATCH]
        patched = patch_tags(batch, dry_run=args.dry_run)
        total_patched += patched
        logger.info(
            "Patched %d/%d rows...",
            min(i + PATCH_BATCH, len(updates)), len(updates),
        )

    logger.info("=" * 55)
    logger.info(
        "Done — %d rows %s",
        total_patched,
        "would be tagged (dry-run)" if args.dry_run else "tagged",
    )
    logger.info("=" * 55)


if __name__ == "__main__":
    main()
