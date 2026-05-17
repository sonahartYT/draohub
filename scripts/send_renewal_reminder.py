#!/usr/bin/env python3
"""
DracoHub — Subscription Renewal Reminder

Runs daily. Finds paid subscribers whose subscription expires in exactly
3 days and sends them an email + SMS reminder to renew.

Usage:
    python scripts/send_renewal_reminder.py           # live
    python scripts/send_renewal_reminder.py --dry-run # log only, don't send
"""

import argparse
import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("renewal_reminder")

SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
RESEND_API_KEY       = os.getenv("RESEND_API_KEY")
TERMII_API_KEY       = os.getenv("TERMII_API_KEY")
TERMII_SENDER_ID     = os.getenv("TERMII_SENDER_ID", "DracoHub")
FROM_EMAIL           = os.getenv("DIGEST_FROM_EMAIL", "DracoHub Digest <digest@dracohub.co>")
SITE_URL             = "https://dracohub.co/"
RENEW_URL            = f"{SITE_URL}profile.html"

REMINDER_DAYS = 3  # how many days before expiry to send the reminder


def service_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def fetch_expiring_subscribers() -> list[dict]:
    """Return paid subscribers whose subscription expires in REMINDER_DAYS days."""
    now = datetime.now(timezone.utc)
    window_start = (now + timedelta(days=REMINDER_DAYS)).replace(hour=0, minute=0, second=0, microsecond=0)
    window_end   = window_start + timedelta(days=1)

    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/subscribers",
        headers=service_headers(),
        params={
            "select": "email,name,phone,whatsapp_number,subscription_expires_at",
            "subscription_status": "eq.paid",
            "subscription_expires_at": f"gte.{window_start.isoformat()}",
            "and": f"(subscription_expires_at.lt.{window_end.isoformat()})",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        logger.error("Failed to fetch subscribers: %s %s", resp.status_code, resp.text[:200])
        return []
    subs = resp.json()
    logger.info("Found %d subscriber(s) expiring in %d days", len(subs), REMINDER_DAYS)
    return subs


def build_email_html(name: str, expires_at: str) -> str:
    first = name.split()[0] if name else "there"
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        expiry_str = expiry.strftime("%-d %B %Y")
    except Exception:
        expiry_str = expires_at[:10]

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:40px 16px;">
    <tr><td align="center">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#fff;border-radius:12px;overflow:hidden;">
        <tr><td style="background:#142A47;padding:28px 32px;">
          <span style="font-size:1.3rem;font-weight:800;color:#fff;">Draco<span style="color:#ED880D;">Hub</span>.</span>
        </td></tr>
        <tr><td style="padding:32px;">
          <p style="margin:0 0 16px;font-size:1rem;color:#111;">Hi {first},</p>
          <p style="margin:0 0 16px;font-size:1rem;color:#374151;line-height:1.6;">
            Your DracoHub subscription expires on <strong>{expiry_str}</strong> — that's in {REMINDER_DAYS} days.
          </p>
          <p style="margin:0 0 24px;font-size:1rem;color:#374151;line-height:1.6;">
            Renew now to keep getting your weekly personalised O&amp;G digest straight to your inbox and your phone every Monday.
          </p>
          <a href="{RENEW_URL}" style="display:inline-block;background:#ED880D;color:#fff;font-weight:700;font-size:0.95rem;padding:14px 28px;border-radius:8px;text-decoration:none;">
            Renew My Subscription →
          </a>
          <p style="margin:24px 0 0;font-size:0.82rem;color:#9ca3af;">
            ₦3,000/month · Cancel any time · Questions? Reply to this email.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


def send_email(to_email: str, name: str, expires_at: str, dry_run: bool = False) -> bool:
    subject = f"Your DracoHub digest expires in {REMINDER_DAYS} days — renew to keep it going"
    html = build_email_html(name, expires_at)

    if dry_run:
        logger.info("[DRY RUN] Would email %s: %s", to_email, subject)
        return True

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={"from": FROM_EMAIL, "to": [to_email], "subject": subject, "html": html},
        timeout=15,
    )
    if resp.status_code in (200, 201):
        logger.info("✓ Renewal email sent to %s", to_email)
        return True
    logger.error("Email failed for %s: %s %s", to_email, resp.status_code, resp.text[:200])
    return False


def send_sms(phone: str, name: str, dry_run: bool = False) -> bool:
    if not TERMII_API_KEY:
        return False

    first = name.split()[0] if name else "there"
    clean = phone.strip().lstrip("+")
    if clean.startswith("0"):
        clean = "234" + clean[1:]

    message = (
        f"Hi {first}, your DracoHub subscription expires in {REMINDER_DAYS} days. "
        f"Renew at {RENEW_URL} to keep your weekly O&G job digest. ₦3,000/mo."
    )

    if dry_run:
        logger.info("[DRY RUN] Would SMS %s: %s", clean, message[:80] + "…")
        return True

    resp = requests.post(
        "https://api.ng.termii.com/api/sms/send",
        json={
            "to": clean,
            "from": TERMII_SENDER_ID,
            "sms": message,
            "type": "plain",
            "channel": "generic",
            "api_key": TERMII_API_KEY,
        },
        timeout=15,
    )
    result = resp.json() if resp.ok else {}
    if resp.ok and result.get("message_id") or result.get("messageId"):
        logger.info("✓ Renewal SMS sent to %s", clean)
        return True
    logger.error("SMS failed for %s: %s %s", clean, resp.status_code, resp.text[:200])
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("Mode: DRY RUN")

    subs = fetch_expiring_subscribers()
    if not subs:
        logger.info("No subscribers expiring in %d days. Nothing to send.", REMINDER_DAYS)
        return

    email_sent = sms_sent = failed = 0

    for sub in subs:
        email     = sub.get("email")
        name      = sub.get("name") or ""
        phone     = sub.get("whatsapp_number") or sub.get("phone")
        expires   = sub.get("subscription_expires_at", "")

        if not email:
            continue

        ok = send_email(email, name, expires, dry_run=args.dry_run)
        if ok:
            email_sent += 1
        else:
            failed += 1

        if phone:
            sms_ok = send_sms(phone, name, dry_run=args.dry_run)
            if sms_ok:
                sms_sent += 1

    logger.info("=" * 60)
    logger.info("Done. Emails: %d | SMS: %d | Failed: %d", email_sent, sms_sent, failed)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
