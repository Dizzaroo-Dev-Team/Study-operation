"""
Rename MD Anderson site display name: drop trailing (SITE01) / ( SITE01) / ( Site01) suffix.

Run (from Backend-CRM, with DB configured):
  python -m migrations.schema.rename_md_anderson_site_display_name
"""
import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text

from app.config import settings
from app.db import AsyncSessionLocal

TARGET_NAME = "MD Anderson Cancer Center, Houston, TX 77030, United States"


async def run():
    print(
        "Database:",
        settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url,
    )
    async with AsyncSessionLocal() as session:
        # Exact / common variants
        result = await session.execute(
            text(
                """
                UPDATE sites
                SET name = :target
                WHERE name ILIKE '%MD Anderson Cancer Center, Houston, TX 77030, United States%'
                  AND (
                    name ILIKE '%(SITE01)%'
                    OR name ILIKE '%( SITE01)%'
                    OR name ILIKE '%( Site01)%'
                    OR name ILIKE '%(site01)%'
                    OR name ILIKE '%( SITE01 )%'
                  )
                """
            ),
            {"target": TARGET_NAME},
        )
        n = result.rowcount if hasattr(result, "rowcount") else None
        await session.commit()
        print(f"Done: updated MD Anderson site name (rows affected: {n}).")


if __name__ == "__main__":
    asyncio.run(run())
