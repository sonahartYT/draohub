#!/usr/bin/env python3
"""
DracoHub — Weekly Digest Sender

Fetches this week's jobs from Supabase, generates an HTML digest,
and sends it as a Kit broadcast to all 'digest-paid' tagged subscribers.

Usage:
    python scripts/send_digest.py              # send live
    python scripts/send_digest.py --dry-run    # generate HTML, don't send
    python scripts/send_digest.py --preview    # write digest.html locally for inspection
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("send_digest")

SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
KIT_API_KEY   = os.getenv("KIT_API_KEY")
KIT_DIGEST_TAG_ID = os.getenv("KIT_DIGEST_TAG_ID")  # numeric ID of 'digest-paid' tag in Kit
SITE_URL      = "https://sonahartyt.github.io/dracohub/"

ACCENT   = "#ED880D"
DARK     = "#1a2635"
CATEGORY_ORDER = [
    "Engineering", "HSE", "Operations", "Project Management",
    "Finance", "IT/Digital", "Management", "Legal/Contracts", "HR", "Other",
]

# Max jobs per category in the digest
MAX_PER_CATEGORY = 5
# Max total jobs
MAX_TOTAL = 30


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------

def supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def fetch_this_weeks_jobs() -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    jobs, offset = [], 0
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/raw_jobs",
            headers=supabase_headers(),
            params={
                "select": "id,job_title,company,location,apply_url,tags,created_at,flag_count",
                "created_at": f"gte.{since}",
                "flag_count": "lt.3",
                "order": "created_at.desc",
                "limit": 200,
                "offset": offset,
            },
            timeout=30,
        )
        page = resp.json()
        jobs.extend(page)
        if len(page) < 200:
            break
        offset += 200
    logger.info("Fetched %d jobs from the past 7 days", len(jobs))
    return jobs


# ---------------------------------------------------------------------------
# Job selection — curated cross-section
# ---------------------------------------------------------------------------

def select_jobs(all_jobs: list[dict]) -> dict[str, list[dict]]:
    """Pick the best jobs per category, return {category: [jobs]}."""
    by_category: dict[str, list[dict]] = {}

    for job in all_jobs:
        cat = (job.get("tags") or {}).get("category") or "Other"
        by_category.setdefault(cat, []).append(job)

    selected: dict[str, list[dict]] = {}
    total = 0
    for cat in CATEGORY_ORDER:
        if cat not in by_category or total >= MAX_TOTAL:
            continue
        jobs = by_category[cat][:MAX_PER_CATEGORY]
        selected[cat] = jobs
        total += len(jobs)

    # Append any leftover categories not in CATEGORY_ORDER
    for cat, jobs in by_category.items():
        if cat not in selected and total < MAX_TOTAL:
            selected[cat] = jobs[:MAX_PER_CATEGORY]
            total += len(jobs[:MAX_PER_CATEGORY])

    return selected


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def week_label() -> str:
    today = datetime.now(timezone.utc)
    monday = today - timedelta(days=today.weekday())
    return f"Week of {monday.strftime('%-d %B %Y')}"


def job_row_html(job: dict) -> str:
    title   = job.get("job_title") or "Untitled"
    company = job.get("company") or "Company not listed"
    location = job.get("location") or ""
    url     = job.get("apply_url") or f"{SITE_URL}?job={job['id']}"
    tags    = job.get("tags") or {}
    seniority = tags.get("seniority") or ""
    employment = tags.get("employment_type") or ""

    badge = ""
    if employment and employment != "Full-time":
        badge = f'<span style="display:inline-block;background:rgba(237,136,13,0.15);color:{ACCENT};font-size:0.7rem;font-weight:700;padding:2px 8px;border-radius:10px;margin-left:8px;text-transform:uppercase;letter-spacing:0.05em;">{employment}</span>'
    elif seniority and seniority not in ("Mid-Level",):
        badge = f'<span style="display:inline-block;background:#f0f4f8;color:#4a6080;font-size:0.7rem;font-weight:600;padding:2px 8px;border-radius:10px;margin-left:8px;">{seniority}</span>'

    location_html = f'<span style="color:#7a8fa8;font-size:0.82rem;">{location}</span>' if location else ""

    return f"""
    <tr>
      <td style="padding:14px 0;border-bottom:1px solid #eef2f7;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
          <div style="flex:1;">
            <div style="font-weight:600;color:{DARK};font-size:0.95rem;margin-bottom:3px;">
              {title}{badge}
            </div>
            <div style="color:#4a6080;font-size:0.85rem;">{company} {location_html}</div>
          </div>
          <a href="{url}" style="display:inline-block;background:{ACCENT};color:#fff;text-decoration:none;padding:7px 16px;border-radius:6px;font-size:0.8rem;font-weight:700;white-space:nowrap;flex-shrink:0;">Apply</a>
        </div>
      </td>
    </tr>"""


def category_section_html(category: str, jobs: list[dict]) -> str:
    rows = "".join(job_row_html(j) for j in jobs)
    return f"""
    <tr><td style="padding:24px 0 8px;">
      <div style="font-size:0.7rem;font-weight:800;color:{ACCENT};text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px;">{category}</div>
      <table width="100%" cellpadding="0" cellspacing="0" border="0"><tbody>
        {rows}
      </tbody></table>
    </td></tr>"""


def build_html(selected: dict[str, list[dict]], total_this_week: int) -> str:
    week = week_label()
    companies = len({j.get("company") for cat_jobs in selected.values() for j in cat_jobs if j.get("company")})
    total_shown = sum(len(v) for v in selected.values())

    category_sections = "".join(
        category_section_html(cat, jobs) for cat, jobs in selected.items()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DracoHub Weekly Digest — {week}</title>
</head>
<body style="background:#f0f4f8;font-family:'Helvetica Neue',Arial,sans-serif;color:{DARK};margin:0;padding:0;">

<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td align="center" style="padding:32px 16px;">

  <table width="660" cellpadding="0" cellspacing="0" border="0" style="max-width:660px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 32px rgba(0,0,0,0.10);">

    <!-- Header -->
    <tr><td style="background:{DARK};padding:36px 40px 28px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="font-size:1.35rem;font-weight:800;color:#fff;letter-spacing:-0.03em;">
            Draco<span style="color:{ACCENT};">Hub</span>.
          </td>
          <td align="right" style="font-size:0.72rem;font-weight:700;color:{ACCENT};background:rgba(237,136,13,0.15);padding:4px 12px;border-radius:20px;letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap;">
            {week}
          </td>
        </tr>
      </table>
      <div style="color:#fff;font-size:1.15rem;font-weight:600;margin-top:24px;margin-bottom:6px;">Your weekly O&amp;G digest is here.</div>
      <div style="color:#7a8fa8;font-size:0.88rem;line-height:1.5;">We scanned every major Nigerian job platform so you don't have to. Here's what's worth your attention this week.</div>
    </td></tr>

    <!-- Stats strip -->
    <tr><td style="background:#f8fafc;padding:20px 40px;border-bottom:1px solid #eef2f7;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
        <td align="center" style="padding:0 12px;">
          <div style="font-size:1.6rem;font-weight:800;color:{ACCENT};">{total_shown}</div>
          <div style="font-size:0.75rem;color:#7a8fa8;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Curated Roles</div>
        </td>
        <td align="center" style="padding:0 12px;border-left:1px solid #eef2f7;">
          <div style="font-size:1.6rem;font-weight:800;color:{DARK};">{total_this_week}</div>
          <div style="font-size:0.75rem;color:#7a8fa8;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">New This Week</div>
        </td>
        <td align="center" style="padding:0 12px;border-left:1px solid #eef2f7;">
          <div style="font-size:1.6rem;font-weight:800;color:{DARK};">{companies}</div>
          <div style="font-size:0.75rem;color:#7a8fa8;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Companies</div>
        </td>
      </tr></table>
    </td></tr>

    <!-- Jobs -->
    <tr><td style="padding:8px 40px 24px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"><tbody>
        {category_sections}
      </tbody></table>
    </td></tr>

    <!-- CTA -->
    <tr><td style="background:#f8fafc;padding:32px 40px;text-align:center;border-top:1px solid #eef2f7;">
      <div style="font-size:1rem;font-weight:700;color:{DARK};margin-bottom:8px;">See all {total_this_week} new listings on the board</div>
      <div style="font-size:0.85rem;color:#7a8fa8;margin-bottom:20px;">Filter by category, location, or seniority to find exactly what fits.</div>
      <a href="{SITE_URL}" style="display:inline-block;background:{ACCENT};color:#fff;text-decoration:none;padding:13px 32px;border-radius:8px;font-weight:700;font-size:0.95rem;">Browse All Jobs →</a>
    </td></tr>

    <!-- Footer -->
    <tr><td style="padding:24px 40px;text-align:center;border-top:1px solid #eef2f7;">
      <div style="font-size:0.78rem;color:#a0b0c0;line-height:1.6;">
        You're receiving this because you subscribed to DracoHub Weekly Digest.<br>
        <a href="{{{{ subscriber.unsubscribe_url }}}}" style="color:#a0b0c0;">Unsubscribe</a>
      </div>
    </td></tr>

  </table>
</td></tr>
</table>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Kit API
# ---------------------------------------------------------------------------

def kit_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "X-Kit-Api-Key": KIT_API_KEY,
    }


def create_and_send_broadcast(subject: str, html: str, dry_run: bool) -> bool:
    if dry_run:
        logger.info("[DRY RUN] Would send broadcast: %s", subject)
        return True

    # Create broadcast and schedule for immediate send via send_at
    send_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    payload = {
        "subject": subject,
        "content": html,
        "description": f"Auto-generated digest — {week_label()}",
        "public": False,
        "send_at": send_at,
        "subscriber_filter": [
            {"all": [{"type": "tag", "ids": [int(KIT_DIGEST_TAG_ID)]}]}
        ],
    }
    resp = requests.post(
        "https://api.kit.com/v4/broadcasts",
        headers=kit_headers(),
        json=payload,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        logger.error("Failed to create broadcast: %s %s", resp.status_code, resp.text[:300])
        return False

    broadcast_id = resp.json()["broadcast"]["id"]
    logger.info("Broadcast created and queued for send id=%s", broadcast_id)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Send DracoHub weekly digest via Kit")
    parser.add_argument("--dry-run", action="store_true", help="Build digest but don't send")
    parser.add_argument("--preview", action="store_true", help="Write digest.html locally for inspection")
    args = parser.parse_args()

    if not args.dry_run and not args.preview:
        for var in ("SUPABASE_URL", "SUPABASE_KEY", "KIT_API_KEY", "KIT_DIGEST_TAG_ID"):
            if not os.getenv(var):
                logger.error("Missing required env var: %s", var)
                sys.exit(1)

    logger.info("=" * 55)
    logger.info("DracoHub — Weekly Digest Sender")
    logger.info("=" * 55)

    jobs = fetch_this_weeks_jobs()
    if not jobs:
        logger.warning("No jobs this week — skipping digest.")
        return

    selected = select_jobs(jobs)
    total_shown = sum(len(v) for v in selected.values())
    logger.info("Selected %d jobs across %d categories", total_shown, len(selected))

    html = build_html(selected, len(jobs))

    if args.preview:
        out = os.path.join(os.path.dirname(__file__), "digest_preview.html")
        with open(out, "w") as f:
            f.write(html)
        logger.info("Preview written to %s", out)
        return

    week = week_label()
    subject = f"DracoHub Digest — {total_shown} curated O&G roles ({week})"
    success = create_and_send_broadcast(subject, html, dry_run=args.dry_run)

    if success:
        logger.info("Digest sent: %s", subject)
    else:
        logger.error("Digest failed to send.")
        sys.exit(1)


if __name__ == "__main__":
    main()
