# Database Migration Instructions for Neon Database

## Summary

**No migrations are required for the recent CDA comment and OAuth token refresh changes.**

However, there is **one migration needed** for the `study_site_id` column that was added to support study-specific workflow steps.

## Recent Changes Analysis

### ✅ No Migration Needed

1. **CDA Comment Field**
   - Stored in the existing `step_data` JSONB column
   - No schema changes required
   - Already supported by the current table structure

2. **OAuth Token Refresh**
   - Handled entirely in application code and configuration
   - No database changes required
   - Tokens are stored in environment variables, not the database

### ⚠️ Migration Required

**Add `study_site_id` column to `site_workflow_steps` table**

This migration is needed to support study-specific workflow steps (Site Identification, CDA Execution, Feasibility) that are scoped to a (study + site) combination.

## Migration Steps

### Option 1: Run SQL Migration Script (Recommended)

1. **Connect to your Neon database** using your preferred SQL client or the Neon console.

2. **Run the migration script:**
   ```bash
   # The migration file is located at:
   Backend-CRM/migrations/add_study_site_id_to_workflow_steps.sql
   ```

   Or copy and paste the SQL from the file directly into your Neon SQL editor.

3. **Verify the migration:**
   ```sql
   SELECT 
       column_name, 
       data_type, 
       is_nullable
   FROM information_schema.columns 
   WHERE table_name = 'site_workflow_steps' 
   ORDER BY ordinal_position;
   ```

   You should see:
   - `site_id` (nullable)
   - `study_site_id` (nullable, new column)

### Option 2: Manual Migration via Neon Console

1. Go to your Neon project dashboard
2. Open the SQL Editor
3. Run these commands one by one:

```sql
-- Make site_id nullable
ALTER TABLE site_workflow_steps 
ALTER COLUMN site_id DROP NOT NULL;

-- Add study_site_id column
ALTER TABLE site_workflow_steps 
ADD COLUMN study_site_id UUID REFERENCES study_sites(id) ON DELETE CASCADE;

-- Create index
CREATE INDEX IF NOT EXISTS ix_site_workflow_steps_study_site_id 
ON site_workflow_steps (study_site_id);

-- Drop old unique constraint
ALTER TABLE site_workflow_steps 
DROP CONSTRAINT IF EXISTS uq_site_workflow_step;

-- Add new unique indexes for both patterns
CREATE UNIQUE INDEX IF NOT EXISTS uq_site_workflow_steps_study_site_step 
ON site_workflow_steps (study_site_id, step_name) 
WHERE study_site_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_site_workflow_steps_site_step 
ON site_workflow_steps (site_id, step_name) 
WHERE site_id IS NOT NULL AND study_site_id IS NULL;

-- Add check constraint
ALTER TABLE site_workflow_steps 
ADD CONSTRAINT ck_site_workflow_steps_has_site_reference 
CHECK (site_id IS NOT NULL OR study_site_id IS NOT NULL);
```

## What This Migration Does

1. **Makes `site_id` nullable** - Allows study-specific steps to use `study_site_id` instead
2. **Adds `study_site_id` column** - Foreign key to `study_sites` table for study-specific workflow steps
3. **Creates indexes** - Improves query performance for both `site_id` and `study_site_id` lookups
4. **Updates unique constraints** - Ensures uniqueness for both patterns:
   - Study-specific steps: unique on `(study_site_id, step_name)`
   - Non-study-specific steps: unique on `(site_id, step_name)`
5. **Adds check constraint** - Ensures at least one of `site_id` or `study_site_id` is set

## Rollback (If Needed)

If you need to rollback this migration:

```sql
-- Remove check constraint
ALTER TABLE site_workflow_steps 
DROP CONSTRAINT IF EXISTS ck_site_workflow_steps_has_site_reference;

-- Drop unique indexes
DROP INDEX IF EXISTS uq_site_workflow_steps_study_site_step;
DROP INDEX IF EXISTS uq_site_workflow_steps_site_step;

-- Restore old unique constraint
ALTER TABLE site_workflow_steps 
ADD CONSTRAINT uq_site_workflow_step UNIQUE (site_id, step_name);

-- Drop index
DROP INDEX IF EXISTS ix_site_workflow_steps_study_site_id;

-- Remove study_site_id column
ALTER TABLE site_workflow_steps 
DROP COLUMN IF EXISTS study_site_id;

-- Make site_id NOT NULL again
ALTER TABLE site_workflow_steps 
ALTER COLUMN site_id SET NOT NULL;
```

## Verification

After running the migration, verify it worked:

```sql
-- Check columns exist
SELECT column_name, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'site_workflow_steps' 
AND column_name IN ('site_id', 'study_site_id');

-- Check indexes exist
SELECT indexname 
FROM pg_indexes 
WHERE tablename = 'site_workflow_steps' 
AND indexname LIKE '%study_site%';

-- Check constraints exist
SELECT constraint_name, constraint_type 
FROM information_schema.table_constraints 
WHERE table_name = 'site_workflow_steps';
```

## Notes

- This migration is **safe to run** on existing data
- Existing rows will have `site_id` set and `study_site_id` as NULL
- The application code already handles both patterns
- No data loss will occur
