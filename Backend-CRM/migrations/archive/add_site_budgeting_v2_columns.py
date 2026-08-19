"""Additive columns for cascade v2, factor scope, version lock, amendment flags."""
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
ALTER TABLE budget_template ADD COLUMN IF NOT EXISTS cost_version_label VARCHAR(100);

ALTER TABLE budget_line_item ADD COLUMN IF NOT EXISTS override_quantity NUMERIC(18,4);
ALTER TABLE budget_line_item ADD COLUMN IF NOT EXISTS needs_review BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE conversion_factor ADD COLUMN IF NOT EXISTS scope_level VARCHAR(32);
ALTER TABLE conversion_factor ADD COLUMN IF NOT EXISTS scope_element_id UUID REFERENCES cost_element(id) ON DELETE SET NULL;
ALTER TABLE conversion_factor ADD COLUMN IF NOT EXISTS scope_category VARCHAR(200);

ALTER TABLE budget_visit_matrix ADD COLUMN IF NOT EXISTS is_excluded BOOLEAN NOT NULL DEFAULT FALSE;
"""


async def run():
    print("Site budgeting v2 columns")
    db_info = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Database: {db_info}\n")
    async with AsyncSessionLocal() as session:
        for chunk in SQL.split(";"):
            stmt = chunk.strip()
            if not stmt:
                continue
            await session.execute(text(stmt))
        await session.commit()
        print("[OK] Columns applied.")


if __name__ == "__main__":
    asyncio.run(run())
