"""
One-time migration to drop the legacy AgreementVersion system.

This script:
- Drops the agreements.current_version_id column (if it exists)
- Drops the agreement_versions table (if it exists)

It is SAFE to run only after confirming that agreement_versions has 0 rows.
"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

from app.config import settings


async def drop_legacy_agreement_versions() -> None:
  """Drop legacy AgreementVersion column and table using IF EXISTS guards."""
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
      # Drop foreign key and column if they exist
      await session.execute(
          text(
              """
              DO $$
              BEGIN
                  IF EXISTS (
                      SELECT 1
                      FROM information_schema.columns
                      WHERE table_name = 'agreements'
                        AND column_name = 'current_version_id'
                  ) THEN
                      BEGIN
                          -- Drop FK constraint if present
                          IF EXISTS (
                              SELECT 1
                              FROM pg_constraint
                              WHERE conname = 'fk_agreements_current_version'
                          ) THEN
                              ALTER TABLE agreements
                              DROP CONSTRAINT fk_agreements_current_version;
                          END IF;

                          ALTER TABLE agreements
                          DROP COLUMN IF EXISTS current_version_id;
                      END;
                  END IF;
              END $$;
              """
          )
      )

      # Drop FK from agreement_comments.version_id if it exists, then drop table if it exists
      await session.execute(
          text(
              """
              DO $$
              BEGIN
                  IF EXISTS (
                      SELECT 1
                      FROM information_schema.table_constraints
                      WHERE constraint_name = 'agreement_comments_version_id_fkey'
                        AND table_name = 'agreement_comments'
                  ) THEN
                      ALTER TABLE agreement_comments
                      DROP CONSTRAINT agreement_comments_version_id_fkey;
                  END IF;
              END $$;
              """
          )
      )

      await session.execute(
          text(
              """
              DROP TABLE IF EXISTS agreement_versions;
              """
          )
      )

      await session.commit()
    finally:
      await engine.dispose()


if __name__ == "__main__":
  asyncio.run(drop_legacy_agreement_versions())

