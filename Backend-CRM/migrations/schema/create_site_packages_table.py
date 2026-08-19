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
    CREATE TABLE IF NOT EXISTS site_packages (
        id UUID PRIMARY KEY,
        study_id UUID NOT NULL REFERENCES studies(id),
        site_id UUID NULL REFERENCES sites(id),
        irb_id INTEGER NULL,
        "ethicsBoard" VARCHAR(500) NOT NULL,
        "packageName" VARCHAR(500) NULL,
        description TEXT NULL,
        priority VARCHAR(20) NOT NULL DEFAULT 'Medium',
        "expectedSubmissionDate" TIMESTAMPTZ NULL,
        notes TEXT NULL,
        "contactPerson" JSON NULL,
        documents JSON NOT NULL DEFAULT '[]'::json,
        "auditTrail" JSON NOT NULL DEFAULT '[]'::json,
        "createdBy" VARCHAR(255) NULL,
        "lastUpdated" TIMESTAMPTZ NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'Draft',
        "isDeleted" BOOLEAN NOT NULL DEFAULT FALSE,
        "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_site_packages_study_id ON site_packages (study_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_site_packages_site_id ON site_packages (site_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_site_packages_is_deleted ON site_packages ("isDeleted");
    """,
]


async def main() -> None:
    print("=" * 70)
    print("Create site_packages table (if needed)")
    print("=" * 70)
    async with AsyncSessionLocal() as session:
        for stmt in SQL_STATEMENTS:
            await session.execute(text(stmt))
        await session.commit()
    print("✅ Done")


if __name__ == "__main__":
    asyncio.run(main())

