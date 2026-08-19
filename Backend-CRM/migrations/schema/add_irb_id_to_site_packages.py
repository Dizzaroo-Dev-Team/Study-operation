from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

# Ensure `app.*` imports work when run directly
BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from app.db import AsyncSessionLocal  # noqa: E402


SQL_STATEMENTS = [
    """
    ALTER TABLE IF EXISTS site_packages
    ADD COLUMN IF NOT EXISTS irb_id INTEGER;
    """,
]


async def main() -> None:
    print("=" * 70)
    print("Add irb_id column to site_packages")
    print("=" * 70)
    async with AsyncSessionLocal() as session:
        for stmt in SQL_STATEMENTS:
            await session.execute(text(stmt))
        await session.commit()
    print("✅ Done")


if __name__ == "__main__":
    asyncio.run(main())

