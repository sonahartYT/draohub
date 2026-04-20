#!/usr/bin/env python3
"""Export all jobs from Supabase to docs/jobs.json for static serving.

Runs after each scrape in GitHub Actions (service role key bypasses
the API key allowlist that blocks browser requests).
"""
import json
import os
import sys

import requests


def main():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set", file=sys.stderr)
        sys.exit(1)

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }

    jobs = []
    limit = 1000
    offset = 0

    while True:
        resp = requests.get(
            f"{url}/rest/v1/raw_jobs",
            params={
                "select": "*",
                "order": "created_at.desc",
                "limit": limit,
                "offset": offset,
            },
            headers=headers,
        )
        resp.raise_for_status()
        batch = resp.json()
        jobs.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "jobs.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, default=str)

    print(f"Exported {len(jobs)} jobs → {out_path}")


if __name__ == "__main__":
    main()
