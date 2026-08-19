"""Normalize IEC Type labels on irb_administrative_info (Institutional / Independent)."""
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

UPDATES = [
    ("UPDATE irb_administrative_info SET iec_type = 'Institutional' WHERE iec_type = 'Local / Institutional'"),
    ("UPDATE irb_administrative_info SET iec_type = 'Independent' WHERE iec_type = 'Commercial / Independent'"),
]


async def run():
    print(
        "Database:",
        settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url,
    )
    async with AsyncSessionLocal() as session:
        for stmt in UPDATES:
            await session.execute(text(stmt))
        await session.commit()
    print("Done: IEC type labels migrated.")


if __name__ == "__main__":
    asyncio.run(run())
