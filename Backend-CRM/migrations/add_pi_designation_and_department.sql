-- Add Designation and Department fields to PI in site profile
ALTER TABLE site_profiles
ADD COLUMN IF NOT EXISTS pi_designation VARCHAR(255),
ADD COLUMN IF NOT EXISTS pi_department VARCHAR(255);
