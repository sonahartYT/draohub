-- DracoHub Careers - Supabase Database Schema
-- Run this in the Supabase SQL Editor (Dashboard > SQL Editor > New Query)

-- ============================================================
-- Table: raw_jobs
-- Stores scraped job listings before any AI processing.
-- This is the "landing zone" — future tables (e.g. processed_jobs,
-- user_alerts) will reference or derive from this data.
-- ============================================================

CREATE TABLE IF NOT EXISTS raw_jobs (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_title   TEXT NOT NULL,
    company     TEXT,
    location    TEXT,
    date_posted TEXT,                -- kept as TEXT because source formats vary
    description TEXT,
    apply_url   TEXT,
    source      TEXT NOT NULL,       -- 'linkedin', 'myjobmag', 'jobberman', etc.
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Unique constraint to prevent duplicate listings.
-- Two jobs are considered duplicates if they share the same title,
-- company, and source. This lets the scraper do a simple upsert.
CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_jobs_dedup
    ON raw_jobs (job_title, company, source);

-- Index for quick lookups by source (useful for the future web board)
CREATE INDEX IF NOT EXISTS idx_raw_jobs_source
    ON raw_jobs (source);

-- Index for date-based queries (useful for the future email/WhatsApp digests)
CREATE INDEX IF NOT EXISTS idx_raw_jobs_created_at
    ON raw_jobs (created_at DESC);

-- Enable Row Level Security (good practice, even if we only use the service key for now)
ALTER TABLE raw_jobs ENABLE ROW LEVEL SECURITY;

-- Allow the anon/service key to read and insert (adjust when you add auth)
CREATE POLICY "Allow public read" ON raw_jobs FOR SELECT USING (true);
CREATE POLICY "Allow service insert" ON raw_jobs FOR INSERT WITH CHECK (true);
