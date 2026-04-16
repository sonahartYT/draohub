-- DracoHub Careers — Schema V4: Serper.dev detected_extensions
-- Run this in Supabase SQL Editor before the first Serper scraper run.
-- Purely additive — does not modify existing columns, indexes, or policies.

-- 1. Add a JSONB column to store Serper.dev's detected_extensions payload
--    (e.g. {"posted_at": "2 days ago", "schedule_type": "Full-time", "salary": "..."})
ALTER TABLE raw_jobs
    ADD COLUMN IF NOT EXISTS detected_extensions JSONB;
