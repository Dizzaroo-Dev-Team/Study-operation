-- Migration: Create agreement_signers table for sequential multi-signer flow
-- Purpose: Track ordered list of signers per agreement (sponsor → site → witness etc.)
-- Safe to run multiple times (idempotent)

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'agreement_signers'
    ) THEN
        CREATE TABLE agreement_signers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agreement_id UUID NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
            -- role label matching _SIGNATURE_PLACEHOLDERS_BY_ROLE keys:
            -- e.g. 'sponsor', 'site', 'witness', 'pi', 'legal', 'reviewer', 'investigator'
            role VARCHAR(50) NOT NULL,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            -- 1-based position in the sequential signing order
            sign_order INTEGER NOT NULL,
            -- Which DOCX placeholder this signer maps to (e.g. 'SITE_SIGNATURE').
            -- Resolved at agreement-create time from the template scan + role lookup;
            -- null when the placeholder will be injected later.
            placeholder_name VARCHAR(100),
            -- 'pending' (not yet their turn), 'invited' (OTP sent),
            -- 'signed' (signature stamped), 'declined' (signer rejected)
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            signed_at TIMESTAMPTZ,
            invited_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_agreement_signers_status
                CHECK (status IN ('pending', 'invited', 'signed', 'declined')),
            -- One signer per (agreement, sign_order); no duplicate positions.
            CONSTRAINT uq_agreement_signers_agreement_order
                UNIQUE (agreement_id, sign_order),
            -- One role per agreement (user chose "one person per role" model).
            CONSTRAINT uq_agreement_signers_agreement_role
                UNIQUE (agreement_id, role)
        );

        CREATE INDEX idx_agreement_signers_agreement_id ON agreement_signers(agreement_id);
        CREATE INDEX idx_agreement_signers_status ON agreement_signers(status);
        CREATE INDEX idx_agreement_signers_email ON agreement_signers(email);

        COMMENT ON TABLE agreement_signers IS
            'Per-agreement ordered signer list for sequential multi-signer e-sign flow';

        RAISE NOTICE 'Created agreement_signers table';
    ELSE
        RAISE NOTICE 'agreement_signers table already exists';
    END IF;
END $$;
