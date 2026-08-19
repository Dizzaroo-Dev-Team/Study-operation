-- ============================================================
-- A1: Refactor trial_factor_configuration
-- ============================================================

-- Step 1: Add new columns
ALTER TABLE trial_factor_configuration
    ADD COLUMN IF NOT EXISTS factor_type_id UUID
        REFERENCES conversion_factor_type(id) ON DELETE CASCADE;

ALTER TABLE trial_factor_configuration
    ADD COLUMN IF NOT EXISTS application_sequence INT NOT NULL DEFAULT 0;

ALTER TABLE trial_factor_configuration
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- Step 2: Backfill factor_type_id from existing conversion_factor_id
UPDATE trial_factor_configuration tfc
SET    factor_type_id = cf.factor_type_id
FROM   conversion_factor cf
WHERE  tfc.conversion_factor_id = cf.id
  AND  tfc.factor_type_id IS NULL;

-- Step 3: Backfill application_sequence from sequence_override / factor.sequence_order
UPDATE trial_factor_configuration tfc
SET    application_sequence = COALESCE(tfc.sequence_override, cf.sequence_order, 0)
FROM   conversion_factor cf
WHERE  tfc.conversion_factor_id = cf.id
  AND  tfc.application_sequence = 0;

-- Step 4: Backfill is_active from enabled
UPDATE trial_factor_configuration
SET    is_active = COALESCE(enabled, TRUE)
WHERE  is_active = TRUE;

-- Step 5: De-duplicate — keep lowest application_sequence per (trial_id, factor_type_id)
DELETE FROM trial_factor_configuration
WHERE id NOT IN (
    SELECT DISTINCT ON (trial_id, factor_type_id) id
    FROM   trial_factor_configuration
    WHERE  factor_type_id IS NOT NULL
    ORDER  BY trial_id, factor_type_id, application_sequence, id
);

-- Step 6: Remove rows where factor_type_id could not be resolved
DELETE FROM trial_factor_configuration WHERE factor_type_id IS NULL;

-- Step 7: Drop old columns (if they exist)
ALTER TABLE trial_factor_configuration
    DROP COLUMN IF EXISTS conversion_factor_id;

ALTER TABLE trial_factor_configuration
    DROP COLUMN IF EXISTS enabled;

ALTER TABLE trial_factor_configuration
    DROP COLUMN IF EXISTS sequence_override;

-- Step 8: Add unique constraint and index
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_trial_factor_config_type'
    ) THEN
        ALTER TABLE trial_factor_configuration
            ADD CONSTRAINT uq_trial_factor_config_type
            UNIQUE (trial_id, factor_type_id);
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS ix_trial_factor_config_trial_type
    ON trial_factor_configuration (trial_id, factor_type_id);

-- ============================================================
-- A2: Drop legacy scope columns from conversion_factor
-- ============================================================

ALTER TABLE conversion_factor DROP COLUMN IF EXISTS scope_type;
ALTER TABLE conversion_factor DROP COLUMN IF EXISTS scope_value;
ALTER TABLE conversion_factor ADD COLUMN IF NOT EXISTS justification TEXT;
ALTER TABLE conversion_factor ADD COLUMN IF NOT EXISTS scope_level VARCHAR(32);
ALTER TABLE conversion_factor ADD COLUMN IF NOT EXISTS scope_element_id UUID REFERENCES cost_element(id) ON DELETE SET NULL;
ALTER TABLE conversion_factor ADD COLUMN IF NOT EXISTS scope_category VARCHAR(200);

-- ============================================================
-- A3: Refactor budget_line_item (dual-bool → is_excluded)
-- ============================================================

ALTER TABLE budget_line_item ADD COLUMN IF NOT EXISTS is_excluded BOOLEAN NOT NULL DEFAULT FALSE;

-- Backfill: if excluded=true OR included=false → is_excluded=true
UPDATE budget_line_item
SET    is_excluded = TRUE
WHERE  (excluded IS TRUE OR included IS FALSE)
  AND  is_excluded = FALSE;

ALTER TABLE budget_line_item ADD COLUMN IF NOT EXISTS default_quantity NUMERIC(10,2);
ALTER TABLE budget_line_item DROP COLUMN IF EXISTS excluded;
ALTER TABLE budget_line_item DROP COLUMN IF EXISTS included;
ALTER TABLE budget_line_item DROP COLUMN IF EXISTS parent_line_item_id;

-- ============================================================
-- A5: Add trial_id to visit_schedule (trial-scoped visits)
-- ============================================================

ALTER TABLE visit_schedule
    ADD COLUMN IF NOT EXISTS trial_id UUID REFERENCES studies(id) ON DELETE CASCADE;

-- Backfill trial_id from the template's trial_id
UPDATE visit_schedule vs
SET    trial_id = bt.trial_id
FROM   budget_template bt
WHERE  vs.budget_template_id = bt.id
  AND  vs.trial_id IS NULL;

-- Migrate widget_schedule_visit rows into visit_schedule (if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'widget_schedule_visit') THEN
        INSERT INTO visit_schedule (trial_id, visit_code, visit_name, visit_type, target_day, visit_order, is_active)
        SELECT DISTINCT
            wsv.trial_id,
            'wv:' || wsv.id::text,
            wsv.visit_name,
            wsv.visit_type,
            wsv.target_day,
            wsv.visit_order,
            wsv.is_active
        FROM widget_schedule_visit wsv
        WHERE wsv.trial_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM visit_schedule vs2
              WHERE  vs2.trial_id   = wsv.trial_id
                AND  vs2.visit_code = 'wv:' || wsv.id::text
          );
    END IF;
END$$;

ALTER TABLE visit_schedule ADD COLUMN IF NOT EXISTS window_before INT;
ALTER TABLE visit_schedule ADD COLUMN IF NOT EXISTS window_after  INT;
ALTER TABLE visit_schedule ADD COLUMN IF NOT EXISTS country_code  CHAR(3);
ALTER TABLE visit_schedule ADD COLUMN IF NOT EXISTS is_active     BOOLEAN NOT NULL DEFAULT TRUE;

-- ============================================================
-- A6: Add remaining guide columns
-- ============================================================

ALTER TABLE budget_template
    ADD COLUMN IF NOT EXISTS locked_exchange_rate_date DATE;

ALTER TABLE site_budgeting_audit_log
    ADD COLUMN IF NOT EXISTS user_role VARCHAR(50);

ALTER TABLE budget_milestone
    ADD COLUMN IF NOT EXISTS element_id UUID REFERENCES cost_element(id) ON DELETE SET NULL;

-- Rename amount → unit_cost (idempotent)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name = 'budget_milestone' AND column_name = 'amount'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name = 'budget_milestone' AND column_name = 'unit_cost'
    ) THEN
        ALTER TABLE budget_milestone RENAME COLUMN amount TO unit_cost;
    END IF;
END$$;
