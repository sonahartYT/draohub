"""
Supabase database client.
Handles connection, deduplication (cross-source), quality scoring, and inserts.
"""

import logging
from supabase import create_client, Client
from src.config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)


def get_client() -> Client:
    """Return a configured Supabase client."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def compute_quality_score(job: dict) -> int:
    """
    Rate a listing from 1–5 based on how many key fields are populated.
    5 = all fields present, 1 = only title.
    """
    fields = ["job_title", "company", "location", "date_posted", "description", "apply_url"]
    filled = sum(1 for f in fields if job.get(f))
    if filled >= 6:
        return 5
    elif filled >= 5:
        return 4
    elif filled >= 4:
        return 3
    elif filled >= 3:
        return 2
    return 1


def _dedup_key(job: dict) -> tuple:
    """Dedup key: normalised (title, company, location)."""
    return (
        (job.get("job_title") or "").strip().lower(),
        (job.get("company") or "").strip().lower(),
        (job.get("location") or "").strip().lower(),
    )


def get_existing_jobs(client: Client) -> dict[tuple, dict]:
    """
    Fetch existing (job_title, company, location) -> {id, sources} map.
    Used for dedup and multi-source tracking.
    """
    response = (
        client.table("raw_jobs")
        .select("id, job_title, company, location, sources")
        .execute()
    )
    result = {}
    for row in response.data:
        key = (
            (row.get("job_title") or "").strip().lower(),
            (row.get("company") or "").strip().lower(),
            (row.get("location") or "").strip().lower(),
        )
        result[key] = {"id": row["id"], "sources": row.get("sources") or []}
    return result


def insert_jobs(client: Client, jobs: list[dict]) -> dict:
    """
    Insert new jobs and update sources on existing duplicates.

    Returns a stats dict: {"inserted": int, "updated": int, "skipped": int}
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    if not jobs:
        return stats

    existing = get_existing_jobs(client)

    # Deduplicate within the incoming batch too
    seen_in_batch: dict[tuple, dict] = {}
    to_insert = []
    to_update = []  # (row_id, new_sources_list)

    for job in jobs:
        # Score quality
        job["data_quality_score"] = compute_quality_score(job)
        job["sources"] = [job["source"]]

        # Skip jobs with no title at all
        if not job.get("job_title", "").strip():
            stats["skipped"] += 1
            continue

        key = _dedup_key(job)

        # Already in database?
        if key in existing:
            db_row = existing[key]
            if job["source"] not in db_row["sources"]:
                new_sources = list(set(db_row["sources"] + [job["source"]]))
                to_update.append((db_row["id"], new_sources))
                # Update the cache so further dupes in this batch don't re-trigger
                db_row["sources"] = new_sources
            else:
                stats["skipped"] += 1
            continue

        # Already seen earlier in this batch?
        if key in seen_in_batch:
            prev = seen_in_batch[key]
            if job["source"] not in prev["sources"]:
                prev["sources"].append(job["source"])
            stats["skipped"] += 1
            continue

        seen_in_batch[key] = job
        to_insert.append(job)

    # --- Batch insert new jobs ---
    batch_size = 50
    for i in range(0, len(to_insert), batch_size):
        batch = to_insert[i : i + batch_size]
        try:
            client.table("raw_jobs").insert(batch).execute()
            stats["inserted"] += len(batch)
        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            # Fall back to one-by-one to salvage what we can
            for single in batch:
                try:
                    client.table("raw_jobs").insert(single).execute()
                    stats["inserted"] += 1
                except Exception:
                    stats["skipped"] += 1

    # --- Update sources on existing duplicates ---
    for row_id, new_sources in to_update:
        try:
            client.table("raw_jobs").update({"sources": new_sources}).eq("id", row_id).execute()
            stats["updated"] += 1
        except Exception as e:
            logger.error(f"Source update failed for row {row_id}: {e}")

    return stats
