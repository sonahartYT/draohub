-- schema_v8_background.sql
-- Add background column to subscribers table
-- Run in Supabase → SQL Editor

ALTER TABLE subscribers
  ADD COLUMN IF NOT EXISTS background TEXT;
