-- Migration: Create agreement_review_documents table
-- Purpose: Store review copies of agreement documents for external site editing
-- Safe to run multiple times (idempotent)

-- Create agreement_review_documents table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'agreement_review_documents'
    ) THEN
        CREATE TABLE agreement_review_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agreement_id UUID NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
            review_token_id UUID NOT NULL REFERENCES agreement_review_tokens(id) ON DELETE CASCADE,
            base_version_id UUID NOT NULL REFERENCES agreement_documents(id) ON DELETE CASCADE,
            review_file_path TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            is_submitted VARCHAR(10) NOT NULL DEFAULT 'false',
            submitted_at TIMESTAMPTZ,
            CONSTRAINT chk_agreement_review_documents_is_submitted CHECK (is_submitted IN ('true', 'false'))
        );

        CREATE INDEX idx_agreement_review_documents_agreement_id ON agreement_review_documents(agreement_id);
        CREATE INDEX idx_agreement_review_documents_review_token_id ON agreement_review_documents(review_token_id);
        CREATE INDEX idx_agreement_review_documents_base_version_id ON agreement_review_documents(base_version_id);
        CREATE INDEX idx_agreement_review_documents_is_submitted ON agreement_review_documents(is_submitted);
        CREATE INDEX idx_agreement_review_documents_created_at ON agreement_review_documents(created_at);

        COMMENT ON TABLE agreement_review_documents IS 'Review copies of agreement documents for external site editing';

        RAISE NOTICE 'Created agreement_review_documents table';
    ELSE
        RAISE NOTICE 'agreement_review_documents table already exists';
    END IF;
END $$;
