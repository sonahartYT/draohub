-- DracoHub schema v13 — extended profile fields for AI matching
ALTER TABLE subscribers
  ADD COLUMN IF NOT EXISTS nysc_status         text,
  ADD COLUMN IF NOT EXISTS sector_pref         text,
  ADD COLUMN IF NOT EXISTS company_type_pref   text,
  ADD COLUMN IF NOT EXISTS contract_type_pref  text,
  ADD COLUMN IF NOT EXISTS notice_period       text,
  ADD COLUMN IF NOT EXISTS certifications      text,
  ADD COLUMN IF NOT EXISTS willing_abroad      boolean DEFAULT false;
