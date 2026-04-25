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
    title      = job.get("job_title") or "Untitled"
    company    = job.get("company") or "Company not listed"
    location   = job.get("location") or ""
    url        = job.get("apply_url") or f"{SITE_URL}?job={job['id']}"
    tags       = job.get("tags") or {}
    seniority  = tags.get("seniority") or ""
    employment = tags.get("employment_type") or ""

    badge = ""
    if employment and employment != "Full-time":
        badge = (
            f' <span style="display:inline-block;background:rgba(237,136,13,0.12);'
            f'color:#ED880D;font-size:11px;font-weight:700;padding:2px 7px;'
            f'border-radius:8px;text-transform:uppercase;vertical-align:middle;">'
            f'{employment}</span>'
        )
    elif seniority and seniority not in ("Mid-Level",):
        badge = (
            f' <span style="display:inline-block;background:#F3F4F6;'
            f'color:#6B7280;font-size:11px;font-weight:600;padding:2px 7px;'
            f'border-radius:8px;vertical-align:middle;">{seniority}</span>'
        )

    location_html = (
        f'&nbsp;&bull;&nbsp;<span style="color:#9CA3AF;font-size:13px;">{location}</span>'
        if location else ""
    )

    return (
        f'<tr><td style="padding:13px 0;border-bottom:1px solid #F3F4F6;">'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="padding-right:12px;">'
        f'<div style="font-weight:600;color:#142A47;font-size:15px;margin-bottom:3px;line-height:1.35;">{title}{badge}</div>'
        f'<div style="color:#6B7280;font-size:13px;">{company}{location_html}</div>'
        f'</td>'
        f'<td width="64" align="right" valign="middle">'
        f'<a href="{url}" style="display:inline-block;background:#ED880D;color:#ffffff;'
        f'text-decoration:none;padding:8px 14px;border-radius:6px;font-size:13px;'
        f'font-weight:700;white-space:nowrap;">Apply</a>'
        f'</td>'
        f'</tr></table>'
        f'</td></tr>'
    )


def category_section_html(category: str, jobs: list[dict]) -> str:
    rows = "".join(job_row_html(j) for j in jobs)
    return (
        f'<tr><td style="padding-top:20px;">'
        f'<div style="font-size:11px;font-weight:800;color:#ED880D;'
        f'text-transform:uppercase;letter-spacing:1.2px;margin-bottom:4px;">{category}</div>'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0">{rows}</table>'
        f'</td></tr>'
    )


def build_jobs_table(selected: dict[str, list[dict]]) -> str:
    """Wrap all category sections in a single table for mj-raw injection."""
    sections = "".join(category_section_html(cat, jobs) for cat, jobs in selected.items())
    return f'<table width="100%" cellpadding="0" cellspacing="0" border="0">{sections}</table>'


def build_html(selected: dict[str, list[dict]], total_this_week: int) -> str:
    from mjml import mjml_to_html

    week      = week_label()
    companies = len({j.get("company") for cat_jobs in selected.values() for j in cat_jobs if j.get("company")})
    total_shown = sum(len(v) for v in selected.values())
    jobs_table  = build_jobs_table(selected)

    mjml_src = f"""
<mjml>
  <mj-head>
    <mj-preview>Your weekly O&G digest — {total_shown} curated roles this week</mj-preview>
    <mj-attributes>
      <mj-all font-family="'Helvetica Neue', Helvetica, Arial, sans-serif" />
      <mj-section padding="0" background-color="#ffffff" />
      <mj-column padding="0" />
      <mj-text padding="0" font-size="14px" line-height="1.6" color="#142A47" />
    </mj-attributes>
  </mj-head>

  <mj-body background-color="#F0F4F8">

    <!-- Top spacer -->
    <mj-section padding="24px 0 0" background-color="#F0F4F8" />

    <!-- Header -->
    <mj-section background-color="#142A47" padding="28px 28px 24px" border-radius="14px 14px 0 0">
      <mj-column>
        <mj-text font-size="22px" font-weight="800" color="#ffffff" letter-spacing="-0.5px" padding-bottom="10px">
          Draco<span style="color:#ED880D;">Hub</span>.
        </mj-text>
        <mj-text padding-bottom="14px">
          <span style="display:inline-block;background:rgba(237,136,13,0.18);color:#ED880D;font-size:11px;font-weight:700;padding:4px 12px;border-radius:20px;text-transform:uppercase;letter-spacing:1px;">{week}</span>
        </mj-text>
        <mj-text font-size="18px" font-weight="700" color="#ffffff" padding-bottom="6px">
          Your weekly O&amp;G digest is here.
        </mj-text>
        <mj-text font-size="14px" color="#8AA0B8" line-height="1.6">
          We scanned every major Nigerian job platform so you don't have to. Here's what's worth your attention this week.
        </mj-text>
      </mj-column>
    </mj-section>

    <!-- Stats -->
    <mj-section background-color="#F9FAFB" border-top="2px solid #F3F4F6" border-bottom="2px solid #F3F4F6" padding="16px 0">
      <mj-column padding="8px">
        <mj-text align="center" font-size="26px" font-weight="800" color="#ED880D" padding-bottom="2px">{total_shown}</mj-text>
        <mj-text align="center" font-size="10px" font-weight="700" color="#9CA3AF" letter-spacing="1px" padding-top="2px">CURATED ROLES</mj-text>
      </mj-column>
      <mj-column padding="8px" border-left="1px solid #E5E7EB" border-right="1px solid #E5E7EB">
        <mj-text align="center" font-size="26px" font-weight="800" color="#142A47" padding-bottom="2px">{total_this_week}</mj-text>
        <mj-text align="center" font-size="10px" font-weight="700" color="#9CA3AF" letter-spacing="1px" padding-top="2px">NEW THIS WEEK</mj-text>
      </mj-column>
      <mj-column padding="8px">
        <mj-text align="center" font-size="26px" font-weight="800" color="#142A47" padding-bottom="2px">{companies}</mj-text>
        <mj-text align="center" font-size="10px" font-weight="700" color="#9CA3AF" letter-spacing="1px" padding-top="2px">COMPANIES</mj-text>
      </mj-column>
    </mj-section>

    <!-- Job listings -->
    <mj-section padding="8px 24px 16px">
      <mj-column>
        <mj-raw>{jobs_table}</mj-raw>
      </mj-column>
    </mj-section>

    <!-- CTA -->
    <mj-section background-color="#F9FAFB" border-top="2px solid #F3F4F6" padding="28px 24px">
      <mj-column>
        <mj-text align="center" font-size="16px" font-weight="700" color="#142A47" padding-bottom="6px">
          See all {total_this_week} new listings on the board
        </mj-text>
        <mj-text align="center" font-size="13px" color="#6B7280" padding-bottom="20px">
          Filter by category, location, or seniority.
        </mj-text>
        <mj-button background-color="#ED880D" color="#ffffff" border-radius="8px" font-size="15px" font-weight="700" href="{SITE_URL}" inner-padding="13px 28px" align="center">
          Browse All Jobs →
        </mj-button>
      </mj-column>
    </mj-section>

    <!-- Footer -->
    <mj-section border-top="2px solid #F3F4F6" padding="20px 24px" border-radius="0 0 14px 14px">
      <mj-column>
        <mj-text align="center" font-size="12px" color="#9CA3AF" line-height="1.7">
          You're receiving this because you subscribed to DracoHub Weekly Digest.<br />
          <a href="{{{{ subscriber.unsubscribe_url }}}}" style="color:#9CA3AF;text-decoration:underline;">Unsubscribe</a>
        </mj-text>
      </mj-column>
    </mj-section>

    <!-- Bottom spacer -->
    <mj-section padding="0 0 24px" background-color="#F0F4F8" />

  </mj-body>
</mjml>
"""

    result = mjml_to_html(mjml_src)
    if result.errors:
        logger.warning("MJML warnings: %s", result.errors)
    logger.info("Email HTML compiled via MJML")
    return result.html


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
