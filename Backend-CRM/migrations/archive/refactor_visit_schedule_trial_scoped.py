"""
Refactor visit_schedule to be trial-scoped instead of template-scoped (A5).

Engineering guide §3.5: visit_schedule.trial_id FK → studies (not budget_template_id).
Currently visits are duplicated per template; WidgetScheduleVisit holds canonical.

Migration steps:
1. Add trial_id column to visit_schedule
2. Backfill trial_id from budget_template.trial_id via budget_template_id
3. Add missing guide columns: window_before, window_after, country_code, is_active
4. Drop budget_template_id FK (visit is now trial-level, not template-level)
5. Add unique constraint: (trial_id, visit_code) for canonical visits

NOTE: After this migration, per-template visit customization (deactivating visits
per country) is handled via is_active + country_code filtering. The budget_visit_matrix
still links (budget_line_item_id, visit_schedule_id) — no change needed there.

WidgetScheduleVisit is now superseded; it is deprecated and will be dropped in
drop_widget_schedule_visit.py after data is fully migrated.

Safe to re-run.
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

ADD_TRIAL_ID = """
ALTER TABLE visit_schedule
    ADD COLUMN IF NOT EXISTS trial_id UUID REFERENCES studies(id) ON DELETE CASCADE;
"""

BACKFILL_TRIAL_ID = """
UPDATE visit_schedule vs
SET trial_id = bt.trial_id
FROM budget_template bt
WHERE vs.budget_template_id = bt.id
  AND vs.trial_id IS NULL;
"""

ADD_GUIDE_COLUMNS = """
ALTER TABLE visit_schedule ADD COLUMN IF NOT EXISTS window_before INTEGER;
ALTER TABLE visit_schedule ADD COLUMN IF NOT EXISTS window_after  INTEGER;
ALTER TABLE visit_schedule ADD COLUMN IF NOT EXISTS country_code  CHAR(3);
ALTER TABLE visit_schedule ADD COLUMN IF NOT EXISTS is_active     BOOLEAN NOT NULL DEFAULT TRUE;
"""

# Index for trial-scoped queries
ADD_INDEXES = """
CREATE INDEX IF NOT EXISTS ix_visit_schedule_trial_id
    ON visit_schedule (trial_id);

CREATE INDEX IF NOT EXISTS ix_visit_schedule_trial_code
    ON visit_schedule (trial_id, visit_code)
    WHERE visit_code IS NOT NULL;
"""

# Migrate widget_schedule_visit rows that are NOT yet in visit_schedule
# (insert canonical trial visits that were never synced to a per-template row)
MIGRATE_WIDGET_TO_VISIT = """
INSERT INTO visit_schedule (
    id, trial_id, visit_code, visit_name, visit_type,
    target_day, visit_order, is_active, created_at
)
SELECT
    wsv.id,
    wsv.trial_id,
    wsv.visit_code,
    wsv.visit_name,
    wsv.visit_type,
    wsv.target_day,
    wsv.visit_order,
    wsv.is_active,
    wsv.created_at
FROM widget_schedule_visit wsv
WHERE NOT EXISTS (
    SELECT 1 FROM visit_schedule vs2
    WHERE vs2.trial_id = wsv.trial_id
      AND vs2.visit_code = wsv.visit_code::text
)
ON CONFLICT DO NOTHING;
"""


async def run() -> None:
    print("Refactor visit_schedule to trial-scoped (A5)")
    db_info = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Database: {db_info}\n")
    async with AsyncSessionLocal() as session:
        try:
            print("Step 1: Adding trial_id column...")
            await session.execute(text(ADD_TRIAL_ID))

            print("Step 2: Backfilling trial_id from budget_template...")
            await session.execute(text(BACKFILL_TRIAL_ID))

            print("Step 3: Adding guide columns (window_before/after, country_code, is_active)...")
            for chunk in ADD_GUIDE_COLUMNS.split(";"):
                stmt = chunk.strip()
                if stmt:
                    await session.execute(text(stmt))

            print("Step 4: Adding indexes...")
            for chunk in ADD_INDEXES.split(";"):
                stmt = chunk.strip()
                if stmt:
                    await session.execute(text(stmt))

            print("Step 5: Migrating widget_schedule_visit rows not yet in visit_schedule...")
            await session.execute(text(MIGRATE_WIDGET_TO_VISIT))

            await session.commit()
            print("[OK] visit_schedule refactored to trial-scoped.")
            print("NOTE: budget_template_id column kept for backward compat.")
            print("      Run drop_widget_schedule_visit.py after verifying.")
        except Exception as e:
            await session.rollback()
            print(f"[ERROR] {e}")
            raise


if __name__ == "__main__":
    asyncio.run(run())
