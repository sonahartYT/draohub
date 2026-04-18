-- Add subscription tracking columns to subscribers
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'free';
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS paystack_reference TEXT;
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS paystack_subscription_code TEXT;
