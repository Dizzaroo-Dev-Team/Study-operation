"""
Database migration script to create:
- irb_administrative_info
- irbs

Run manually when deploying schema changes.
"""
import asyncio
import sys
from pathlib import Path

# Fix Windows encoding issues
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Ensure `app.*` imports work even when executing this script directly.
# Adds the backend project root (Backend-CRM/) to sys.path.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text

from app.config import settings
from app.db import AsyncSessionLocal


async def create_irb_admin_tables():
    print("=" * 70)
    print("IRB Administrative Info Tables Migration")
    print("=" * 70)
    db_info = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Database: {db_info}")
    print()

    async with AsyncSessionLocal() as session:
        try:
            print("  Creating irb_administrative_info and irbs tables (if needed)...")
            # asyncpg / prepared statements do not support executing multiple commands at once.
            statements = [
                """
                CREATE TABLE IF NOT EXISTS irb_administrative_info (
                    id SERIAL PRIMARY KEY,
                    site_id UUID NOT NULL,
                    study_id UUID,

                    organization_type TEXT NOT NULL,
                    irb_name TEXT,
                    iec_name TEXT,
                    irb_type TEXT,
                    iec_type TEXT,
                    registration_id TEXT,
                    fwa_number TEXT,
                    ohrp_number TEXT,
                    accreditation_body TEXT,
                    accreditation_number TEXT,
                    accreditation_expiry DATE,
                    irb_status TEXT,
                    date_established DATE,
                    jurisdiction TEXT,

                    address_line_1 TEXT,
                    address_line_2 TEXT,
                    city TEXT,
                    state TEXT,
                    zip_code TEXT,
                    country TEXT,
                    office_hours TEXT,
                    time_zone TEXT,

                    primary_contact_name TEXT,
                    primary_contact_job_title TEXT,
                    primary_contact_email TEXT,
                    primary_contact_phone TEXT,

                    secondary_contact_name TEXT,
                    secondary_contact_job_title TEXT,
                    secondary_contact_email TEXT,
                    secondary_contact_phone TEXT,

                    chair_name TEXT,
                    vice_chair_name TEXT,
                    number_of_members INTEGER,
                    number_of_alternates INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE INDEX IF NOT EXISTS ix_irb_admin_site_id
                    ON irb_administrative_info (site_id);
                """,
                """
                CREATE TABLE IF NOT EXISTS irbs (
                    id SERIAL PRIMARY KEY,
                    site_id UUID NOT NULL,
                    study_id UUID NOT NULL,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (study_id, site_id)
                );
                """,
                """
                CREATE INDEX IF NOT EXISTS ix_irbs_site_id
                    ON irbs (site_id);
                """,
                """
                -- Upgrade existing installations:
                -- Drop old unique constraints (if present) and enforce UNIQUE(study_id, site_id).
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'uq_irbs_site_id_name'
                    ) THEN
                        ALTER TABLE irbs DROP CONSTRAINT uq_irbs_site_id_name;
                    END IF;
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'irbs_site_id_name_key'
                    ) THEN
                        ALTER TABLE irbs DROP CONSTRAINT irbs_site_id_name_key;
                    END IF;
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'unique_study_site_irb'
                    ) THEN
                        ALTER TABLE irbs DROP CONSTRAINT unique_study_site_irb;
                    END IF;
                END $$;
                """,
                """
                -- Backfill legacy NULL study_id rows using the latest irb_administrative_info record for the same site.
                UPDATE irbs i
                SET study_id = x.study_id
                FROM (
                    SELECT DISTINCT ON (a.site_id)
                        a.site_id,
                        a.study_id
                    FROM irb_administrative_info a
                    WHERE a.study_id IS NOT NULL
                    ORDER BY a.site_id, a.created_at DESC
                ) x
                WHERE i.study_id IS NULL
                  AND i.site_id = x.site_id;
                """,
                """
                -- If any legacy rows still have NULL study_id, they cannot satisfy the new rule.
                -- These typically come from earlier test submissions; remove them to unblock the constraint.
                DELETE FROM irbs WHERE study_id IS NULL;
                """,
                """
                -- Ensure study_id is NOT NULL.
                ALTER TABLE irbs
                ALTER COLUMN study_id SET NOT NULL;
                """,
                """
                -- Deduplicate legacy rows so we can enforce UNIQUE(study_id, site_id).
                -- Keep the smallest id per (study_id, site_id).
                DELETE FROM irbs a
                USING irbs b
                WHERE a.study_id = b.study_id
                  AND a.site_id = b.site_id
                  AND a.id > b.id;
                """,
                """
                -- Re-add the correct uniqueness rule for 1 IRB per study+site.
                ALTER TABLE irbs
                ADD CONSTRAINT unique_study_site_irb UNIQUE (study_id, site_id);
                """,
            ]

            for stmt in statements:
                await session.execute(text(stmt))
            await session.commit()
            print()
            print("=" * 70)
            print("[SUCCESS] IRB tables created / verified successfully.")
            print("=" * 70)
        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] Failed to create IRB tables: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(create_irb_admin_tables())

