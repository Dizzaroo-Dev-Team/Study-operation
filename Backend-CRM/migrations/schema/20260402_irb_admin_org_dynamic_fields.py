"""
Migration: Replace irb_administrative_info.organization_name with:
- irb_name (for organization_type IRB/BOTH)
- iec_name (for organization_type IEC/BOTH)

This matches the dynamic Basic Demographics UX:
IRB  => require irb_name
IEC  => require iec_name
BOTH => require both

Steps:
1) Add irb_name + iec_name columns (idempotent)
2) Backfill from organization_name using organization_type
3) Drop organization_name column (if present)
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
    ALTER TABLE IF EXISTS irb_administrative_info
    ADD COLUMN IF NOT EXISTS irb_name TEXT;
    """,
    """
    ALTER TABLE IF EXISTS irb_administrative_info
    ADD COLUMN IF NOT EXISTS iec_name TEXT;
    """,
    # Backfill only if the legacy column still exists.
    """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name='irb_administrative_info'
              AND column_name='organization_name'
        ) THEN
            -- IRB => move organization_name => irb_name
            UPDATE irb_administrative_info
            SET irb_name = organization_name
            WHERE organization_type = 'IRB'
              AND (irb_name IS NULL OR irb_name = '');

            -- IEC => move organization_name => iec_name
            UPDATE irb_administrative_info
            SET iec_name = organization_name
            WHERE organization_type = 'IEC'
              AND (iec_name IS NULL OR iec_name = '');

            -- BOTH => set both from legacy organization_name
            UPDATE irb_administrative_info
            SET irb_name = COALESCE(NULLIF(irb_name, ''), organization_name),
                iec_name = COALESCE(NULLIF(iec_name, ''), organization_name)
            WHERE organization_type = 'BOTH';
        END IF;
    END $$;
    """,
    """
    ALTER TABLE IF EXISTS irb_administrative_info
    DROP COLUMN IF EXISTS organization_name;
    """,
]


async def main() -> None:
    print("=" * 70)
    print("IRB Admin dynamic org fields migration")
    print("=" * 70)
    async with AsyncSessionLocal() as session:
        for stmt in SQL_STATEMENTS:
            await session.execute(text(stmt))
        await session.commit()
    print("✅ Done")


if __name__ == "__main__":
    asyncio.run(main())

