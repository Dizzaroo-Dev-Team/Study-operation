-- Add document_file_url column to agreement_documents table
-- This column stores the Azure Blob Storage URL when documents are stored in Azure.
-- When NULL, the document is stored locally at document_file_path.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'agreement_documents'
          AND column_name = 'document_file_url'
    ) THEN
        ALTER TABLE agreement_documents ADD COLUMN document_file_url TEXT;
    END IF;
END $$;
