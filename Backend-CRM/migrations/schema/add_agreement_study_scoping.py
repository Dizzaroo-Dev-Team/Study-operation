"""
Migration script to add explicit Study + Site scoping fields to agreements.

Adds:
- study_id UUID (FK to studies.id, nullable)
- agreement_type template_type (nullable)

Backfills study_id from sites.study_id for existing data and adds a partial
unique index on (study_id, site_id, agreement_type) for non-null scoped rows.

This script is idempotent and safe to run multiple times.
"""

import asyncio
from sqlalchemy import text

from app.db import AsyncSessionLocal


async def migrate():
  """Add Study + Site scoping fields to agreements table."""
  async with AsyncSessionLocal() as db:
    try:
      # 1) Add columns if they don't exist
      await db.execute(
        text(
          """
          DO $$
          BEGIN
            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_name = 'agreements' AND column_name = 'study_id'
            ) THEN
              ALTER TABLE agreements
              ADD COLUMN study_id UUID REFERENCES studies(id);
            END IF;

            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_name = 'agreements' AND column_name = 'agreement_type'
            ) THEN
              ALTER TABLE agreements
              ADD COLUMN agreement_type template_type;
            END IF;
          END $$;
          """
        )
      )

      # 2) Backfill study_id from sites.study_id where missing
      await db.execute(
        text(
          """
          UPDATE agreements a
          SET study_id = s.study_id
          FROM sites s
          WHERE a.site_id = s.id
            AND a.study_id IS NULL;
          """
        )
      )

      # 3) Create partial unique index for scoped rows
      await db.execute(
        text(
          """
          CREATE UNIQUE INDEX IF NOT EXISTS uq_agreements_study_site_type
          ON agreements (study_id, site_id, agreement_type)
          WHERE study_id IS NOT NULL AND agreement_type IS NOT NULL;
          """
        )
      )

      await db.commit()
      print("✅ Successfully added Study + Site scoping fields to agreements")
    except Exception as e:
      await db.rollback()
      print(f"❌ Migration failed: {str(e)}")
      raise


if __name__ == "__main__":
  asyncio.run(migrate())

