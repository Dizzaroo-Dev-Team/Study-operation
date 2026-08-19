"""
Database migration script to create site status tracking tables.

This script is ADDITIVE ONLY – it does not modify or remove any existing
tables or columns. It introduces:

- site_statuses          (current primary status per site)
- site_status_history    (audit trail of all status changes)

Run this script once against your Postgres database.
"""

import asyncio
import sys
from sqlalchemy import text
from app.db import AsyncSessionLocal
from app.config import settings


async def create_site_status_tables():
    """Create site status related tables (additive, idempotent)."""
    print("=" * 70)
    print("Site Status Tables Migration")
    print("=" * 70)
    print(
        f"Database: {settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url}"
    )
    print()

    async with AsyncSessionLocal() as session:
        try:
            # ------------------------------------------------------------------
            # site_statuses – current primary status per site
            # ------------------------------------------------------------------
            create_site_statuses_sql = """
                CREATE TYPE IF NOT EXISTS site_primary_status AS ENUM (
                    'UNDER_EVALUATION',
                    'STARTUP',
                    'INITIATING',
                    'INITIATED_NOT_RECRUITING',
                    'RECRUITING',
                    'ACTIVE_NOT_RECRUITING',
                    'COMPLETED',
                    'SUSPENDED',
                    'TERMINATED',
                    'WITHDRAWN',
                    'CLOSED'
                );

                CREATE TABLE IF NOT EXISTS site_statuses (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
                    current_status site_primary_status NOT NULL,
                    previous_status site_primary_status,
                    metadata JSONB DEFAULT '{}'::JSONB,
                    effective_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_site_statuses_site UNIQUE (site_id)
                );

                CREATE INDEX IF NOT EXISTS ix_site_statuses_site_id
                    ON site_statuses (site_id);
                CREATE INDEX IF NOT EXISTS ix_site_statuses_current_status
                    ON site_statuses (current_status);
            """

            # ------------------------------------------------------------------
            # site_status_history – full audit trail of status changes
            # ------------------------------------------------------------------
            create_site_status_history_sql = """
                CREATE TABLE IF NOT EXISTS site_status_history (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
                    status site_primary_status NOT NULL,
                    previous_status site_primary_status,
                    metadata JSONB DEFAULT '{}'::JSONB,
                    triggering_event VARCHAR(100),
                    reason TEXT,
                    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS ix_site_status_history_site_id
                    ON site_status_history (site_id);
                CREATE INDEX IF NOT EXISTS ix_site_status_history_status
                    ON site_status_history (status);
                CREATE INDEX IF NOT EXISTS ix_site_status_history_changed_at
                    ON site_status_history (changed_at DESC);
            """

            print("  Creating site_statuses and site_status_history (if needed)...")
            await session.execute(text(create_site_statuses_sql))
            await session.execute(text(create_site_status_history_sql))

            # Add missing columns to site_status_history if table already exists
            # (for backward compatibility with existing databases)
            add_missing_columns_sql = """
                DO $$
                BEGIN
                    -- Add triggering_event column if it doesn't exist
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                        AND table_name = 'site_status_history' 
                        AND column_name = 'triggering_event'
                    ) THEN
                        ALTER TABLE site_status_history 
                        ADD COLUMN triggering_event VARCHAR(100);
                    END IF;

                    -- Add reason column if it doesn't exist
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                        AND table_name = 'site_status_history' 
                        AND column_name = 'reason'
                    ) THEN
                        ALTER TABLE site_status_history 
                        ADD COLUMN reason TEXT;
                    END IF;
                END $$;
            """
            await session.execute(text(add_missing_columns_sql))

            await session.commit()
            print()
            print("=" * 70)
            print("[SUCCESS] Site status tables created / verified successfully.")
            print("=" * 70)

        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] Failed to create site status tables: {e}")
            import traceback

            traceback.print_exc()
            print("\nMake sure:")
            print("  1. Your database is running")
            print("  2. Database connection settings are correct")
            print("  3. You have permissions to create types/tables")
            sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(create_site_status_tables())
    except KeyboardInterrupt:
        print("\nMigration interrupted by user.")
        sys.exit(1)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"\nAn unexpected error occurred: {exc}")
        sys.exit(1)


