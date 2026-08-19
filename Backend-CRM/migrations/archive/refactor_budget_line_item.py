"""
Refactor budget_line_item to match engineering guide §3.4 (A3).

Changes:
1. Add is_excluded BOOLEAN NOT NULL DEFAULT FALSE
   - Backfill: is_excluded = (excluded = TRUE OR included = FALSE)
2. Drop 'excluded' column (renamed to is_excluded)
3. Drop 'included' column (redundant — inverse of is_excluded causes 4-state confusion)
4. Drop 'parent_line_item_id' column (shadow cascade hierarchy conflicts with template cascade)
5. Add 'default_quantity' NUMERIC(10,2) (stores trial-level default qty per guide)

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

ADD_IS_EXCLUDED = """
ALTER TABLE budget_line_item
    ADD COLUMN IF NOT EXISTS is_excluded BOOLEAN NOT NULL DEFAULT FALSE;
"""

BACKFILL_IS_EXCLUDED = """
UPDATE budget_line_item
SET is_excluded = TRUE
WHERE (excluded = TRUE OR included = FALSE)
  AND is_excluded = FALSE;
"""

ADD_DEFAULT_QUANTITY = """
ALTER TABLE budget_line_item
    ADD COLUMN IF NOT EXISTS default_quantity NUMERIC(10,2);
"""

DROP_OLD = """
ALTER TABLE budget_line_item DROP COLUMN IF EXISTS excluded;
ALTER TABLE budget_line_item DROP COLUMN IF EXISTS included;
ALTER TABLE budget_line_item DROP COLUMN IF EXISTS parent_line_item_id;
"""


async def run() -> None:
    print("Refactor budget_line_item (A3)")
    db_info = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Database: {db_info}\n")
    async with AsyncSessionLocal() as session:
        try:
            print("Step 1: Adding is_excluded column...")
            await session.execute(text(ADD_IS_EXCLUDED))

            print("Step 2: Backfilling is_excluded from excluded/included...")
            await session.execute(text(BACKFILL_IS_EXCLUDED))

            print("Step 3: Adding default_quantity column...")
            await session.execute(text(ADD_DEFAULT_QUANTITY))

            print("Step 4: Dropping excluded, included, parent_line_item_id...")
            for chunk in DROP_OLD.split(";"):
                stmt = chunk.strip()
                if stmt:
                    await session.execute(text(stmt))

            await session.commit()
            print("[OK] budget_line_item refactored.")
        except Exception as e:
            await session.rollback()
            print(f"[ERROR] {e}")
            raise


if __name__ == "__main__":
    asyncio.run(run())
