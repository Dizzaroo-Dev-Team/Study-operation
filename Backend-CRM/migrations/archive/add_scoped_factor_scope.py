"""Scoped factor support: high-level GLOBAL/COUNTRY/SITE columns."""
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
ALTER TABLE conversion_factor ADD COLUMN IF NOT EXISTS scope_type VARCHAR(32);
ALTER TABLE conversion_factor ADD COLUMN IF NOT EXISTS scope_value VARCHAR(200);
UPDATE conversion_factor SET scope_type = 'GLOBAL' WHERE scope_type IS NULL;
"""


async def run() -> None:
    print("Site budgeting scoped factor columns")
    db_info = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Database: {db_info}\n")
    async with AsyncSessionLocal() as session:
        for chunk in SQL.split(";"):
            stmt = chunk.strip()
            if not stmt:
                continue
            await session.execute(text(stmt))
        await session.commit()
        print("[OK] Scoped factor columns applied.")


if __name__ == "__main__":
    asyncio.run(run())

