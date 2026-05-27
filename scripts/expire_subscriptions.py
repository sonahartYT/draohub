#!/usr/bin/env python3
"""
DracoHub — Subscription Auto-Expiry

Runs daily. Finds all subscribers with subscription_status='paid' whose
subscription_expires_at is in the past, and marks them as 'expired'.

Usage:
    python scripts/expire_subscriptions.py           # live run
    python scripts/expire_subscriptions.py --dry-run # preview only
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("expire_subscriptions")

SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")


def service_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def fetch_expired() -> list[dict]:
    """Find paid subscribers whose subscription_expires_at is in the past."""
    now = datetime.now(timezone.utc).isoformat()
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/subscribers",
        headers=service_headers(),
        params={
            "select": "id,email,name,subscription_expires_at",
            "subscription_status": "eq.paid",
            "subscription_expires_at": f"lt.{now}",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        logger.error("Failed to fetch subscribers: %s %s", resp.status_code, resp.text)
        return []
    return resp.json()


def mark_expired(subscriber_id: str, dry_run: bool) -> bool:
    if dry_run:
        return True
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/subscribers",
        headers=service_headers(),
        params={"id": f"eq.{subscriber_id}"},
        json={"subscription_status": "expired"},
        timeout=30,
    )
    return resp.status_code in (200, 204)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        logger.error("SUPABASE_URL and SUPABASE_SERVICE_KEY are required.")
        sys.exit(1)

    expired = fetch_expired()

    if not expired:
        logger.info("No expired subscriptions found.")
        return

    logger.info("Found %d expired subscription(s)%s", len(expired),
                " (dry run — no changes)" if args.dry_run else "")

    success, failed = 0, 0
    for sub in expired:
        name  = sub.get("name") or sub.get("email", "unknown")
        expiry = sub.get("subscription_expires_at", "unknown")
        logger.info("Expiring: %s (expired %s)", name, expiry)

        if mark_expired(sub["id"], args.dry_run):
            success += 1
        else:
            logger.error("Failed to expire subscription for %s", name)
            failed += 1

    logger.info("Done — %d expired%s, %d failed",
                success,
                " (dry run)" if args.dry_run else "",
                failed)


if __name__ == "__main__":
    main()
