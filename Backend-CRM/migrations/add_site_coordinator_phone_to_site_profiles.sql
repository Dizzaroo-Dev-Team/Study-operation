-- Add Site Coordinator Phone field to site profile
ALTER TABLE site_profiles
ADD COLUMN IF NOT EXISTS site_coordinator_phone VARCHAR(50);
