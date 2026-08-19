"""Add decision/outcome, dates, and letter reference to irb_administrative_info."""
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
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS decision_outcome TEXT",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS decision_date DATE",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS decision_letter_reference TEXT",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS approval_date DATE",
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
    print("Done: review decision / letter / approval date columns added.")


if __name__ == "__main__":
    asyncio.run(run())
