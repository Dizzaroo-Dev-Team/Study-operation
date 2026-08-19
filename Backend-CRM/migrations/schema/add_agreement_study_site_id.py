"""
Migration script to add study_site_id to agreements and backfill it.

This is an additive, non-breaking migration:
- Adds study_site_id UUID column (nullable) referencing study_sites(id)
- Backfills study_site_id using existing (study_id, site_id) pairs
- Adds an index on study_site_id for faster joins
"""

import asyncio
from sqlalchemy import text

from app.db import AsyncSessionLocal


async def migrate():
    """Add study_site_id to agreements and backfill from study_sites."""
    async with AsyncSessionLocal() as db:
        try:
            # 1) Add study_site_id column if it does not exist
            await db.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'agreements'
                              AND column_name = 'study_site_id'
                        ) THEN
                            ALTER TABLE agreements
                            ADD COLUMN study_site_id UUID REFERENCES study_sites(id);
                        END IF;
                    END $$;
                    """
                )
            )

            # 2) Backfill study_site_id from study_sites for existing agreements
            await db.execute(
                text(
                    """
                    UPDATE agreements a
                    SET study_site_id = ss.id
                    FROM study_sites ss
                    WHERE a.study_id = ss.study_id
                      AND a.site_id = ss.site_id
                      AND a.study_site_id IS NULL;
                    """
                )
            )

            # 3) Add index on study_site_id for faster lookups
            await db.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_agreements_study_site_id
                    ON agreements (study_site_id);
                    """
                )
            )

            await db.commit()
            print("✅ Successfully added and backfilled study_site_id on agreements")
        except Exception as e:
            await db.rollback()
            print(f"❌ Migration failed: {str(e)}")
            raise


if __name__ == "__main__":
    asyncio.run(migrate())

