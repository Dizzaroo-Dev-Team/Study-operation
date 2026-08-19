"""
One-time migration to drop the deprecated sites.study_id column.

Prerequisites:
- All Study + Site scoping must use StudySite.

This script:
- Drops the sites.study_id column if it exists.
"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

from app.config import settings


async def drop_sites_study_id() -> None:
    """Drop the deprecated study_id column from sites using IF EXISTS guards."""
    db_url = settings.database_url

    engine = create_async_engine(db_url, echo=False, future=True)
    SessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with SessionLocal() as session:
        try:
            await session.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = 'sites'
                              AND column_name = 'study_id'
                        ) THEN
                            ALTER TABLE sites
                            DROP COLUMN IF EXISTS study_id;
                        END IF;
                    END $$;
                    """
                )
            )

            await session.commit()
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(drop_sites_study_id())

