-- DracoHub Careers — Schema V2 Migration
-- Run this in Supabase SQL Editor AFTER the original schema.sql
-- Adds: sources array, data_quality_score, improved dedup index

-- 1. Add new columns
ALTER TABLE raw_jobs ADD COLUMN IF NOT EXISTS sources TEXT[] DEFAULT '{}';
ALTER TABLE raw_jobs ADD COLUMN IF NOT EXISTS data_quality_score INTEGER DEFAULT 0;

-- 2. Backfill: copy existing `source` value into the `sources` array
UPDATE raw_jobs SET sources = ARRAY[source] WHERE sources = '{}' OR sources IS NULL;

-- 3. Drop the old unique index (was on title + company + source)
DROP INDEX IF EXISTS idx_raw_jobs_dedup;

-- 4. Create new unique index on title + company + location
--    This means the same job from LinkedIn and Jobberman merges into one row
CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_jobs_dedup
    ON raw_jobs (job_title, COALESCE(company, ''), COALESCE(location, ''));

-- 5. Allow updates (needed so we can append to the sources array)
CREATE POLICY "Allow service update" ON raw_jobs FOR UPDATE USING (true) WITH CHECK (true);

-- 6. Index on data_quality_score for filtering low-quality listings
CREATE INDEX IF NOT EXISTS idx_raw_jobs_quality
    ON raw_jobs (data_quality_score);
