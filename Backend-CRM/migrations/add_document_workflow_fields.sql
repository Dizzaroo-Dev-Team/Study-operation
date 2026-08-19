-- Migration: Add document workflow fields to site_documents table
-- This adds support for Sponsor Documents and Site Documents workflow with review status.
-- Date: 2024

-- Step 1: Create document_type enum if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'document_type') THEN
        CREATE TYPE document_type AS ENUM ('sponsor', 'site');
        RAISE NOTICE 'Created document_type enum';
    ELSE
        RAISE NOTICE 'document_type enum already exists';
    END IF;
END $$;

-- Step 2: Create review_status enum if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'review_status') THEN
        CREATE TYPE review_status AS ENUM ('pending', 'approved', 'rejected');
        RAISE NOTICE 'Created review_status enum';
    ELSE
        RAISE NOTICE 'review_status enum already exists';
    END IF;
END $$;

-- Step 3: Add document_type column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'site_documents' 
        AND column_name = 'document_type'
    ) THEN
        ALTER TABLE site_documents 
        ADD COLUMN document_type document_type DEFAULT 'site';
        
        -- Update existing records to have 'site' as default
        UPDATE site_documents SET document_type = 'site' WHERE document_type IS NULL;
        
        RAISE NOTICE 'Added document_type column to site_documents';
    ELSE
        RAISE NOTICE 'document_type column already exists in site_documents';
    END IF;
END $$;

-- Step 4: Add review_status column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'site_documents' 
        AND column_name = 'review_status'
    ) THEN
        ALTER TABLE site_documents 
        ADD COLUMN review_status review_status DEFAULT 'pending';
        
        -- Update existing records: set 'pending' for site documents, NULL for sponsor documents
        -- Since we don't know which existing docs are sponsor vs site, we'll set all to pending
        -- This is safe as sponsor documents don't need review anyway
        UPDATE site_documents SET review_status = 'pending' WHERE review_status IS NULL;
        
        RAISE NOTICE 'Added review_status column to site_documents';
    ELSE
        RAISE NOTICE 'review_status column already exists in site_documents';
    END IF;
END $$;

-- Step 5: Add tmf_filed column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'site_documents' 
        AND column_name = 'tmf_filed'
    ) THEN
        ALTER TABLE site_documents 
        ADD COLUMN tmf_filed VARCHAR(10) DEFAULT 'false' NOT NULL;
        
        -- Update existing records to have 'false' as default
        UPDATE site_documents SET tmf_filed = 'false' WHERE tmf_filed IS NULL;
        
        RAISE NOTICE 'Added tmf_filed column to site_documents';
    ELSE
        RAISE NOTICE 'tmf_filed column already exists in site_documents';
    END IF;
END $$;

-- Step 6: Create indexes for better query performance
DO $$
BEGIN
    -- Index on document_type
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'site_documents' 
        AND indexname = 'ix_site_documents_document_type'
    ) THEN
        CREATE INDEX ix_site_documents_document_type ON site_documents (document_type);
        RAISE NOTICE 'Created index on document_type';
    ELSE
        RAISE NOTICE 'Index on document_type already exists';
    END IF;
    
    -- Index on review_status
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'site_documents' 
        AND indexname = 'ix_site_documents_review_status'
    ) THEN
        CREATE INDEX ix_site_documents_review_status ON site_documents (review_status);
        RAISE NOTICE 'Created index on review_status';
    ELSE
        RAISE NOTICE 'Index on review_status already exists';
    END IF;
END $$;

-- Summary
SELECT 
    'Migration completed. New columns added to site_documents:' as message,
    CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'site_documents' AND column_name = 'document_type') THEN '✓ document_type' ELSE '✗ document_type' END,
    CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'site_documents' AND column_name = 'review_status') THEN '✓ review_status' ELSE '✗ review_status' END,
    CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'site_documents' AND column_name = 'tmf_filed') THEN '✓ tmf_filed' ELSE '✗ tmf_filed' END;
