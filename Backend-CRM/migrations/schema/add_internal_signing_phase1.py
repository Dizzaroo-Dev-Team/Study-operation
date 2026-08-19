"""
Phase 1 additive migration: internal signing alongside Zoho.
"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings


async def add_internal_signing_phase1():
    db_url_to_use = settings.database_url
    if 'postgres:' in db_url_to_use and 'localhost' not in db_url_to_use and '127.0.0.1' not in db_url_to_use:
        db_url_to_use = db_url_to_use.replace('postgres:', 'localhost:')

    engine = create_async_engine(db_url_to_use, echo=False, future=True)
    SessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with SessionLocal() as session:
        try:
            # Agreement status enum value
            await session.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_enum
                        WHERE enumlabel = 'FULLY_SIGNED'
                        AND enumtypid = (
                            SELECT oid FROM pg_type WHERE typname = 'agreement_status'
                        )
                    ) THEN
                        ALTER TYPE agreement_status ADD VALUE 'FULLY_SIGNED' AFTER 'REVIEWED_AND_SIGNED';
                    END IF;
                END $$;
            """))

            # Signature source enum type
            await session.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE agreement_signature_source AS ENUM ('ZOHO', 'INTERNAL');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))

            # Add signature_source column (default ZOHO for backward compatibility)
            await session.execute(text("""
                ALTER TABLE agreements
                ADD COLUMN IF NOT EXISTS signature_source agreement_signature_source NOT NULL DEFAULT 'ZOHO';
            """))

            # Internal signatures
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS agreement_internal_signatures (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    agreement_id UUID NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
                    document_id UUID NOT NULL REFERENCES agreement_documents(id) ON DELETE CASCADE,
                    role VARCHAR(50) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    meaning VARCHAR(255) NOT NULL,
                    auth_method VARCHAR(50) NOT NULL DEFAULT 'otp',
                    version INTEGER NOT NULL,
                    ip_address VARCHAR(100),
                    document_hash VARCHAR(64) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_agreement_internal_signatures_agreement_id
                ON agreement_internal_signatures (agreement_id);
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_agreement_internal_signatures_role
                ON agreement_internal_signatures (agreement_id, role);
            """))

            # Signing OTPs
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS agreement_signing_otps (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    agreement_id UUID NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
                    document_id UUID NOT NULL REFERENCES agreement_documents(id) ON DELETE CASCADE,
                    role VARCHAR(50) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    otp_hash VARCHAR(255) NOT NULL,
                    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    last_sent_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    consumed_at TIMESTAMP WITH TIME ZONE,
                    is_active VARCHAR(10) NOT NULL DEFAULT 'true'
                );
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_agreement_signing_otps_agreement_id
                ON agreement_signing_otps (agreement_id);
            """))

            await session.commit()
            print("Internal signing Phase 1 migration applied successfully.")
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(add_internal_signing_phase1())

