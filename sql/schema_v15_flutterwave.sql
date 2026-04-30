-- DracoHub schema v15 — Flutterwave payment columns
-- Run in Supabase SQL Editor

ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS flw_ref              TEXT;
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS flw_tx_id            TEXT;
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMPTZ;
