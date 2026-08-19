"""Add cascade metadata to budget_template: template_level, country_code, parent/geo indexes."""
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
ALTER TABLE budget_template ADD COLUMN IF NOT EXISTS template_level VARCHAR(32);
ALTER TABLE budget_template ADD COLUMN IF NOT EXISTS country_code VARCHAR(3);

-- Backfill existing rows as TRIAL-level (legacy behavior).
UPDATE budget_template
SET template_level = 'TRIAL'
WHERE template_level IS NULL;

-- Helpful indexes for cascade lookups.
CREATE INDEX IF NOT EXISTS ix_budget_template_trial_level ON budget_template (trial_id, template_level);
CREATE INDEX IF NOT EXISTS ix_budget_template_trial_country ON budget_template (trial_id, country_code);
"""


async def run() -> None:
    print("Site budgeting: cascade template_level/country_code columns")
    db_info = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Database: {db_info}\n")
    async with AsyncSessionLocal() as session:
        for chunk in SQL.split(";"):
            stmt = chunk.strip()
            if not stmt:
                continue
            await session.execute(text(stmt))
        await session.commit()
        print("[OK] Cascade template columns applied.")


if __name__ == "__main__":
    asyncio.run(run())

