"""
Add columns from engineering guide spec:
  - cost_element: element_type, cost_type, therapeutic_area, is_active
  - budget_milestone: quantity

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
-- cost_element: engineering guide fields
ALTER TABLE cost_element
    ADD COLUMN IF NOT EXISTS element_type VARCHAR(20);

ALTER TABLE cost_element
    ADD COLUMN IF NOT EXISTS cost_type VARCHAR(30);

ALTER TABLE cost_element
    ADD COLUMN IF NOT EXISTS therapeutic_area VARCHAR(100);

ALTER TABLE cost_element
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- budget_milestone: quantity (unit_cost × qty = line total)
ALTER TABLE budget_milestone
    ADD COLUMN IF NOT EXISTS quantity NUMERIC(10,2) NOT NULL DEFAULT 1;
"""


async def run() -> None:
    print("Site budgeting v4 columns migration")
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
            print("[OK] v4 columns applied.")
        except Exception as e:
            await session.rollback()
            print(f"[ERROR] {e}")
            raise


if __name__ == "__main__":
    asyncio.run(run())
