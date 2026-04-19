-- Add profile token to subscribers (auto-generated UUID per subscriber)
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS profile_token UUID DEFAULT gen_random_uuid();

-- Ensure tokens are unique and indexed for fast lookup
CREATE UNIQUE INDEX IF NOT EXISTS subscribers_profile_token_idx ON subscribers (profile_token);

-- Safe RPC for updating profile preferences via token (anon-accessible)
-- Only allows updating preference fields — not email, subscription status, or payment data
CREATE OR REPLACE FUNCTION update_subscriber_profile(
    p_token       UUID,
    p_name        TEXT,
    p_category    TEXT,
    p_seniority   TEXT,
    p_location_pref TEXT,
    p_background  TEXT
)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    updated_count INT;
BEGIN
    UPDATE subscribers
    SET
        name          = p_name,
        category      = p_category,
        seniority     = p_seniority,
        location_pref = p_location_pref,
        background    = p_background
    WHERE profile_token = p_token;

    GET DIAGNOSTICS updated_count = ROW_COUNT;

    IF updated_count = 0 THEN
        RETURN json_build_object('success', false, 'error', 'Invalid token');
    END IF;

    RETURN json_build_object('success', true);
END;
$$;

GRANT EXECUTE ON FUNCTION update_subscriber_profile TO anon;

-- Allow anon to read subscriber record by token (for profile page)
-- (SELECT policy may already exist from schema_v7 — this is a no-op if so)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'subscribers' AND policyname = 'allow_anon_select'
    ) THEN
        EXECUTE 'CREATE POLICY "allow_anon_select" ON subscribers FOR SELECT TO anon USING (true)';
    END IF;
END$$;
