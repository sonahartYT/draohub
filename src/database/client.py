"""
DracoHub Careers — Supabase database client.

Uses direct PostgREST HTTP calls via requests (not the supabase-py SDK,
which hangs on WebSocket initialisation on some platforms).

Schema columns written by this module:
    job_title, company, location, date_posted, description, apply_url,
    source, sources[], data_quality_score, detected_extensions

Dedup index (v2):
    idx_raw_jobs_dedup ON raw_jobs (job_title, COALESCE(company,''), COALESCE(location,''))

Cross-source merging: if the same job (matched by title+company+location)
is seen from a new source, we PATCH the existing row to append the source
to the sources[] array rather than inserting a duplicate.
"""
import logging
import math
import os

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

_session: requests.Session | None = None


def get_client() -> requests.Session:
    """
    Return a requests.Session pre-loaded with Supabase auth headers.
    Raises RuntimeError if credentials are missing.
    """
    global _session
    if _session is not None:
        return _session

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

    s = requests.Session()
    s.headers.update({
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    })
    s.base_url = f"{url.rstrip('/')}/rest/v1"  # type: ignore[attr-defined]
    _session = s
    return _session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(value) -> str | None:
    """Return None for any falsy, NaN, or NA value; otherwise a clean string."""
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
    except (TypeError, ValueError):
        pass
    s = str(value).strip()
    return s if s and s.lower() not in ("none", "nan", "nat", "n/a", "") else None


def compute_quality_score(job: dict) -> int:
    """Score 1–5 based on how many of the six key fields are populated."""
    fields = ["job_title", "company", "location", "date_posted", "description", "apply_url"]
    filled = sum(1 for f in fields if job.get(f))
    if filled >= 6: return 5
    if filled >= 5: return 4
    if filled >= 4: return 3
    if filled >= 3: return 2
    return 1


def _dedup_key(job: dict) -> tuple:
    """Normalised (title, company, location) — matches the v2 unique index."""
    return (
        (job.get("job_title") or "").strip().lower(),
        (job.get("company") or "").strip().lower(),
        (job.get("location") or "").strip().lower(),
    )


def _build_row(raw: dict, source: str) -> dict | None:
    """
    Normalise a scraper job dict into a raw_jobs row.
    Returns None if job_title is missing (required NOT NULL).
    """
    job_title = _clean(raw.get("job_title") or raw.get("title"))
    if not job_title:
        return None

    apply_url = _clean(raw.get("apply_url") or raw.get("job_url"))

    row = {
        "job_title":   job_title,
        "company":     _clean(raw.get("company")),
        "location":    _clean(raw.get("location")),
        "date_posted": _clean(raw.get("date_posted")),
        "description": _clean(raw.get("description")),
        "apply_url":   apply_url,
        "source":      source,
        "sources":     [source],
    }

    # Preserve detected_extensions if the scraper provides it (Serper.dev)
    if raw.get("detected_extensions"):
        row["detected_extensions"] = raw["detected_extensions"]

    row["data_quality_score"] = compute_quality_score(row)
    return row


# ---------------------------------------------------------------------------
# Dedup: fetch existing rows
# ---------------------------------------------------------------------------

def _fetch_existing(session: requests.Session) -> dict[tuple, dict]:
    """
    Fetch all existing rows (id, job_title, company, location, sources).
    Returns a dict keyed by normalised (title, company, location).

    Paginated in chunks of 1000 to handle large tables.
    """
    existing: dict[tuple, dict] = {}
    offset = 0
    page_size = 1000

    while True:
        resp = session.get(
            f"{session.base_url}/raw_jobs",
            params={
                "select": "id,job_title,company,location,sources",
                "order": "id.asc",
                "offset": offset,
                "limit": page_size,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error("fetch existing failed: %s %s", resp.status_code, resp.text[:200])
            break

        rows = resp.json()
        for row in rows:
            key = (
                (row.get("job_title") or "").strip().lower(),
                (row.get("company") or "").strip().lower(),
                (row.get("location") or "").strip().lower(),
            )
            existing[key] = {"id": row["id"], "sources": row.get("sources") or []}

        if len(rows) < page_size:
            break
        offset += page_size

    return existing


# ---------------------------------------------------------------------------
# Insert + update
# ---------------------------------------------------------------------------

def _insert_batch(session: requests.Session, batch: list[dict]) -> int:
    """
    Insert a batch of new rows. On conflict, falls back to one-by-one.
    Returns the number of successfully inserted rows.
    """
    resp = session.post(
        f"{session.base_url}/raw_jobs",
        json=batch,
        headers={**session.headers, "Prefer": "return=minimal"},
        timeout=30,
    )
    if resp.status_code in (200, 201, 204):
        return len(batch)
    if resp.status_code == 409:
        # Mixed batch — insert row by row
        inserted = 0
        for row in batch:
            r = session.post(
                f"{session.base_url}/raw_jobs",
                json=row,
                headers={**session.headers, "Prefer": "return=minimal"},
                timeout=15,
            )
            if r.status_code in (200, 201, 204):
                inserted += 1
            elif r.status_code != 409:
                logger.error("single insert failed: %s %s", r.status_code, r.text[:150])
        return inserted
    logger.error("batch insert failed: %s %s", resp.status_code, resp.text[:200])
    return 0


def _append_source(session: requests.Session, row_id: int, new_sources: list[str]) -> bool:
    """PATCH an existing row to update its sources array."""
    resp = session.patch(
        f"{session.base_url}/raw_jobs",
        params={"id": f"eq.{row_id}"},
        json={"sources": new_sources},
        headers={**session.headers, "Prefer": "return=minimal"},
        timeout=15,
    )
    return resp.status_code in (200, 201, 204)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def insert_jobs(session: requests.Session, jobs: list[dict], source: str | None = None) -> dict:
    """
    Deduplicate and insert a list of jobs.

    - New jobs (not in DB, not seen earlier in this batch): inserted.
    - Same job, new source: sources[] array updated on existing row.
    - True duplicates (same job, same source already recorded): skipped.

    Returns: {"inserted": int, "updated": int, "skipped": int}
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    if not jobs:
        return stats

    # Normalise rows (also resolves source from row if not passed explicitly)
    rows = []
    for raw in jobs:
        src = source or raw.get("source") or "unknown"
        row = _build_row(raw, src)
        if row:
            rows.append(row)
        else:
            stats["skipped"] += 1

    if not rows:
        return stats

    # Fetch existing rows for dedup
    existing = _fetch_existing(session)

    to_insert: list[dict] = []
    seen_in_batch: dict[tuple, dict] = {}

    for row in rows:
        key = _dedup_key(row)
        source_val = row["source"]

        if key in existing:
            db_row = existing[key]
            if source_val not in db_row["sources"]:
                new_sources = list(set(db_row["sources"] + [source_val]))
                if _append_source(session, db_row["id"], new_sources):
                    db_row["sources"] = new_sources
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
            else:
                stats["skipped"] += 1
            continue

        if key in seen_in_batch:
            prev = seen_in_batch[key]
            if source_val not in prev["sources"]:
                prev["sources"].append(source_val)
            stats["skipped"] += 1
            continue

        seen_in_batch[key] = row
        to_insert.append(row)

    # Batch insert new rows
    batch_size = 50
    for i in range(0, len(to_insert), batch_size):
        batch = to_insert[i : i + batch_size]
        stats["inserted"] += _insert_batch(session, batch)

    return stats
