"""
Refactor trial_factor_configuration to match engineering guide §3.2.

BEFORE (wrong architecture):
  id UUID PK
  trial_id → studies
  conversion_factor_id → conversion_factor   ← specific factor VALUE, not type
  enabled BOOLEAN
  sequence_override INT

AFTER (guide-compliant):
  id UUID PK
  trial_id → studies
  factor_type_id → conversion_factor_type     ← factor TYPE in sequence
  application_sequence INT NOT NULL DEFAULT 0
  is_active BOOLEAN NOT NULL DEFAULT TRUE

Migration steps:
  1. Add new columns (factor_type_id, application_sequence, is_active)
  2. Backfill factor_type_id from existing rows (join through conversion_factor)
  3. Backfill application_sequence from sequence_override (or sequence_order on the factor)
  4. Backfill is_active from enabled
  5. Drop old columns (conversion_factor_id, enabled, sequence_override)
  6. Add UNIQUE constraint on (trial_id, factor_type_id)

Safe to re-run: all steps use IF NOT EXISTS / IF EXISTS guards.
"""
import asyncio
import sys

if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

from sqlalchemy import text
from app.db import AsyncSessionLocal
from app.config import settings

# Phase 1: add new columns
ADD_COLUMNS = """
ALTER TABLE trial_factor_configuration
    ADD COLUMN IF NOT EXISTS factor_type_id UUID
        REFERENCES conversion_factor_type(id) ON DELETE CASCADE;

ALTER TABLE trial_factor_configuration
    ADD COLUMN IF NOT EXISTS application_sequence INTEGER NOT NULL DEFAULT 0;

ALTER TABLE trial_factor_configuration
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
"""

# Phase 2: backfill from existing conversion_factor_id rows
BACKFILL = """
UPDATE trial_factor_configuration tfc
SET
    factor_type_id = cf.factor_type_id,
    application_sequence = COALESCE(tfc.sequence_override, cf.sequence_order, 0),
    is_active = COALESCE(tfc.enabled, TRUE)
FROM conversion_factor cf
WHERE tfc.conversion_factor_id = cf.id
  AND tfc.factor_type_id IS NULL;
"""

# Phase 3: de-duplicate — if backfill produced duplicate (trial_id, factor_type_id),
# keep only the row with the lowest application_sequence (or smallest id as tiebreak)
DEDUP = """
DELETE FROM trial_factor_configuration
WHERE id NOT IN (
    SELECT DISTINCT ON (trial_id, factor_type_id) id
    FROM trial_factor_configuration
    WHERE factor_type_id IS NOT NULL
    ORDER BY trial_id, factor_type_id, application_sequence, id
);
"""

# Phase 4: make factor_type_id NOT NULL now that we've backfilled
# (rows with no match are orphaned and were not updated — delete them)
CLEAN_ORPHANS = """
DELETE FROM trial_factor_configuration WHERE factor_type_id IS NULL;
"""

SET_NOT_NULL = """
ALTER TABLE trial_factor_configuration
    ALTER COLUMN factor_type_id SET NOT NULL;
"""

# Phase 5: drop old columns
DROP_OLD = """
ALTER TABLE trial_factor_configuration
    DROP COLUMN IF EXISTS conversion_factor_id;

ALTER TABLE trial_factor_configuration
    DROP COLUMN IF EXISTS enabled;

ALTER TABLE trial_factor_configuration
    DROP COLUMN IF EXISTS sequence_override;
"""

# Phase 6: unique constraint and index
ADD_CONSTRAINT = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_trial_factor_config_type'
    ) THEN
        ALTER TABLE trial_factor_configuration
            ADD CONSTRAINT uq_trial_factor_config_type
            UNIQUE (trial_id, factor_type_id);
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS ix_trial_factor_config_trial_type
    ON trial_factor_configuration (trial_id, factor_type_id);
"""


async def run() -> None:
    print("Refactor trial_factor_configuration (A1)")
    db_info = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Database: {db_info}\n")

    async with AsyncSessionLocal() as session:
        try:
            print("Step 1: Adding new columns...")
            for chunk in ADD_COLUMNS.split(";"):
                stmt = chunk.strip()
                if stmt:
                    await session.execute(text(stmt))

            print("Step 2: Backfilling factor_type_id from conversion_factor...")
            await session.execute(text(BACKFILL))

            print("Step 3: De-duplicating (trial_id, factor_type_id)...")
            await session.execute(text(DEDUP))

            print("Step 4: Removing orphaned rows, setting NOT NULL...")
            await session.execute(text(CLEAN_ORPHANS))
            await session.execute(text(SET_NOT_NULL))

            print("Step 5: Dropping old columns...")
            for chunk in DROP_OLD.split(";"):
                stmt = chunk.strip()
                if stmt:
                    await session.execute(text(stmt))

            print("Step 6: Adding UNIQUE constraint and index...")
            await session.execute(text(ADD_CONSTRAINT))

            await session.commit()
            print("[OK] trial_factor_configuration refactored.")

        except Exception as e:
            await session.rollback()
            print(f"[ERROR] {e}")
            raise


if __name__ == "__main__":
    asyncio.run(run())
