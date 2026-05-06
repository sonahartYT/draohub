-- DracoHub schema v16 — WhatsApp delivery + auth constraints
-- These changes were applied manually; this file documents them.
-- Run in Supabase SQL Editor (safe to re-run — uses IF NOT EXISTS / ON CONFLICT).

-- 1. Unique constraint on user_id — required for upsert ON CONFLICT(user_id)
ALTER TABLE subscribers
    ADD CONSTRAINT IF NOT EXISTS subscribers_user_id_key UNIQUE (user_id);

-- 2. WhatsApp number column — stores subscriber's WhatsApp for Termii delivery
ALTER TABLE subscribers
    ADD COLUMN IF NOT EXISTS whatsapp_number TEXT;

-- ─── digests table (v14, included here for completeness) ───────────────────
-- Stores per-subscriber weekly digest data for the web viewer (digest.html).
-- The UUID is the access key embedded in the WhatsApp CTA link.

CREATE TABLE IF NOT EXISTS digests (
    id               UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    subscriber_email TEXT,
    week_label       TEXT,
    first_name       TEXT,
    is_personalised  BOOLEAN     DEFAULT false,
    jobs             JSONB,      -- [{job_title, company, location, apply_url, tags, _reason}]
    created_at       TIMESTAMPTZ DEFAULT now(),
    expires_at       TIMESTAMPTZ DEFAULT (now() + INTERVAL '7 days')
);

-- Public read — anyone with the UUID link can view their digest
ALTER TABLE digests ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "digests_public_read"
    ON digests FOR SELECT
    USING (true);

-- Service role (used by send_digest.py) bypasses RLS — no extra INSERT policy needed.

-- Optional: clean up expired digests (run manually or via pg_cron)
-- DELETE FROM digests WHERE expires_at < now();
