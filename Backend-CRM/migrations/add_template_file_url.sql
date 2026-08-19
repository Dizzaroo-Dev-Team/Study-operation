-- Add template_file_url column to study_templates table
-- Safe to run multiple times (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'study_templates'
          AND column_name = 'template_file_url'
    ) THEN
        ALTER TABLE study_templates ADD COLUMN template_file_url TEXT;
        COMMENT ON COLUMN study_templates.template_file_url
            IS 'Azure Blob Storage URL for template file';
        RAISE NOTICE 'Added template_file_url column to study_templates';
    ELSE
        RAISE NOTICE 'template_file_url column already exists';
    END IF;
END $$;
