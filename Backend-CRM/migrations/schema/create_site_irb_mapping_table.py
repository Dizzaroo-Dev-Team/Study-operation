"""
Create site_irb_mapping if missing (IRB selection from Site Profile).

Safe to run multiple times.
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
    CREATE TABLE IF NOT EXISTS site_irb_mapping (
        id SERIAL PRIMARY KEY,
        site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
        study_id UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
        irb_id INTEGER NOT NULL REFERENCES irbs(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_site_irb_mapping_site_study UNIQUE (site_id, study_id)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_site_irb_mapping_site_id ON site_irb_mapping (site_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_site_irb_mapping_study_id ON site_irb_mapping (study_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_site_irb_mapping_irb_id ON site_irb_mapping (irb_id);
    """,
]


async def main() -> None:
    print("Creating site_irb_mapping (if missing)...")
    async with AsyncSessionLocal() as session:
        for stmt in SQL_STATEMENTS:
            await session.execute(text(stmt))
        await session.commit()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
