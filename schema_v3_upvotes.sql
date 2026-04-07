-- DracoHub Careers — Schema V3: Upvote System
-- Run this in Supabase SQL Editor

-- 1. Add upvotes counter to raw_jobs
ALTER TABLE raw_jobs ADD COLUMN IF NOT EXISTS upvotes INTEGER DEFAULT 0;

-- 2. Index for sorting by popularity
CREATE INDEX IF NOT EXISTS idx_raw_jobs_upvotes ON raw_jobs (upvotes DESC);
