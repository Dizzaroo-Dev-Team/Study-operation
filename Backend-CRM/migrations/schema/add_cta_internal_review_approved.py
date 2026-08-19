"""
Add INTERNAL_REVIEW_APPROVED to the agreementstatus enum.

The CTA workflow now splits "approve" and "send for signature" into two
distinct steps:
  - Internal Reviewer clicks Approve → AWAITING_INTERNAL_REVIEW → INTERNAL_REVIEW_APPROVED
  - Creator (or any non-reviewer team member) clicks Send for Signature →
    INTERNAL_REVIEW_APPROVED → SENT_FOR_SIGNATURE (PDF + dispatch fires here)

Run inside the backend container:
  PYTHONPATH=/app python migrations/schema/add_cta_internal_review_approved.py
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings


async def upgrade() -> None:
    engine = create_async_engine(settings.database_url, echo=False, future=True)
    SessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with SessionLocal() as session:
        try:
            await session.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_enum
                        WHERE enumlabel = 'INTERNAL_REVIEW_APPROVED'
                          AND enumtypid = (
                              SELECT oid FROM pg_type WHERE typname = 'agreement_status'
                          )
                    ) THEN
                        ALTER TYPE agreement_status
                            ADD VALUE 'INTERNAL_REVIEW_APPROVED' AFTER 'AWAITING_INTERNAL_REVIEW';
                    END IF;
                END $$;
            """))
            await session.commit()
            print("add_cta_internal_review_approved migration applied successfully.")
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(upgrade())
