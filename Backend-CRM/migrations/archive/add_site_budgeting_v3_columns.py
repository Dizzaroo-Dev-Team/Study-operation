"""
Add missing columns identified in audit:
  - budget_milestone.payment_trigger
  - budget_note.category
  - visit_schedule.visit_type, target_day
  - site_budgeting_audit_log.cascade_level, field_name, justification, session_id
  - budget_template.template_level, country_code (if not already added by cascade migration)

Safe to re-run: uses ADD COLUMN IF NOT EXISTS.
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

SQL = """
-- budget_milestone: payment trigger (e.g. "SIV Complete", "Last Patient Last Visit")
ALTER TABLE budget_milestone
    ADD COLUMN IF NOT EXISTS payment_trigger VARCHAR(200);

-- budget_note: category (e.g. "Payment Terms", "Enrollment Cap", "Pass-Through")
ALTER TABLE budget_note
    ADD COLUMN IF NOT EXISTS category VARCHAR(50);

-- visit_schedule: visit type and target protocol day
ALTER TABLE visit_schedule
    ADD COLUMN IF NOT EXISTS visit_type VARCHAR(50);
ALTER TABLE visit_schedule
    ADD COLUMN IF NOT EXISTS target_day INTEGER;

-- site_budgeting_audit_log: cascade level, field, justification, session grouping
ALTER TABLE site_budgeting_audit_log
    ADD COLUMN IF NOT EXISTS cascade_level VARCHAR(32);
ALTER TABLE site_budgeting_audit_log
    ADD COLUMN IF NOT EXISTS field_name VARCHAR(100);
ALTER TABLE site_budgeting_audit_log
    ADD COLUMN IF NOT EXISTS justification TEXT;
ALTER TABLE site_budgeting_audit_log
    ADD COLUMN IF NOT EXISTS session_id UUID;

CREATE INDEX IF NOT EXISTS ix_site_budgeting_audit_session_id
    ON site_budgeting_audit_log (session_id);

-- budget_template: cascade level columns (may already exist from add_cascade_template_levels)
ALTER TABLE budget_template
    ADD COLUMN IF NOT EXISTS template_level VARCHAR(32);
ALTER TABLE budget_template
    ADD COLUMN IF NOT EXISTS country_code VARCHAR(3);

CREATE INDEX IF NOT EXISTS ix_budget_template_trial_level
    ON budget_template (trial_id, template_level);
CREATE INDEX IF NOT EXISTS ix_budget_template_trial_country
    ON budget_template (trial_id, country_code);
"""


async def run() -> None:
    print("Site budgeting v3 columns migration")
    db_info = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Database: {db_info}\n")
    async with AsyncSessionLocal() as session:
        try:
            for chunk in SQL.split(";"):
                stmt = chunk.strip()
                if not stmt:
                    continue
                await session.execute(text(stmt))
            await session.commit()
            print("[OK] v3 columns applied.")
        except Exception as e:
            await session.rollback()
            print(f"[ERROR] {e}")
            raise


if __name__ == "__main__":
    asyncio.run(run())
