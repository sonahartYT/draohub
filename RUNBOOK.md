# DracoHub — Technical Runbook

> **Audience:** Anyone maintaining DracoHub. You don't need to be a developer, but you should be comfortable running a terminal command.
> **Last updated:** July 2026

---

## 1. What is DracoHub?

DracoHub is an Oil & Gas job aggregator for Nigeria. It scrapes job listings daily from multiple sources, tags them with AI, and emails a curated weekly digest to paid subscribers.

**Live site:** https://dracohub.co  
**GitHub repo:** https://github.com/sonahartYT/draohub  
**Admin page:** https://dracohub.co/admin.html (password: see note below)

---

## 2. System Architecture

```
GitHub Actions (automation hub)
    │
    ├── Daily scrape (7am UTC)  →  Supabase DB  →  docs/jobs.json (GitHub Pages)
    ├── Weekly digest (Mon 8am UTC)  →  Resend (email)  →  paid subscribers
    ├── Renewal reminder (daily 8am UTC)  →  Resend + Termii SMS  →  expiring subscribers
    └── Auto-expiry (daily 1am UTC)  →  Supabase  →  marks expired subscriptions

GitHub Pages (static hosting)
    └── docs/ folder on main branch  →  https://dracohub.co

Supabase (database + auth)
    └── subscribers table, jobs table, auth users

Flutterwave (payments)
    └── live key in docs/app.js

Resend (transactional email)
    └── SMTP + API, from: digest@dracohub.co

Termii (SMS)
    └── Sender ID: Dracohub
```

---

## 3. Automated Workflows (run without any human action)

| Workflow | Schedule | What it does | Where to check |
|----------|----------|--------------|----------------|
| Daily Job Scrape | 7am UTC (8am WAT) | Scrapes jobs, tags with Claude AI, updates jobs.json | GitHub Actions → Daily Job Scrape |
| Weekly Digest Email | Monday 8am UTC (9am WAT) | Emails personalised job digest to paid subscribers | GitHub Actions → Weekly Digest Email |
| Renewal Reminder | Daily 8am UTC | Emails/SMS subscribers expiring in 3 days | GitHub Actions → Subscription Renewal Reminder |
| Auto-Expire Subscriptions | Daily 1am UTC | Marks subscriptions expired if past 30 days | GitHub Actions → Auto-Expire Subscriptions |

**To check if any workflow failed:**
1. Go to https://github.com/sonahartYT/draohub/actions
2. A red X = failed. A green tick = success.
3. Click on a failed run to see the error log.

---

## 4. Common Fixes

### 4.1 — The weekly digest didn't send

**Symptoms:** Monday came and went, subscribers report no email.

**Steps:**
1. Go to https://github.com/sonahartYT/draohub/actions → Weekly Digest Email
2. If the last run is red (failed), click it, read the error
3. To trigger it manually:
   ```bash
   gh workflow run weekly-digest.yml --ref main
   ```
   Or go to GitHub → Actions → Weekly Digest Email → Run workflow → Run workflow (leave dry run unchecked)

**Common causes:**
- A GitHub Actions Node.js update broke things → already fixed with `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true`
- A Supabase API call failed → usually temporary, just re-run
- `RESEND_API_KEY` expired → update it in GitHub Secrets (see Section 6)

---

### 4.2 — The daily scrape failed

**Symptoms:** Jobs on the site look stale/outdated.

**Steps:**
1. Go to GitHub Actions → Daily Job Scrape, check for red runs
2. To trigger manually:
   ```bash
   gh workflow run daily-scrape.yml --ref main
   ```
   Or via GitHub UI: Actions → Daily Job Scrape → Run workflow
3. The scrape takes ~15-20 minutes to complete
4. After it finishes, `docs/jobs.json` is automatically updated and committed

**Common causes:**
- Job board websites changed their layout (scraper needs updating — needs a developer)
- `ANTHROPIC_API_KEY` or `SERPER_API_KEY` expired → update in GitHub Secrets

---

### 4.3 — A subscriber says they can't log in / confirm email

**Steps:**
1. Go to https://supabase.com → DracoHub project → Authentication → Users
2. Search for their email
3. Check if their email is confirmed (there's a "Confirmed" column)
4. If not confirmed: click their row → "Send magic link" or manually confirm

**If Supabase email confirmation stops working entirely:**
- Check Supabase → Project Settings → Authentication → SMTP Settings
- SMTP host: `smtp.resend.com`, Port: `465`, User: `resend`, Password = Resend API key

---

### 4.4 — Subscriber paid but their status isn't updating to "paid"

**Steps:**
1. Go to Supabase → Table Editor → `subscribers` table
2. Search for their email
3. Check `subscription_status` column
4. If it's still `free`, manually update it:
   - Click the row → edit `subscription_status` to `paid`
   - Set `subscription_expires_at` to 30 days from today (e.g. `2026-08-05T00:00:00+00:00`)
5. Also check Flutterwave dashboard to confirm payment was received

---

### 4.5 — The site is down / shows old content

The site is hosted on GitHub Pages from the `docs/` folder on the `main` branch.

**Steps:**
1. Check https://github.com/sonahartYT/draohub/actions → look for `pages build and deployment`
2. If it's red, there may be a broken file in `docs/` — check recent commits
3. GitHub Pages status: https://www.githubstatus.com

**The site should never go fully down** unless GitHub itself is down. Jobs.json updates every day via the scrape workflow.

---

### 4.6 — Flutterwave payment button not working

The live Flutterwave key is in `docs/app.js`:
```
FLWPUBK-46eacd3bb99e6db0652248a5a390859f-X
```

**If payments stop working:**
1. Log into your Flutterwave dashboard
2. Check if the API key is still active / not revoked
3. If you've rotated the key, update it in `docs/app.js` line 11, then push to main

---

## 5. How to Deploy a Change

All changes go through Git → GitHub → auto-deploys to GitHub Pages.

```bash
# Navigate to the project
cd /Users/sonahart/Library/CloudStorage/OneDrive-Personal/CLAUDE\ CODE/DRACOHUB

# Check what changed
git status
git diff

# Stage and commit
git add docs/index.html   # add the specific files you changed
git commit -m "fix: description of what you changed"

# Push — GitHub Pages auto-deploys in ~1-2 minutes
git push
```

**Never push directly to main if someone else is maintaining this** — use a branch + pull request.

---

## 6. Secrets & API Keys

All secrets live in **GitHub Repository Secrets**: https://github.com/sonahartYT/draohub/settings/secrets/actions

| Secret | What it's for | Where to get a new one |
|--------|--------------|----------------------|
| `SUPABASE_URL` | Database connection | Supabase → Project Settings → API |
| `SUPABASE_KEY` | DB read/write (anon key) | Supabase → Project Settings → API |
| `SUPABASE_SERVICE_KEY` | DB admin (bypasses RLS) | Supabase → Project Settings → API |
| `ANTHROPIC_API_KEY` | AI job tagging | console.anthropic.com |
| `RESEND_API_KEY` | Email sending | resend.com → API Keys |
| `DIGEST_FROM_EMAIL` | From address for emails | Currently: `digest@dracohub.co` |
| `TERMII_API_KEY` | SMS sending | termii.com dashboard |
| `TERMII_SENDER_ID` | SMS sender name | `Dracohub` |
| `SERPER_API_KEY` | Job search (Google) | serper.dev |
| `KIT_API_KEY` | Newsletter (Kit/ConvertKit) | kit.com |

**To update a secret:**
1. Go to the secrets page above
2. Click the secret name → Update → paste new value → Save

---

## 7. Database Overview (Supabase)

**Project:** https://supabase.com → DracoHub project  
**Main table:** `subscribers`

Key columns in `subscribers`:
- `email` — unique identifier
- `subscription_status` — `free`, `paid`, or `expired`
- `subscription_expires_at` — timestamp, 30 days after payment
- `name`, `category`, `seniority`, `location_pref` — used to personalise digests
- `whatsapp_number`, `phone` — for SMS delivery

**To query manually:**
Go to Supabase → Table Editor → `subscribers` → use the filter bar

---

## 8. Subscription Lifecycle

```
User signs up (free)
    ↓
Pays via Flutterwave on profile page
    ↓
subscription_status = 'paid'
subscription_expires_at = now + 30 days
    ↓
Day 27: Renewal reminder email + SMS sent automatically
    ↓
Day 30: Auto-expiry workflow marks them 'expired'
    ↓
Profile page shows "No active subscription" with button to re-subscribe
```

---

## 9. Admin Page

**URL:** https://dracohub.co/admin.html  
**Password:** `dracohub2026`

Shows visitor stats. For deeper analytics, use **Google Analytics**: analytics.google.com → DracoHub property (tracking ID: G-RW46C4GGWS).

---

## 10. Contacts & Accounts

| Service | Login |
|---------|-------|
| GitHub | sonahartYT |
| Supabase | dracovantservices@gmail.com |
| Flutterwave | dracovantservices@gmail.com |
| Resend | dracovantservices@gmail.com |
| Vercel | dracovantservices@gmail.com (connected but not actively used — GitHub Pages is primary) |
| Termii | dracovantservices@gmail.com |

---

## 11. Monthly Maintenance Checklist

Do this once a month (takes ~15 minutes):

- [ ] Check GitHub Actions — any recurring red runs?
- [ ] Check Supabase → subscribers — any `paid` users whose `subscription_expires_at` is in the past but status wasn't updated? (auto-expiry should catch these)
- [ ] Check Flutterwave dashboard — payments coming through correctly?
- [ ] Check Resend dashboard — any email bounces or delivery failures?
- [ ] Check Google Analytics — traffic trends, anything unusual?
- [ ] Review one or two job listings on the site — are links still working? Companies still hiring?

---

## 12. When to Call a Developer

You don't need a developer for routine operations. Get a developer when:

- A scraper stops finding jobs (job boards change their HTML structure)
- You want to add a new feature (e.g. WhatsApp delivery, more job sources)
- A GitHub Actions workflow error shows Python code failing (not just a credentials issue)
- Supabase Row Level Security is blocking something unexpected

**Estimated maintenance cost (hosting/APIs per month at ~2000 subscribers):**
- Supabase: Free tier (upgrade ~$25/mo if DB exceeds limits)
- GitHub Actions: Free (public repo)
- Resend: ~$20/mo at 2000 emails/week
- Anthropic API: ~$5-10/mo for tagging
- Termii SMS: ~$10-20/mo depending on SMS volume
- Flutterwave: 1.4% per transaction (no monthly fee)
- **Total: ~$55-75/mo**
