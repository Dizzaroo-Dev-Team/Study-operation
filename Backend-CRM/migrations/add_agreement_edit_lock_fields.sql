-- Migration: Add lightweight edit lock fields to agreements table
-- Purpose: Support single-editor locking for agreement documents
-- Safe to run multiple times (idempotent)

-- Step 1: Add editing_user_id column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'agreements'
          AND column_name = 'editing_user_id'
    ) THEN
        ALTER TABLE agreements
        ADD COLUMN editing_user_id VARCHAR(255);

        RAISE NOTICE 'Added editing_user_id column to agreements';
    ELSE
        RAISE NOTICE 'editing_user_id column already exists on agreements';
    END IF;
END $$;

-- Step 2: Add editing_started_at column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'agreements'
          AND column_name = 'editing_started_at'
    ) THEN
        ALTER TABLE agreements
        ADD COLUMN editing_started_at TIMESTAMPTZ;

        RAISE NOTICE 'Added editing_started_at column to agreements';
    ELSE
        RAISE NOTICE 'editing_started_at column already exists on agreements';
    END IF;
END $$;

-- Optional: small index to help lookups by lock holder
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'agreements'
          AND indexname = 'ix_agreements_editing_user_id'
    ) THEN
        CREATE INDEX ix_agreements_editing_user_id
        ON agreements (editing_user_id);

        RAISE NOTICE 'Created index ix_agreements_editing_user_id on agreements';
    ELSE
        RAISE NOTICE 'Index ix_agreements_editing_user_id already exists on agreements';
    END IF;
END $$;

