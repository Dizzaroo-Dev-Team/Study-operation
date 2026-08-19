-- SQL script to add field_mappings column to study_templates table
-- Run this directly in your PostgreSQL database if the Python migration script has connection issues

-- Check if column exists and add if not
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'study_templates' 
        AND column_name = 'field_mappings'
    ) THEN
        ALTER TABLE study_templates
        ADD COLUMN field_mappings JSON;
        
        RAISE NOTICE 'Column field_mappings added successfully.';
    ELSE
        RAISE NOTICE 'Column field_mappings already exists. Skipping.';
    END IF;
END $$;
