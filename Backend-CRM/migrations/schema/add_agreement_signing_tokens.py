"""
Add agreement_signing_tokens table for secure email-link signing.

Run inside the backend container:
  python migrations/schema/add_agreement_signing_tokens.py
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


async def upgrade() -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agreement_signing_tokens (
                id UUID PRIMARY KEY,
                agreement_id UUID NOT NULL REFERENCES agreements(id),
                token VARCHAR(255) NOT NULL UNIQUE,
                role VARCHAR(50) NOT NULL DEFAULT 'site',
                recipient_email VARCHAR(255) NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                created_by VARCHAR(255),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                used_at TIMESTAMPTZ,
                is_active VARCHAR(10) NOT NULL DEFAULT 'true'
            );
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_agreement_signing_tokens_token
            ON agreement_signing_tokens(token);
        """))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(upgrade())
    print("agreement_signing_tokens migration completed")
