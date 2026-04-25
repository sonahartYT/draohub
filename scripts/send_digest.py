#!/usr/bin/env python3
"""
DracoHub — Weekly Digest Sender (Personalised + Generic fallback)

For each paid subscriber:
  - If profile is complete enough → two-stage AI personalisation via Claude
  - Otherwise → generic curated digest (fallback)

All emails sent via Resend. Kit kept for subscriber tag management only.

Usage:
    python scripts/send_digest.py              # send live
    python scripts/send_digest.py --dry-run    # build emails, don't send
    python scripts/send_digest.py --preview    # write preview HTMLs as artifacts
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import anthropic
import requests
from dotenv import load_dotenv
from mjml import mjml_to_html

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("send_digest")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SUPABASE_URL      = os.getenv("SUPABASE_URL")
SUPABASE_KEY      = os.getenv("SUPABASE_KEY")
RESEND_API_KEY    = os.getenv("RESEND_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
FROM_EMAIL        = os.getenv("DIGEST_FROM_EMAIL", "DracoHub Digest <digest@dracohub.com>")
SITE_URL          = "https://sonahartyt.github.io/dracohub/"

ACCENT = "#ED880D"
DARK   = "#142A47"

CATEGORY_ORDER = [
    "Engineering", "HSE", "Operations", "Project Management",
    "Finance", "IT/Digital", "Management", "Legal/Contracts", "HR", "Other",
]
MAX_PER_CATEGORY = 5
MAX_TOTAL        = 30

# Minimum profile fields needed to attempt personalisation
REQUIRED_FIELDS = ["category"]


# ---------------------------------------------------------------------------
# Supabase helpers
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


def fetch_paid_subscribers() -> list[dict]:
    """Fetch all paid subscribers with their profile data."""
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/subscribers",
        headers=supabase_headers(),
        params={
            "select": (
                "email,name,category,seniority,location_pref,work_type_pref,"
                "years_experience,background,open_to_relocation,"
                "employment_status,job_hunting_status,subscription_status"
            ),
            "subscription_status": "eq.paid",
        },
        timeout=30,
    )
    subs = resp.json() if resp.status_code == 200 else []
    logger.info("Found %d paid subscribers", len(subs))
    return subs


# ---------------------------------------------------------------------------
# Generic digest — job selection
# ---------------------------------------------------------------------------

def select_jobs(all_jobs: list[dict]) -> dict[str, list[dict]]:
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

    for cat, jobs in by_category.items():
        if cat not in selected and total < MAX_TOTAL:
            selected[cat] = jobs[:MAX_PER_CATEGORY]
            total += len(jobs[:MAX_PER_CATEGORY])

    return selected


# ---------------------------------------------------------------------------
# HTML helpers — shared between generic and personalised
# ---------------------------------------------------------------------------

def week_label() -> str:
    today  = datetime.now(timezone.utc)
    monday = today - timedelta(days=today.weekday())
    return f"Week of {monday.strftime('%-d %B %Y')}"


def job_row_html(job: dict, reason: str = "") -> str:
    title      = job.get("job_title") or "Untitled"
    company    = job.get("company") or "Company not listed"
    location   = job.get("location") or ""
    url        = job.get("apply_url") or f"{SITE_URL}?job={job.get('id','')}"
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

    reason_html = ""
    if reason:
        reason_html = (
            f'<div style="margin-top:4px;font-size:12px;color:#ED880D;font-weight:600;">'
            f'&#10003;&nbsp;{reason}</div>'
        )

    return (
        f'<tr><td style="padding:13px 0;border-bottom:1px solid #F3F4F6;">'
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="padding-right:12px;">'
        f'<div style="font-weight:600;color:#142A47;font-size:15px;margin-bottom:3px;line-height:1.35;">{title}{badge}</div>'
        f'<div style="color:#6B7280;font-size:13px;">{company}{location_html}</div>'
        f'{reason_html}'
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
    sections = "".join(category_section_html(cat, jobs) for cat, jobs in selected.items())
    return f'<table width="100%" cellpadding="0" cellspacing="0" border="0">{sections}</table>'


def build_personalised_jobs_table(ranked_jobs: list[dict]) -> str:
    rows = "".join(job_row_html(j, reason=j.get("_reason", "")) for j in ranked_jobs)
    return f'<table width="100%" cellpadding="0" cellspacing="0" border="0">{rows}</table>'


# ---------------------------------------------------------------------------
# Generic digest HTML (MJML)
# ---------------------------------------------------------------------------

def build_generic_html(selected: dict[str, list[dict]], total_this_week: int) -> str:
    week        = week_label()
    companies   = len({j.get("company") for v in selected.values() for j in v if j.get("company")})
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
    <mj-section padding="24px 0 0" background-color="#F0F4F8" />
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
    <mj-section padding="8px 24px 16px">
      <mj-column>
        <mj-raw>{jobs_table}</mj-raw>
      </mj-column>
    </mj-section>
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
    <mj-section border-top="2px solid #F3F4F6" padding="20px 24px" border-radius="0 0 14px 14px">
      <mj-column>
        <mj-text align="center" font-size="12px" color="#9CA3AF" line-height="1.7">
          You're receiving this because you subscribed to DracoHub Weekly Digest.<br />
          <a href="{SITE_URL}profile.html" style="color:#9CA3AF;text-decoration:underline;">Manage subscription</a>
        </mj-text>
      </mj-column>
    </mj-section>
    <mj-section padding="0 0 24px" background-color="#F0F4F8" />
  </mj-body>
</mjml>
"""
    result = mjml_to_html(mjml_src)
    if result.errors:
        logger.warning("MJML warnings (generic): %s", result.errors)
    return result.html


# ---------------------------------------------------------------------------
# Personalised digest — two-stage pipeline
# ---------------------------------------------------------------------------

def is_profile_complete(sub: dict) -> bool:
    return all(sub.get(f) for f in REQUIRED_FIELDS)


def prefilter_jobs(all_jobs: list[dict], sub: dict) -> list[dict]:
    """Stage 1 — code-based filter. Cuts ~250 jobs to ~30-40."""
    category   = (sub.get("category") or "").lower()
    seniority  = (sub.get("seniority") or "").lower()
    location   = (sub.get("location_pref") or "").lower()
    work_type  = (sub.get("work_type_pref") or "").lower()
    relocation = sub.get("open_to_relocation") or False

    # Seniority tier mapping for fuzzy matching
    SENIORITY_TIERS = {
        "junior":    {"junior", "entry", "graduate", "trainee", "intern"},
        "mid-level": {"mid", "mid-level", "intermediate"},
        "senior":    {"senior", "lead", "principal", "specialist"},
        "manager":   {"manager", "head", "director", "vp", "chief"},
    }
    user_tier = None
    for tier, keywords in SENIORITY_TIERS.items():
        if any(k in seniority for k in keywords) or seniority == tier:
            user_tier = tier
            break

    scored = []
    for job in all_jobs:
        score  = 0
        tags   = job.get("tags") or {}
        j_cat  = (tags.get("category") or "").lower()
        j_sen  = (tags.get("seniority") or "").lower()
        j_loc  = (job.get("location") or "").lower()
        j_emp  = (tags.get("employment_type") or "").lower()

        # Category — highest weight
        if category and category in j_cat:
            score += 10
        elif category and j_cat in category:
            score += 4

        # Seniority tier match
        if user_tier:
            tier_keywords = SENIORITY_TIERS.get(user_tier, set())
            if any(k in j_sen for k in tier_keywords):
                score += 6

        # Location match (relaxed if open to relocation)
        if location and location in j_loc:
            score += 4
        elif location and relocation and j_loc:
            score += 1  # still worth showing, just lower priority

        # Work type
        if work_type and work_type in j_emp:
            score += 2

        scored.append((score, job))

    # Sort descending, take top 40, but always include at least 15 jobs
    scored.sort(key=lambda x: x[0], reverse=True)
    filtered = [j for _, j in scored[:40] if scored[0][0] > 0 or True]

    # Ensure minimum of 15 for Claude to work with
    if len([j for _, j in scored if _ > 0]) < 15:
        filtered = [j for _, j in scored[:25]]

    logger.debug("Pre-filter: %d → %d jobs for %s", len(all_jobs), len(filtered), sub.get("email"))
    return filtered


def rank_jobs_with_claude(filtered_jobs: list[dict], sub: dict) -> list[dict]:
    """Stage 2 — one Claude Haiku call ranks filtered jobs and adds reasons."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build compact job list for the prompt
    jobs_text = "\n".join(
        f"{i+1}. {j.get('job_title','?')} at {j.get('company','?')} "
        f"({j.get('location','')}) "
        f"[{(j.get('tags') or {}).get('category','')} / {(j.get('tags') or {}).get('seniority','')}]"
        for i, j in enumerate(filtered_jobs)
    )

    # Build profile summary
    profile_lines = []
    fields = [
        ("category",          "Desired category"),
        ("seniority",         "Seniority level"),
        ("location_pref",     "Location preference"),
        ("work_type_pref",    "Work type preference"),
        ("years_experience",  "Years of experience"),
        ("background",        "Educational background"),
        ("employment_status", "Employment status"),
        ("job_hunting_status","Job hunting status"),
    ]
    for key, label in fields:
        val = sub.get(key)
        if val:
            profile_lines.append(f"- {label}: {val}")
    if sub.get("open_to_relocation"):
        profile_lines.append("- Open to relocation: Yes")

    profile_text = "\n".join(profile_lines) if profile_lines else "- No profile data"

    prompt = f"""You are a job matching assistant for Nigerian oil & gas professionals.

CANDIDATE PROFILE:
{profile_text}

JOBS THIS WEEK ({len(filtered_jobs)} listings):
{jobs_text}

Return the top 10 most relevant jobs for this candidate as a JSON array.
Each item: {{"index": <1-based number>, "reason": "<max 7 words why this fits>"}}

Rules:
- Rank by relevance to the candidate's profile
- Reasons must be specific: "exact seniority and category match", "Port Harcourt location match", etc.
- Return ONLY the JSON array, no other text"""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        logger.warning("Claude returned unexpected format, using top 10 pre-filtered")
        return filtered_jobs[:10]

    try:
        rankings = json.loads(match.group())
    except json.JSONDecodeError:
        logger.warning("Claude JSON parse failed, using top 10 pre-filtered")
        return filtered_jobs[:10]

    ranked = []
    for item in rankings:
        idx = item.get("index", 0) - 1
        if 0 <= idx < len(filtered_jobs):
            job = dict(filtered_jobs[idx])
            job["_reason"] = item.get("reason", "")
            ranked.append(job)

    return ranked or filtered_jobs[:10]


def build_personalised_html(ranked_jobs: list[dict], sub: dict, total_this_week: int) -> str:
    week       = week_label()
    name       = sub.get("name") or "there"
    first_name = name.split()[0] if name != "there" else name
    category   = sub.get("category") or ""
    seniority  = sub.get("seniority") or ""
    location   = sub.get("location_pref") or ""

    # Build profile summary line for the header
    profile_bits = [p for p in [seniority, category, location] if p]
    profile_line = " · ".join(profile_bits) if profile_bits else "your profile"

    jobs_table = build_personalised_jobs_table(ranked_jobs)
    total_matches = len(ranked_jobs)

    mjml_src = f"""
<mjml>
  <mj-head>
    <mj-preview>{total_matches} roles matched to your profile this week</mj-preview>
    <mj-attributes>
      <mj-all font-family="'Helvetica Neue', Helvetica, Arial, sans-serif" />
      <mj-section padding="0" background-color="#ffffff" />
      <mj-column padding="0" />
      <mj-text padding="0" font-size="14px" line-height="1.6" color="#142A47" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#F0F4F8">
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
          Hi {first_name}, your matched roles are in.
        </mj-text>
        <mj-text font-size="14px" color="#8AA0B8" line-height="1.6">
          Out of {total_this_week} new listings this week, we found <strong style="color:#ffffff;">{total_matches} roles</strong> that match your profile ({profile_line}).
        </mj-text>
      </mj-column>
    </mj-section>

    <!-- Stats -->
    <mj-section background-color="#F9FAFB" border-top="2px solid #F3F4F6" border-bottom="2px solid #F3F4F6" padding="16px 0">
      <mj-column padding="8px">
        <mj-text align="center" font-size="26px" font-weight="800" color="#ED880D" padding-bottom="2px">{total_matches}</mj-text>
        <mj-text align="center" font-size="10px" font-weight="700" color="#9CA3AF" letter-spacing="1px" padding-top="2px">MATCHED ROLES</mj-text>
      </mj-column>
      <mj-column padding="8px" border-left="1px solid #E5E7EB" border-right="1px solid #E5E7EB">
        <mj-text align="center" font-size="26px" font-weight="800" color="#142A47" padding-bottom="2px">{total_this_week}</mj-text>
        <mj-text align="center" font-size="10px" font-weight="700" color="#9CA3AF" letter-spacing="1px" padding-top="2px">NEW THIS WEEK</mj-text>
      </mj-column>
      <mj-column padding="8px">
        <mj-text align="center" font-size="26px" font-weight="800" color="#142A47" padding-bottom="2px">AI</mj-text>
        <mj-text align="center" font-size="10px" font-weight="700" color="#9CA3AF" letter-spacing="1px" padding-top="2px">RANKED FOR YOU</mj-text>
      </mj-column>
    </mj-section>

    <!-- Matched jobs -->
    <mj-section padding="8px 24px 16px">
      <mj-column>
        <mj-raw>{jobs_table}</mj-raw>
      </mj-column>
    </mj-section>

    <!-- CTA -->
    <mj-section background-color="#F9FAFB" border-top="2px solid #F3F4F6" padding="28px 24px">
      <mj-column>
        <mj-text align="center" font-size="16px" font-weight="700" color="#142A47" padding-bottom="6px">
          See all {total_this_week} listings on the board
        </mj-text>
        <mj-text align="center" font-size="13px" color="#6B7280" padding-bottom="20px">
          Search, filter, and find more roles that fit.
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
          You're receiving this because you have an active DracoHub subscription.<br />
          <a href="{SITE_URL}profile.html" style="color:#9CA3AF;text-decoration:underline;">Update your profile</a>
          &nbsp;&middot;&nbsp;
          <a href="{SITE_URL}profile.html" style="color:#9CA3AF;text-decoration:underline;">Manage subscription</a>
        </mj-text>
      </mj-column>
    </mj-section>

    <mj-section padding="0 0 24px" background-color="#F0F4F8" />
  </mj-body>
</mjml>
"""
    result = mjml_to_html(mjml_src)
    if result.errors:
        logger.warning("MJML warnings (personalised): %s", result.errors)
    return result.html


# ---------------------------------------------------------------------------
# Resend — email delivery
# ---------------------------------------------------------------------------

def send_via_resend(to_email: str, subject: str, html: str, dry_run: bool = False) -> bool:
    if dry_run:
        logger.info("[DRY RUN] Would send to %s: %s", to_email, subject)
        return True

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
            "html": html,
        },
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        logger.error("Resend failed for %s: %s %s", to_email, resp.status_code, resp.text[:200])
        return False

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Send DracoHub weekly digest")
    parser.add_argument("--dry-run", action="store_true", help="Build emails but don't send")
    parser.add_argument("--preview", action="store_true", help="Write preview HTMLs as artifacts")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("DracoHub — Weekly Digest Sender")
    logger.info("Mode: %s", "DRY RUN" if args.dry_run else "PREVIEW" if args.preview else "LIVE")
    logger.info("=" * 60)

    # 1. Fetch jobs
    all_jobs = fetch_this_weeks_jobs()
    if not all_jobs:
        logger.warning("No jobs this week — skipping digest.")
        return

    # 2. Pre-build generic digest (used as fallback)
    selected_generic = select_jobs(all_jobs)
    total_shown_generic = sum(len(v) for v in selected_generic.values())
    generic_subject = f"DracoHub Digest — {total_shown_generic} curated O&G roles ({week_label()})"

    # 3. Preview mode — write both templates as artifacts
    if args.preview:
        generic_html = build_generic_html(selected_generic, len(all_jobs))
        out_generic = os.path.join(os.path.dirname(__file__), "digest_preview_generic.html")
        with open(out_generic, "w") as f:
            f.write(generic_html)
        logger.info("Generic preview written to %s", out_generic)

        # Write a dummy personalised preview with fake profile
        dummy_sub = {
            "email": "preview@example.com",
            "name": "Amaka Okafor",
            "category": "Engineering",
            "seniority": "Senior",
            "location_pref": "Lagos",
            "work_type_pref": "Full-time",
            "years_experience": "6-10",
            "background": "Mechanical Engineering",
            "open_to_relocation": True,
        }
        filtered  = prefilter_jobs(all_jobs, dummy_sub)
        ranked    = rank_jobs_with_claude(filtered, dummy_sub)
        pers_html = build_personalised_html(ranked, dummy_sub, len(all_jobs))
        out_pers  = os.path.join(os.path.dirname(__file__), "digest_preview_personalised.html")
        with open(out_pers, "w") as f:
            f.write(pers_html)
        logger.info("Personalised preview written to %s", out_pers)
        return

    # 4. Fetch paid subscribers
    subscribers = fetch_paid_subscribers()
    if not subscribers:
        logger.warning("No paid subscribers found — nothing to send.")
        return

    # 5. Send to each subscriber
    sent_personalised = 0
    sent_generic      = 0
    failed            = 0

    for sub in subscribers:
        email = sub.get("email")
        if not email:
            logger.warning("Subscriber missing email, skipping: %s", sub)
            continue

        try:
            if is_profile_complete(sub):
                # Two-stage personalised path
                filtered = prefilter_jobs(all_jobs, sub)
                ranked   = rank_jobs_with_claude(filtered, sub)
                html     = build_personalised_html(ranked, sub, len(all_jobs))
                subject  = f"Your {len(ranked)} matched O&G roles this week — DracoHub"
                label    = "personalised"
            else:
                # Generic fallback
                html    = build_generic_html(selected_generic, len(all_jobs))
                subject = generic_subject
                label   = "generic (incomplete profile)"

            success = send_via_resend(email, subject, html, dry_run=args.dry_run)

            if success:
                logger.info("✓ %s → %s (%s)", email, subject[:50], label)
                if label.startswith("personalised"):
                    sent_personalised += 1
                else:
                    sent_generic += 1
            else:
                failed += 1

        except Exception as e:
            logger.error("Error processing %s: %s", email, e)
            # Try generic fallback on error
            try:
                html    = build_generic_html(selected_generic, len(all_jobs))
                success = send_via_resend(email, generic_subject, html, dry_run=args.dry_run)
                if success:
                    sent_generic += 1
                    logger.info("✓ %s → sent generic fallback after error", email)
                else:
                    failed += 1
            except Exception as e2:
                logger.error("Fallback also failed for %s: %s", email, e2)
                failed += 1

    logger.info("=" * 60)
    logger.info("Done. Personalised: %d | Generic: %d | Failed: %d",
                sent_personalised, sent_generic, failed)
    logger.info("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
