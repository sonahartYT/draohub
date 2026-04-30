-- DracoHub schema v14 — Per-subscriber digest link pages
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS digests (
    id            uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
    subscriber_email text,
    week_label    text,
    first_name    text,
    is_personalised boolean   DEFAULT false,
    jobs          jsonb,      -- [{job_title, company, location, apply_url, tags, _reason}]
    created_at    timestamptz DEFAULT now(),
    expires_at    timestamptz DEFAULT (now() + interval '7 days')
);

-- Anyone with the link (UUID) can read — UUID is the access key
ALTER TABLE digests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "digests_public_read"
    ON digests FOR SELECT
    USING (true);

-- Only service role can insert/update (send_digest.py uses service key)
-- No explicit insert policy needed — service role bypasses RLS

-- Auto-purge expired rows (optional — keeps table tidy)
-- You can run this manually or set up a pg_cron job:
-- DELETE FROM digests WHERE expires_at < now();

-- Index for fast lookup by ID (primary key already covers this,
-- but explicit for clarity)
-- CREATE INDEX IF NOT EXISTS idx_digests_id ON digests (id);
