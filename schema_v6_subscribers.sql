-- DracoHub schema v6: job alert subscribers
-- Run once in Supabase SQL editor

CREATE TABLE IF NOT EXISTS subscribers (
    id          BIGSERIAL PRIMARY KEY,
    email       TEXT UNIQUE NOT NULL,
    name        TEXT,
    category    TEXT,        -- matches tags.category (Engineering, HSE, etc.)
    seniority   TEXT,        -- matches tags.seniority
    location_pref TEXT,      -- city preference
    frequency   TEXT DEFAULT 'weekly',   -- 'weekly' | 'daily' (paid)
    active      BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Index for digest queries
CREATE INDEX IF NOT EXISTS idx_subscribers_active ON subscribers (active);
CREATE INDEX IF NOT EXISTS idx_subscribers_category ON subscribers (category);

-- Allow anonymous inserts from the frontend (sign-ups)
ALTER TABLE subscribers ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "allow_anon_insert" ON subscribers
    FOR INSERT TO anon WITH CHECK (true);

CREATE POLICY IF NOT EXISTS "allow_anon_select_own" ON subscribers
    FOR SELECT TO anon USING (false);  -- users can't read other subscribers
