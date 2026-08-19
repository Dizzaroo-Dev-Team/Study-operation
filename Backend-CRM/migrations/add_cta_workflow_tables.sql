-- =====================================================================
-- Migration: CTA workflow support
--   1. agreement_negotiation_rounds   (Sprint 2: track sponsor↔site rounds)
--   2. agreements.amendment_of_id     (Sprint 4: link amendments to parent)
-- Idempotent: safe to run multiple times.
-- =====================================================================

-- ── Sprint 2: agreement_negotiation_rounds ──────────────────────────────
CREATE TABLE IF NOT EXISTS agreement_negotiation_rounds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agreement_id UUID NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    -- Who started this round: 'sponsor' (sent the doc out) or 'site' (came back).
    initiated_by VARCHAR(20) NOT NULL,
    -- Link to the review document used for this round (the working copy the
    -- site edits with OnlyOffice). Nullable for the sponsor-side review round
    -- where the site has nothing to edit.
    review_document_id UUID REFERENCES agreement_review_documents(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    -- 'in_progress' (token live), 'submitted' (other side returned the doc),
    -- 'cancelled' (sponsor finalized before this round completed).
    status VARCHAR(20) NOT NULL DEFAULT 'in_progress',
    notes TEXT,
    CONSTRAINT chk_agreement_negotiation_rounds_initiated_by
        CHECK (initiated_by IN ('sponsor', 'site')),
    CONSTRAINT chk_agreement_negotiation_rounds_status
        CHECK (status IN ('in_progress', 'submitted', 'cancelled')),
    CONSTRAINT uq_agreement_negotiation_rounds_agreement_round
        UNIQUE (agreement_id, round_number)
);

CREATE INDEX IF NOT EXISTS idx_agreement_negotiation_rounds_agreement_id
    ON agreement_negotiation_rounds(agreement_id);
CREATE INDEX IF NOT EXISTS idx_agreement_negotiation_rounds_status
    ON agreement_negotiation_rounds(status);

COMMENT ON TABLE agreement_negotiation_rounds IS
    'Per-CTA-agreement back-and-forth negotiation rounds between sponsor and site';

-- ── Sprint 4: amendments link ───────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'agreements' AND column_name = 'amendment_of_id'
    ) THEN
        ALTER TABLE agreements
          ADD COLUMN amendment_of_id UUID REFERENCES agreements(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added agreements.amendment_of_id';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_agreements_amendment_of_id
    ON agreements(amendment_of_id);
