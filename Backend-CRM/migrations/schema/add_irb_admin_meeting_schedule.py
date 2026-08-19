"""Add meeting schedule fields to irb_administrative_info."""
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
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS full_board_meeting_frequency TEXT",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS usual_meeting_day TEXT",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS meeting_time TEXT",
    "ALTER TABLE IF EXISTS irb_administrative_info ADD COLUMN IF NOT EXISTS submission_deadline_before_meeting TEXT",
]


async def run():
    print("Database:", settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url)
    async with AsyncSessionLocal() as session:
        for stmt in STEPS:
            await session.execute(text(stmt))
        await session.commit()
    print("Done: meeting schedule columns added.")


if __name__ == "__main__":
    asyncio.run(run())
