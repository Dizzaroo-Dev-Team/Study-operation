"""
CTA workflow rewrite — schema migration.

Changes applied:
  1. Add AWAITING_INTERNAL_REVIEW and AWAITING_SPONSOR_SIGNATURE to the
     agreementstatus enum (idempotent via pg_enum guard).
  2. Create cta_assignments table (one row per CTA agreement).
  3. Create cta_placeholder_mappings table (one row per placeholder token per
     agreement).

NOT done here (intentionally deferred):
  - Dropping agreement_negotiation_rounds: the old CTA routes still reference
    it. A follow-up migration will drop that table once the old routes are
    removed from production.

Run inside the backend container:
  python migrations/schema/add_cta_workflow_rewrite.py
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
            # ------------------------------------------------------------------
            # 1. Extend agreementstatus enum with two new CTA-specific values.
            #    ALTER TYPE ... ADD VALUE cannot run inside a transaction block,
            #    so each statement is committed individually.
            # ------------------------------------------------------------------
            await session.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_enum
                        WHERE enumlabel = 'AWAITING_INTERNAL_REVIEW'
                          AND enumtypid = (
                              SELECT oid FROM pg_type WHERE typname = 'agreement_status'
                          )
                    ) THEN
                        ALTER TYPE agreement_status
                            ADD VALUE 'AWAITING_INTERNAL_REVIEW' AFTER 'SENT_FOR_SIGNATURE';
                    END IF;
                END $$;
            """))
            await session.commit()

            await session.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_enum
                        WHERE enumlabel = 'AWAITING_SPONSOR_SIGNATURE'
                          AND enumtypid = (
                              SELECT oid FROM pg_type WHERE typname = 'agreement_status'
                          )
                    ) THEN
                        ALTER TYPE agreement_status
                            ADD VALUE 'AWAITING_SPONSOR_SIGNATURE' AFTER 'AWAITING_INTERNAL_REVIEW';
                    END IF;
                END $$;
            """))
            await session.commit()

            # ------------------------------------------------------------------
            # 2. Create cta_assignments table.
            #    UNIQUE on agreement_id — exactly one assignment row per CTA.
            # ------------------------------------------------------------------
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS cta_assignments (
                    id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                    agreement_id                UUID        NOT NULL UNIQUE
                                                            REFERENCES agreements(id) ON DELETE CASCADE,
                    internal_reviewer_user_id   UUID        NOT NULL,
                    sponsor_head_user_id        UUID        NOT NULL,
                    pi_name                     VARCHAR(255) NOT NULL,
                    pi_email                    VARCHAR(255) NOT NULL,
                    designated_signer_name      VARCHAR(255) NOT NULL,
                    designated_signer_email     VARCHAR(255) NOT NULL,
                    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """))
            await session.execute(text("""
                COMMENT ON TABLE cta_assignments IS
                    'Per-CTA-agreement reviewer/signer assignment (new workflow)';
            """))

            # ------------------------------------------------------------------
            # 3. Create cta_placeholder_mappings table.
            #    UNIQUE on (agreement_id, placeholder_token).
            # ------------------------------------------------------------------
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS cta_placeholder_mappings (
                    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                    agreement_id            UUID        NOT NULL
                                                        REFERENCES agreements(id) ON DELETE CASCADE,
                    placeholder_token       VARCHAR(255) NOT NULL,
                    source                  VARCHAR(20)  NOT NULL,
                    resolved_value          TEXT,
                    ai_suggestion_field     VARCHAR(255),
                    ai_confidence           NUMERIC(4, 3),
                    confirmed_by_reviewer   BOOLEAN     NOT NULL DEFAULT FALSE,
                    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_cta_placeholder_mappings_agreement_token
                        UNIQUE (agreement_id, placeholder_token)
                );
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_cta_placeholder_mappings_agreement_id
                    ON cta_placeholder_mappings (agreement_id);
            """))
            await session.execute(text("""
                COMMENT ON TABLE cta_placeholder_mappings IS
                    'Per-token placeholder mapping rows for CTA DOCX fill workflow';
            """))

            await session.commit()
            print("add_cta_workflow_rewrite migration applied successfully.")

        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(upgrade())
