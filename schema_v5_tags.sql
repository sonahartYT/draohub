-- ============================================================
-- DracoHub schema v5: AI/rule-based job tags
-- Run once in Supabase SQL editor
-- ============================================================

-- Add tags column (JSONB — flexible, queryable, filterable)
ALTER TABLE raw_jobs ADD COLUMN IF NOT EXISTS tags JSONB;

-- Index for fast filtering by category, discipline, seniority
CREATE INDEX IF NOT EXISTS idx_raw_jobs_tags ON raw_jobs USING GIN (tags);

-- Convenience: index on specific tag keys for common filter patterns
CREATE INDEX IF NOT EXISTS idx_raw_jobs_tags_category
    ON raw_jobs ((tags->>'category'));

CREATE INDEX IF NOT EXISTS idx_raw_jobs_tags_discipline
    ON raw_jobs ((tags->>'discipline'));

CREATE INDEX IF NOT EXISTS idx_raw_jobs_tags_seniority
    ON raw_jobs ((tags->>'seniority'));
