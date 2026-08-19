-- Drop study_id and enforce one-IRB-per-site
-- Keeps the oldest mapping per site and removes later updates.

-- 1) De-duplicate: keep oldest row per site_id (delete latest updated rows)
WITH ranked AS (
    SELECT
        id,
        site_id,
        ROW_NUMBER() OVER (
            PARTITION BY site_id
            ORDER BY updated_at ASC NULLS FIRST, id ASC
        ) AS rn
    FROM site_irb_mapping
)
DELETE FROM site_irb_mapping
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

-- 2) Drop old constraints and column
ALTER TABLE site_irb_mapping
    DROP CONSTRAINT IF EXISTS uq_site_irb_mapping_site_study;

ALTER TABLE site_irb_mapping
    DROP CONSTRAINT IF EXISTS site_irb_mapping_study_id_fkey;

DROP INDEX IF EXISTS ix_site_irb_mapping_study_id;

ALTER TABLE site_irb_mapping
    DROP COLUMN IF EXISTS study_id;

-- 3) Enforce one-IRB-per-site
ALTER TABLE site_irb_mapping
    ADD CONSTRAINT uq_site_irb_mapping_site UNIQUE (site_id);
