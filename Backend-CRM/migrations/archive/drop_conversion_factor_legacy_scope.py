"""
Remove legacy scope_type / scope_value columns from conversion_factor (A2).

These were a high-level geographic scope overlay (GLOBAL/COUNTRY/SITE) added as
a UI convenience. The factor resolution engine (resolve_factor_match_rank) does
NOT use them — it uses scope_level + scope_element_id + scope_category.

Having two overlapping scope systems in the same table causes confusion and
violates the engineering guide's data model.

Deletion criteria:
- scope_type: set to 'GLOBAL' for all rows by the add_scoped_factor_scope migration
  then never read by any service code (verified by grep: only ConversionFactorCreate
  schema accepted it as input; no service reads it for resolution).
- scope_value: similarly unused by engine.

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

SQL = """
ALTER TABLE conversion_factor DROP COLUMN IF EXISTS scope_type;
ALTER TABLE conversion_factor DROP COLUMN IF EXISTS scope_value;
"""

# Also add justification column (guide §3.2) while we're here
ADD_JUSTIFICATION = """
ALTER TABLE conversion_factor ADD COLUMN IF NOT EXISTS justification TEXT;
"""


async def run() -> None:
    print("Drop conversion_factor legacy scope columns (A2)")
    db_info = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Database: {db_info}\n")
    async with AsyncSessionLocal() as session:
        try:
            print("Dropping scope_type and scope_value...")
            for chunk in SQL.split(";"):
                stmt = chunk.strip()
                if stmt:
                    await session.execute(text(stmt))

            print("Adding justification column...")
            await session.execute(text(ADD_JUSTIFICATION))

            await session.commit()
            print("[OK] Legacy scope columns dropped; justification added.")
        except Exception as e:
            await session.rollback()
            print(f"[ERROR] {e}")
            raise


if __name__ == "__main__":
    asyncio.run(run())
