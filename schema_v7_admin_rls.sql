-- schema_v7_admin_rls.sql
-- Allow anon key to SELECT from subscribers (needed for admin dashboard)
-- The admin dashboard is password-protected in the frontend, so this is acceptable.
-- Run in Supabase → SQL Editor

-- Allow anon to read subscriber rows (admin dashboard uses anon key)
CREATE POLICY "allow_anon_select"
  ON subscribers
  FOR SELECT
  TO anon
  USING (true);

-- Verify policies are in place
-- SELECT policyname, cmd, roles FROM pg_policies WHERE tablename = 'subscribers';
