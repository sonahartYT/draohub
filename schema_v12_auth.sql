-- ============================================================
-- schema_v12_auth.sql
-- Full user authentication via Supabase Auth
-- Adds user_id FK, extended profile columns, and auth-based RLS
--
-- BEFORE RUNNING:
--   1. Go to Supabase → Authentication → Settings
--   2. Disable "Enable email confirmations" (so users log in immediately)
--
-- Run in Supabase SQL Editor
-- ============================================================

-- ------------------------------------------------------------
-- 1. Link subscribers to auth.users
-- ------------------------------------------------------------
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS subscribers_user_id_idx ON subscribers (user_id);

-- ------------------------------------------------------------
-- 2. Extended profile columns
-- ------------------------------------------------------------
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS years_experience TEXT;        -- '0-1', '1-3', '3-5', '5-10', '10+'
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS current_role TEXT;
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS current_company TEXT;
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS linkedin_url TEXT;
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS employment_status TEXT;       -- 'employed', 'unemployed', 'student', 'nysc', 'siwes'
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS open_to_relocation BOOLEAN DEFAULT false;
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS work_type_pref TEXT;          -- 'onshore', 'offshore', 'both'
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS highest_qualification TEXT;   -- 'OND', 'HND', 'BSc', 'MSc', 'PhD'
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS institution TEXT;
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS graduation_year TEXT;
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS job_hunting_status TEXT;      -- 'active', 'passive', 'browsing'
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS salary_expectation TEXT;
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS state_of_origin TEXT;
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS gender TEXT;

-- ------------------------------------------------------------
-- 3. RLS — replace permissive anon read with auth-based access
-- ------------------------------------------------------------

-- Drop the old wide-open anon select policy (added in schema_v7)
DROP POLICY IF EXISTS "allow_anon_select" ON subscribers;

-- Authenticated users can only read their own subscriber row
DROP POLICY IF EXISTS "auth_select_own" ON subscribers;
CREATE POLICY "auth_select_own" ON subscribers
  FOR SELECT TO authenticated USING (auth.uid() = user_id);

-- Authenticated users can only update their own subscriber row
DROP POLICY IF EXISTS "auth_update_own" ON subscribers;
CREATE POLICY "auth_update_own" ON subscribers
  FOR UPDATE TO authenticated USING (auth.uid() = user_id);

-- Note: allow_anon_insert (from schema_v6) stays in place — needed for the
-- Paystack payment flow which inserts the subscriber row before auth is set up.

-- ------------------------------------------------------------
-- 4. RPC: claim_subscriber
-- Links an existing subscriber row to a newly-created auth user.
-- Called after supabase.auth.signUp() to connect any subscriber row
-- that was created earlier (e.g. via Paystack before account creation).
-- Uses SECURITY DEFINER so it can read auth.users.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION claim_subscriber(p_user_id UUID)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    user_email TEXT;
    updated_count INT;
BEGIN
    -- Look up the email for this auth user
    SELECT email INTO user_email
    FROM auth.users
    WHERE id = p_user_id;

    IF user_email IS NULL THEN
        RETURN json_build_object('success', false, 'error', 'User not found');
    END IF;

    -- Link any subscriber row with matching email that isn't yet linked
    UPDATE subscribers
    SET user_id = p_user_id
    WHERE lower(email) = lower(user_email)
      AND user_id IS NULL;

    GET DIAGNOSTICS updated_count = ROW_COUNT;

    RETURN json_build_object('success', true, 'linked', updated_count > 0);
END;
$$;

-- Both anon (during signup flow before email confirmation) and authenticated can call this
GRANT EXECUTE ON FUNCTION claim_subscriber TO anon, authenticated;
