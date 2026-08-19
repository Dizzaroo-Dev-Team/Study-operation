-- Adds the structured links the in-app site-creation form needs:
--   * facility_external_id  — UUID of the row in the external Azure facilities DB
--   * principal_investigator_id — FK to users.id (Postgres) for the PI
-- Both nullable so existing site rows survive the migration unchanged.

ALTER TABLE sites
    ADD COLUMN IF NOT EXISTS facility_external_id UUID NULL,
    ADD COLUMN IF NOT EXISTS principal_investigator_id UUID NULL;

-- FK to users on the PI column (deferred so existing rows with NULL PI are fine).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_sites_principal_investigator_id'
    ) THEN
        ALTER TABLE sites
            ADD CONSTRAINT fk_sites_principal_investigator_id
            FOREIGN KEY (principal_investigator_id)
            REFERENCES users(id)
            ON DELETE SET NULL;
    END IF;
END $$;

-- Lookup index for "find sites at this facility".
CREATE INDEX IF NOT EXISTS ix_sites_facility_external_id
    ON sites (facility_external_id);

CREATE INDEX IF NOT EXISTS ix_sites_principal_investigator_id
    ON sites (principal_investigator_id);
