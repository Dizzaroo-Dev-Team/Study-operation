"""
Remove an IRB row by exact catalog-normalized name (e.g. duplicate "ABC").

Clears site_packages.irb_id, deletes site_irb_mapping rows, then deletes irbs row.
CASCADE removes irb_administrative_info and irb_required_documents.

Usage (from Backend-CRM, DB env configured):
  python -m migrations.schema.delete_irb_by_exact_name
  python -m migrations.schema.delete_irb_by_exact_name --name ABC
"""
from __future__ import annotations

import argparse
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
from app.modules.sites.irb_catalog import normalize_irb_list_name


async def run(target_normalized: str) -> None:
    print(
        "Database:",
        settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url,
    )
    target = (target_normalized or "").strip().lower()
    if not target:
        print("Empty target name.")
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(text("SELECT id, name, unique_code FROM irbs ORDER BY id ASC"))
        rows = res.fetchall()
        to_delete: list[int] = []
        for row in rows:
            rid, name, ucode = int(row[0]), row[1], row[2]
            if normalize_irb_list_name(name) == target:
                to_delete.append(rid)
                print(f"  Will delete IRB id={rid} name={name!r} code={ucode!r}")

        if not to_delete:
            print(f"No IRB found with normalized name equal to {target!r}.")
            await session.commit()
            return

        ids_csv = ",".join(str(i) for i in to_delete)

        await session.execute(text(f"UPDATE site_packages SET irb_id = NULL WHERE irb_id IN ({ids_csv})"))
        await session.execute(text(f"DELETE FROM site_irb_mapping WHERE irb_id IN ({ids_csv})"))
        await session.execute(text(f"DELETE FROM irbs WHERE id IN ({ids_csv})"))
        await session.commit()
        print(
            f"Done: removed {len(to_delete)} IRB(s); site_packages.irb_id cleared; mappings deleted; CASCADE cleans admin rows."
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Delete IRB(s) whose normalized name matches exactly.")
    p.add_argument(
        "--name",
        default="ABC",
        help="IRB display name to match (normalized: trim, lower, collapse spaces). Default: ABC",
    )
    args = p.parse_args()
    asyncio.run(run(normalize_irb_list_name(args.name)))
