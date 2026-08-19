"""Add submission method, copies, fee, and payment fields to irb_administrative_info."""
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

STEPS = [
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS submission_method TEXT",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS number_of_copies_required INTEGER",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS submission_fee_currency TEXT",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS submission_fee_amount NUMERIC(14, 2)",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS payment_method TEXT",
]


async def run():
    print(
        "Database:",
        settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url,
    )
    async with AsyncSessionLocal() as session:
        for stmt in STEPS:
            await session.execute(text(stmt))
        await session.commit()
    print("Done: submission method / fee / payment columns added.")


if __name__ == "__main__":
    asyncio.run(run())
