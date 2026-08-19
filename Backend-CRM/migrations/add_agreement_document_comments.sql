-- =============================================================================
-- Migration: agreement_document_comments
-- Purpose  : Store OnlyOffice comments extracted from review copies of
--            agreement documents.  Enables the full comment → reply → status
--            workflow without touching the main agreement_documents table.
-- Safe     : Idempotent – can be re-run without side-effects.
-- =============================================================================

-- Step 1 – Create enum type (if it doesn't exist)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'commentstatus'
    ) THEN
        CREATE TYPE commentstatus AS ENUM ('pending', 'accepted', 'rejected', 'modified');
        RAISE NOTICE 'Created enum type commentstatus';
    ELSE
        RAISE NOTICE 'Enum type commentstatus already exists';
    END IF;
END $$;

-- Step 2 – Create the table
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   information_schema.tables
        WHERE  table_schema = 'public'
          AND  table_name   = 'agreement_document_comments'
    ) THEN
        CREATE TABLE agreement_document_comments (
            -- Primary key
            id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

            -- OnlyOffice / OOXML comment id (e.g. "1", "2", "3")
            -- Used together with review_document_id for upsert de-duplication.
            comment_id          VARCHAR(50) NOT NULL,

            -- FK to the review copy of the document where the comment lives.
            -- NULL for internally-created reply rows (no DOCX backing).
            review_document_id  UUID        REFERENCES agreement_review_documents(id) ON DELETE CASCADE,

            -- Denormalised FK to the parent agreement for efficient per-agreement queries.
            agreement_id        UUID        NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,

            -- Author as stored in the DOCX (usually the reviewer's display name / email).
            author_email        VARCHAR(255) NOT NULL DEFAULT '',

            -- Full comment text body.
            comment_text        TEXT        NOT NULL DEFAULT '',

            -- The document text the comment is anchored to (extracted from commentRangeStart/End).
            referenced_text     TEXT,

            -- ISO 8601 date/time stored inside the DOCX XML.
            oo_date             VARCHAR(50),

            -- Resolution status set by the internal team.
            -- Stored as VARCHAR for maximum Neon / Postgres compatibility.
            status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                                    CONSTRAINT chk_comment_status
                                        CHECK (status IN ('pending', 'accepted', 'rejected', 'modified')),

            -- Self-referential FK: replies point at the top-level comment's UUID PK.
            parent_comment_id   UUID        REFERENCES agreement_document_comments(id) ON DELETE SET NULL,

            -- 'true' if this row was created by an internal CRM user (reply or override).
            is_internal_reply   VARCHAR(10) NOT NULL DEFAULT 'false'
                                    CONSTRAINT chk_internal_reply
                                        CHECK (is_internal_reply IN ('true', 'false')),

            -- Audit timestamps
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW(),

            -- Prevent duplicate rows for the same OnlyOffice comment id inside one review doc.
            CONSTRAINT uq_agreement_doc_comment_oo_id
                UNIQUE (comment_id, review_document_id)
        );

        -- Indexes for typical query patterns
        CREATE INDEX idx_adc_agreement_id       ON agreement_document_comments(agreement_id);
        CREATE INDEX idx_adc_review_document_id ON agreement_document_comments(review_document_id);
        CREATE INDEX idx_adc_parent_comment_id  ON agreement_document_comments(parent_comment_id);
        CREATE INDEX idx_adc_status             ON agreement_document_comments(status);
        CREATE INDEX idx_adc_created_at         ON agreement_document_comments(created_at);

        COMMENT ON TABLE agreement_document_comments IS
            'OnlyOffice review comments extracted from agreement review documents. '
            'Supports full comment → reply → status (accepted/rejected/modified) workflow.';

        RAISE NOTICE 'Created table agreement_document_comments';
    ELSE
        RAISE NOTICE 'Table agreement_document_comments already exists – skipping';
    END IF;
END $$;
