-- Add Site Head contact fields to site profile
ALTER TABLE site_profiles
  ADD COLUMN IF NOT EXISTS site_head_name VARCHAR(255),
  ADD COLUMN IF NOT EXISTS site_head_email VARCHAR(255),
  ADD COLUMN IF NOT EXISTS site_head_phone VARCHAR(50);
