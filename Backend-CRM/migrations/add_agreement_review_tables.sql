-- Migration: Create agreement_review_tokens and agreement_changes tables
-- Purpose: Support agreement review workflow with secure tokens and change tracking
-- Safe to run multiple times (idempotent)

-- Step 1: Create agreement_review_tokens table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'agreement_review_tokens'
    ) THEN
        CREATE TABLE agreement_review_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agreement_id UUID NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
            token VARCHAR(255) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            created_by VARCHAR(255),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            used_at TIMESTAMPTZ,
            is_active VARCHAR(10) NOT NULL DEFAULT 'true',
            CONSTRAINT chk_agreement_review_tokens_is_active CHECK (is_active IN ('true', 'false'))
        );

        CREATE INDEX idx_agreement_review_tokens_token ON agreement_review_tokens(token);
        CREATE INDEX idx_agreement_review_tokens_agreement_id ON agreement_review_tokens(agreement_id);
        CREATE INDEX idx_agreement_review_tokens_expires_at ON agreement_review_tokens(expires_at);

        COMMENT ON TABLE agreement_review_tokens IS 'Secure tokens for external site review access to agreements';

        RAISE NOTICE 'Created agreement_review_tokens table';
    ELSE
        RAISE NOTICE 'agreement_review_tokens table already exists';
    END IF;
END $$;

-- Step 2: Create agreement_changes table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'agreement_changes'
    ) THEN
        CREATE TABLE agreement_changes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agreement_id UUID NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
            document_version_id UUID NOT NULL REFERENCES agreement_documents(id) ON DELETE CASCADE,
            previous_version_id UUID REFERENCES agreement_documents(id) ON DELETE SET NULL,
            change_type VARCHAR(50) NOT NULL,
            section_reference VARCHAR(500),
            old_text TEXT,
            new_text TEXT,
            paragraph_index INTEGER,
            table_index INTEGER,
            row_index INTEGER,
            cell_index INTEGER,
            created_by VARCHAR(255),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            is_external_change VARCHAR(10) NOT NULL DEFAULT 'false',
            is_accepted VARCHAR(10) NOT NULL DEFAULT 'false',
            accepted_by VARCHAR(255),
            accepted_at TIMESTAMPTZ,
            CONSTRAINT chk_agreement_changes_change_type CHECK (change_type IN ('ADDED', 'DELETED', 'MODIFIED')),
            CONSTRAINT chk_agreement_changes_is_external_change CHECK (is_external_change IN ('true', 'false')),
            CONSTRAINT chk_agreement_changes_is_accepted CHECK (is_accepted IN ('true', 'false'))
        );

        CREATE INDEX idx_agreement_changes_agreement_id ON agreement_changes(agreement_id);
        CREATE INDEX idx_agreement_changes_document_version_id ON agreement_changes(document_version_id);
        CREATE INDEX idx_agreement_changes_previous_version_id ON agreement_changes(previous_version_id);
        CREATE INDEX idx_agreement_changes_is_accepted ON agreement_changes(is_accepted);
        CREATE INDEX idx_agreement_changes_is_external_change ON agreement_changes(is_external_change);
        CREATE INDEX idx_agreement_changes_created_at ON agreement_changes(created_at);

        COMMENT ON TABLE agreement_changes IS 'Track document changes during agreement review and negotiation';

        RAISE NOTICE 'Created agreement_changes table';
    ELSE
        RAISE NOTICE 'agreement_changes table already exists';
    END IF;
END $$;
