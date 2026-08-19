"""
Fix inconsistent site_irb_mapping: multiple IRBs for one site (same site_id, different irb_id).

Sets every row for the given site to the same irb_id so IRB Administrative Info save can succeed.

Usage (from Backend-CRM, DB configured):
  python -m migrations.schema.dedupe_site_irb_mapping --site-id <UUID> --keep-irb-id <int>

Example:
  python -m migrations.schema.dedupe_site_irb_mapping \\
    --site-id 550e8400-e29b-41d4-a716-446655440000 \\
    --keep-irb-id 3

Find irb_id for "MD Anderson" in DB:
  SELECT id, name FROM irbs ORDER BY id;
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

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


async def run(site_id: UUID, keep_irb_id: int) -> None:
    print(
        "Database:",
        settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url,
    )

    async with AsyncSessionLocal() as session:
        before = await session.execute(
            text(
                """
                SELECT study_id, irb_id
                FROM site_irb_mapping
                WHERE site_id = CAST(:sid AS uuid)
                ORDER BY study_id
                """
            ),
            {"sid": str(site_id)},
        )
        rows = before.fetchall()
        if not rows:
            print("No site_irb_mapping rows for this site_id. Nothing to do.")
            await session.commit()
            return

        distinct = sorted({int(r[1]) for r in rows})
        print(f"Before: {len(rows)} row(s), distinct irb_id values: {distinct}")

        if len(distinct) <= 1 and distinct[0] == keep_irb_id:
            print("Already consistent. No update needed.")
            await session.commit()
            return

        res = await session.execute(
            text(
                """
                UPDATE site_irb_mapping
                SET irb_id = :iid, updated_at = CURRENT_TIMESTAMP
                WHERE site_id = CAST(:sid AS uuid)
                """
            ),
            {"iid": keep_irb_id, "sid": str(site_id)},
        )
        await session.commit()
        print(f"Updated {res.rowcount} row(s) to irb_id={keep_irb_id}.")

        after = await session.execute(
            text(
                """
                SELECT DISTINCT irb_id FROM site_irb_mapping
                WHERE site_id = CAST(:sid AS uuid)
                """
            ),
            {"sid": str(site_id)},
        )
        print(f"After distinct irb_id: {[int(r[0]) for r in after.fetchall()]}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Set all site_irb_mapping rows for a site to one IRB.")
    p.add_argument("--site-id", required=True, type=UUID, help="Site UUID")
    p.add_argument("--keep-irb-id", required=True, type=int, help="IRB id to keep (e.g. MD Anderson)")
    args = p.parse_args()
    asyncio.run(run(args.site_id, args.keep_irb_id))
