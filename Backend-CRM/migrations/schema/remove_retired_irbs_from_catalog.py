"""
Remove retired IRB rows (Pune IRB, pune board, Dizzaroo Board) from `irbs` and dependents.

Run from Backend-CRM with DB configured:
  python -m migrations.schema.remove_retired_irbs_from_catalog

Clears site_packages.irb_id references (no FK), deletes site_irb_mapping rows,
then deletes irbs rows matching excluded titles (CASCADE cleans admin + required docs).
"""
from __future__ import annotations

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
from app.modules.sites.irb_catalog import is_irb_excluded_from_catalog, normalize_irb_list_name


async def run() -> None:
    print(
        "Database:",
        settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url,
    )
    async with AsyncSessionLocal() as session:
        res = await session.execute(text("SELECT id, name, unique_code FROM irbs ORDER BY id ASC"))
        rows = res.fetchall()
        to_delete: list[int] = []
        for row in rows:
            rid, name, ucode = int(row[0]), row[1], row[2]
            if is_irb_excluded_from_catalog(name, ucode):
                to_delete.append(rid)
                print(
                    f"  Will delete IRB id={rid} name={name!r} code={ucode!r} "
                    f"(normalized name={normalize_irb_list_name(name)!r})"
                )

        if not to_delete:
            print("No matching IRB rows found.")
            await session.commit()
            return

        ids_csv = ",".join(str(i) for i in to_delete)

        await session.execute(text(f"UPDATE site_packages SET irb_id = NULL WHERE irb_id IN ({ids_csv})"))
        await session.execute(text(f"DELETE FROM site_irb_mapping WHERE irb_id IN ({ids_csv})"))
        await session.execute(text(f"DELETE FROM irbs WHERE id IN ({ids_csv})"))
        await session.commit()
        print(f"Done: removed {len(to_delete)} IRB(s); site_packages.irb_id cleared; mappings deleted.")


if __name__ == "__main__":
    asyncio.run(run())
