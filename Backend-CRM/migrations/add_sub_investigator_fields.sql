-- Add Sub Investigator fields to site profile
ALTER TABLE site_profiles
ADD COLUMN IF NOT EXISTS sub_investigator_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS sub_investigator_email VARCHAR(255),
ADD COLUMN IF NOT EXISTS sub_investigator_phone VARCHAR(50),
ADD COLUMN IF NOT EXISTS sub_investigator_designation VARCHAR(255),
ADD COLUMN IF NOT EXISTS sub_investigator_department VARCHAR(255);
