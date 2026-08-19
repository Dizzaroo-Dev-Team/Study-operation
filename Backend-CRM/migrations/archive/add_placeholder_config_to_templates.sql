-- SQL script to add placeholder_config column to study_templates table
-- Run this directly in your PostgreSQL database if the Python migration script has connection issues

-- Check if column already exists, and add it if it doesn't
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'study_templates' 
        AND column_name = 'placeholder_config'
    ) THEN
        ALTER TABLE study_templates
        ADD COLUMN placeholder_config JSON;
        
        RAISE NOTICE 'Column placeholder_config added successfully.';
    ELSE
        RAISE NOTICE 'Column placeholder_config already exists.';
    END IF;
END $$;
