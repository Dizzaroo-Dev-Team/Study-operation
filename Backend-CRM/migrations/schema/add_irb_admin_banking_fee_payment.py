"""Add banking & fee payment detail fields to irb_administrative_info."""
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
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS bank_name TEXT",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS bank_account_name TEXT",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS bank_account_number TEXT",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS routing_swift_code TEXT",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS iban TEXT",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS banking_currency TEXT",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS invoice_address_alt TEXT",
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
    print("Done: banking & fee payment columns added.")


if __name__ == "__main__":
    asyncio.run(run())
