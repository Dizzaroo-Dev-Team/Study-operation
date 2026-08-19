"""
Quick fix: add irbs.unique_code expected by SQLAlchemy models.

Run this if you see:
  UndefinedColumnError: column irbs.unique_code does not exist

Safe to run multiple times (idempotent).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import AsyncSessionLocal  # noqa: E402

SQL_STATEMENTS = [
    """
    ALTER TABLE IF EXISTS irbs
    ADD COLUMN IF NOT EXISTS unique_code TEXT;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = 'ix_irbs_unique_code'
        ) THEN
            CREATE UNIQUE INDEX ix_irbs_unique_code ON irbs (unique_code);
        END IF;
    END $$;
    """,
]


async def main() -> None:
    print("Adding irbs.unique_code (if missing)...")
    async with AsyncSessionLocal() as session:
        for stmt in SQL_STATEMENTS:
            await session.execute(text(stmt))
        await session.commit()
    print("Done. If you use unique_code in the app, uncomment IRB.unique_code in app/models.py.")


if __name__ == "__main__":
    asyncio.run(main())
