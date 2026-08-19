"""
Database migration script to create site_profile table.
Run this script to add the SiteProfile table to your database.
"""
import asyncio
import sys
import os
# Fix Windows encoding issues
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from sqlalchemy import text
from app.db import AsyncSessionLocal
from app.config import settings


async def create_site_profile_table():
    """Create the site_profile table."""
    print("=" * 70)
    print("Site Profile Table Migration")
    print("=" * 70)
    db_info = settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url
    print(f"Database: {db_info}")
    print()
    
    async with AsyncSessionLocal() as session:
        try:
            create_site_profiles_sql = """
                CREATE TABLE IF NOT EXISTS site_profiles (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    site_id UUID NOT NULL UNIQUE,
                    site_name VARCHAR(500),
                    hospital_name VARCHAR(500),
                    pi_name VARCHAR(255),
                    pi_email VARCHAR(255),
                    pi_phone VARCHAR(50),
                    pi_designation VARCHAR(255),
                    pi_department VARCHAR(255),
                    primary_contracting_entity VARCHAR(500),
                    authorized_signatory_name VARCHAR(255),
                    authorized_signatory_email VARCHAR(255),
                    authorized_signatory_title VARCHAR(255),
                    address_line_1 VARCHAR(500),
                    city VARCHAR(255),
                    state VARCHAR(255),
                    country VARCHAR(255),
                    postal_code VARCHAR(50),
                    site_coordinator_name VARCHAR(255),
                    site_coordinator_email VARCHAR(255),
                    site_coordinator_phone VARCHAR(50),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    
                    CONSTRAINT fk_site_profile_site
                        FOREIGN KEY(site_id) 
                        REFERENCES sites(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS ix_site_profiles_site_id
                    ON site_profiles (site_id);
            """
            align_pi_sql = """
                ALTER TABLE site_profiles
                ADD COLUMN IF NOT EXISTS pi_designation VARCHAR(255),
                ADD COLUMN IF NOT EXISTS pi_department VARCHAR(255)
            """
            align_phone_sql = """
                ALTER TABLE site_profiles
                ADD COLUMN IF NOT EXISTS site_coordinator_phone VARCHAR(50)
            """
            align_site_head_sql = """
                ALTER TABLE site_profiles
                ADD COLUMN IF NOT EXISTS site_head_name VARCHAR(255),
                ADD COLUMN IF NOT EXISTS site_head_email VARCHAR(255),
                ADD COLUMN IF NOT EXISTS site_head_phone VARCHAR(50)
            """
            
            print("  Creating site_profiles table (if needed)...")
            await session.execute(text(create_site_profiles_sql))
            print("  Aligning site_profiles columns (safe on existing DBs)...")
            await session.execute(text(align_pi_sql))
            await session.execute(text(align_phone_sql))
            await session.execute(text(align_site_head_sql))
            
            await session.commit()
            print()
            print("=" * 70)
            print("[SUCCESS] Site profile table created / verified successfully.")
            print("=" * 70)
            
        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] Failed to create site profile table: {e}")
            import traceback
            traceback.print_exc()
            print("\nMake sure:")
            print("  1. Your database is running")
            print("  2. Database connection settings are correct")
            print("  3. You have permissions to create tables")
            print("  4. The 'sites' table already exists (site_profiles references it)")
            sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(create_site_profile_table())
    except KeyboardInterrupt:
        print("\nMigration interrupted by user.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nAn unexpected error occurred: {exc}")
        sys.exit(1)
