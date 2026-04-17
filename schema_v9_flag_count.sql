-- Add flag_count column to raw_jobs
ALTER TABLE raw_jobs ADD COLUMN IF NOT EXISTS flag_count INTEGER DEFAULT 0;

-- Allow anon users to call the flag function (safe: only increments flag_count)
CREATE OR REPLACE FUNCTION increment_flag_count(job_id BIGINT)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  UPDATE raw_jobs SET flag_count = COALESCE(flag_count, 0) + 1 WHERE id = job_id;
END;
$$;

GRANT EXECUTE ON FUNCTION increment_flag_count TO anon;
