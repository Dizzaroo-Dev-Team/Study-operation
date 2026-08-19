-- Migration: Add study_site_id column to site_workflow_steps table
-- This allows study-specific workflow steps (Site Identification, CDA, Feasibility)
-- to be scoped to a (study + site) combination instead of just site_id.
-- Date: 2024

-- Step 1: Make site_id nullable (since study-specific steps use study_site_id instead)
DO $$
BEGIN
    -- Check if site_id is currently NOT NULL
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'site_workflow_steps' 
        AND column_name = 'site_id'
        AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE site_workflow_steps 
        ALTER COLUMN site_id DROP NOT NULL;
        
        RAISE NOTICE 'Made site_id nullable in site_workflow_steps';
    ELSE
        RAISE NOTICE 'site_id is already nullable in site_workflow_steps';
    END IF;
END $$;

-- Step 2: Add study_site_id column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'site_workflow_steps' 
        AND column_name = 'study_site_id'
    ) THEN
        -- First, ensure study_sites table exists
        IF EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'study_sites'
        ) THEN
            ALTER TABLE site_workflow_steps 
            ADD COLUMN study_site_id UUID REFERENCES study_sites(id) ON DELETE CASCADE;
            
            RAISE NOTICE 'Added study_site_id column to site_workflow_steps';
        ELSE
            RAISE WARNING 'study_sites table does not exist. Please create it first.';
        END IF;
    ELSE
        RAISE NOTICE 'study_site_id column already exists in site_workflow_steps';
    END IF;
END $$;

-- Step 3: Create index on study_site_id for better query performance
CREATE INDEX IF NOT EXISTS ix_site_workflow_steps_study_site_id 
    ON site_workflow_steps (study_site_id);

-- Step 4: Update unique constraint to allow both site_id and study_site_id patterns
-- Drop the old unique constraint if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_site_workflow_step'
    ) THEN
        ALTER TABLE site_workflow_steps 
        DROP CONSTRAINT uq_site_workflow_step;
        
        RAISE NOTICE 'Dropped old unique constraint uq_site_workflow_step';
    END IF;
END $$;

-- Add new unique constraint that handles both site_id and study_site_id patterns
-- For study-specific steps: unique on (study_site_id, step_name)
-- For non-study-specific steps: unique on (site_id, step_name)
-- Note: PostgreSQL doesn't support conditional unique constraints directly,
-- so we'll use a partial unique index approach

-- Unique constraint for study-specific steps (when study_site_id is NOT NULL)
CREATE UNIQUE INDEX IF NOT EXISTS uq_site_workflow_steps_study_site_step 
    ON site_workflow_steps (study_site_id, step_name) 
    WHERE study_site_id IS NOT NULL;

-- Unique constraint for non-study-specific steps (when site_id is NOT NULL and study_site_id IS NULL)
CREATE UNIQUE INDEX IF NOT EXISTS uq_site_workflow_steps_site_step 
    ON site_workflow_steps (site_id, step_name) 
    WHERE site_id IS NOT NULL AND study_site_id IS NULL;

-- Step 5: Add a check constraint to ensure at least one of site_id or study_site_id is set
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'ck_site_workflow_steps_has_site_reference'
    ) THEN
        ALTER TABLE site_workflow_steps 
        ADD CONSTRAINT ck_site_workflow_steps_has_site_reference 
        CHECK (site_id IS NOT NULL OR study_site_id IS NOT NULL);
        
        RAISE NOTICE 'Added check constraint to ensure at least one site reference exists';
    ELSE
        RAISE NOTICE 'Check constraint already exists';
    END IF;
END $$;

-- Verification query (run this to check the migration)
-- SELECT 
--     column_name, 
--     data_type, 
--     is_nullable,
--     column_default
-- FROM information_schema.columns 
-- WHERE table_name = 'site_workflow_steps' 
-- ORDER BY ordinal_position;
