"""
Database migration script to create study_site mapping table and update workflow steps.

This script:
1. Creates study_sites table for many-to-many study-site relationships
2. Migrates existing workflow steps to use study_site_id
3. Updates site_workflow_steps table to add study_site_id column

Usage:
  - For Neon Production: Set NEON_DATABASE_URL environment variable
    Example: set NEON_DATABASE_URL=postgresql+asyncpg://user:pass@neon-host/dbname
    Then run: python create_study_site_mapping.py
  
  - For Local Database: Uses DATABASE_URL from .env file
    Then run: python create_study_site_mapping.py

Run this script once against your Postgres database.
"""

import asyncio
import sys
import os
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Load environment variables
from dotenv import load_dotenv
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

from app.config import settings


async def create_study_site_mapping():
    """Create study_site mapping table and migrate workflow steps."""
    print("=" * 70)
    print("Study-Site Mapping Migration")
    print("=" * 70)
    
    # Check for NEON_DATABASE_URL first (for production), then fall back to DATABASE_URL
    neon_db_url = os.getenv("NEON_DATABASE_URL")
    if neon_db_url:
        db_url_to_use = neon_db_url.strip().strip('"').strip("'")
        print("☁️  Using NEON_DATABASE_URL (Production)")
    else:
        # Handle Docker service name when running from host
        db_url_to_use = settings.database_url
        if 'postgres:' in db_url_to_use and 'localhost' not in db_url_to_use and '127.0.0.1' not in db_url_to_use:
            db_url_to_use = db_url_to_use.replace('postgres:', 'localhost:')
            print("Note: Using localhost instead of Docker service name for connection")
        print("💻 Using DATABASE_URL (Local)")
    
    print(
        f"Database: {db_url_to_use.split('@')[-1] if '@' in db_url_to_use else db_url_to_use}"
    )
    print()

    # Create a temporary engine for this migration
    temp_engine = create_async_engine(
        db_url_to_use,
        echo=False,
        future=True
    )
    TempAsyncSessionLocal = async_sessionmaker(
        temp_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with TempAsyncSessionLocal() as session:
        try:
            # ------------------------------------------------------------------
            # Step 1: Create study_sites table
            # ------------------------------------------------------------------
            print("  Creating study_sites table...")
            create_study_sites_table = """
                CREATE TABLE IF NOT EXISTS study_sites (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    study_id UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
                    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_study_site UNIQUE (study_id, site_id)
                )
            """
            
            create_study_sites_indexes = [
                "CREATE INDEX IF NOT EXISTS ix_study_sites_study_id ON study_sites (study_id)",
                "CREATE INDEX IF NOT EXISTS ix_study_sites_site_id ON study_sites (site_id)",
            ]
            
            await session.execute(text(create_study_sites_table))
            for index_sql in create_study_sites_indexes:
                await session.execute(text(index_sql))
            
            await session.commit()
            print("    ✓ study_sites table created")
            
            # ------------------------------------------------------------------
            # Step 2: Populate study_sites from existing site-study relationships
            # ------------------------------------------------------------------
            print("  Populating study_sites from existing sites...")
            populate_study_sites = """
                INSERT INTO study_sites (study_id, site_id)
                SELECT DISTINCT study_id, id as site_id
                FROM sites
                WHERE NOT EXISTS (
                    SELECT 1 FROM study_sites ss 
                    WHERE ss.study_id = sites.study_id AND ss.site_id = sites.id
                )
            """
            result = await session.execute(text(populate_study_sites))
            await session.commit()
            print(f"    ✓ Created {result.rowcount} study_site mappings")
            
            # ------------------------------------------------------------------
            # Step 3: Add study_site_id column to site_workflow_steps (if not exists)
            # ------------------------------------------------------------------
            print("  Adding study_site_id column to site_workflow_steps...")
            add_study_site_id_column = """
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'site_workflow_steps' 
                        AND column_name = 'study_site_id'
                    ) THEN
                        ALTER TABLE site_workflow_steps 
                        ADD COLUMN study_site_id UUID REFERENCES study_sites(id) ON DELETE CASCADE;
                    END IF;
                END $$;
            """
            await session.execute(text(add_study_site_id_column))
            await session.commit()
            print("    ✓ study_site_id column added")
            
            # ------------------------------------------------------------------
            # Step 4: Make site_id nullable (for study-specific steps)
            # ------------------------------------------------------------------
            print("  Making site_id nullable in site_workflow_steps...")
            make_site_id_nullable = """
                DO $$ 
                BEGIN
                    -- Check if site_id is currently NOT NULL
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'site_workflow_steps' 
                        AND column_name = 'site_id'
                        AND is_nullable = 'NO'
                    ) THEN
                        ALTER TABLE site_workflow_steps 
                        ALTER COLUMN site_id DROP NOT NULL;
                    END IF;
                END $$;
            """
            await session.execute(text(make_site_id_nullable))
            await session.commit()
            print("    ✓ site_id made nullable")
            
            # ------------------------------------------------------------------
            # Step 5: Migrate existing workflow steps to use study_site_id
            # ------------------------------------------------------------------
            print("  Migrating existing workflow steps to study_site_id...")
            migrate_workflow_steps = """
                UPDATE site_workflow_steps sws
                SET study_site_id = ss.id
                FROM sites s
                JOIN study_sites ss ON ss.site_id = s.id AND ss.study_id = s.study_id
                WHERE sws.site_id = s.id
                AND sws.study_site_id IS NULL
                AND sws.step_name IN ('site_identification', 'cda_execution', 'feasibility', 'site_selection_outcome')
            """
            result = await session.execute(text(migrate_workflow_steps))
            await session.commit()
            print(f"    ✓ Migrated {result.rowcount} workflow steps to use study_site_id")
            
            # ------------------------------------------------------------------
            # Step 6: Create index on study_site_id
            # ------------------------------------------------------------------
            print("  Creating index on study_site_id...")
            create_index = """
                CREATE INDEX IF NOT EXISTS ix_site_workflow_steps_study_site_id 
                ON site_workflow_steps (study_site_id)
            """
            await session.execute(text(create_index))
            await session.commit()
            print("    ✓ Index created")
            
            # ------------------------------------------------------------------
            # Step 7: Update unique constraint to handle both site_id and study_site_id
            # ------------------------------------------------------------------
            print("  Updating unique constraints...")
            # Drop old constraint if it exists
            drop_old_constraint = """
                DO $$ 
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint 
                        WHERE conname = 'uq_site_workflow_step'
                    ) THEN
                        ALTER TABLE site_workflow_steps 
                        DROP CONSTRAINT uq_site_workflow_step;
                    END IF;
                END $$;
            """
            await session.execute(text(drop_old_constraint))
            
            # Create new constraints
            # For study-specific steps: unique on (study_site_id, step_name)
            create_study_site_constraint = """
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint 
                        WHERE conname = 'uq_study_site_workflow_step'
                    ) THEN
                        CREATE UNIQUE INDEX uq_study_site_workflow_step 
                        ON site_workflow_steps (study_site_id, step_name)
                        WHERE study_site_id IS NOT NULL;
                    END IF;
                END $$;
            """
            await session.execute(text(create_study_site_constraint))
            
            # For site-level steps: unique on (site_id, step_name)
            create_site_constraint = """
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint 
                        WHERE conname = 'uq_site_workflow_step'
                    ) THEN
                        CREATE UNIQUE INDEX uq_site_workflow_step 
                        ON site_workflow_steps (site_id, step_name)
                        WHERE site_id IS NOT NULL;
                    END IF;
                END $$;
            """
            await session.execute(text(create_site_constraint))
            await session.commit()
            print("    ✓ Unique constraints updated")
            
            print()
            print("=" * 70)
            print("[SUCCESS] Study-site mapping migration completed successfully.")
            print("=" * 70)

        except Exception as e:
            await session.rollback()
            print()
            print("=" * 70)
            print(f"[ERROR] Failed to migrate: {e}")
            print("=" * 70)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            await temp_engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_study_site_mapping())
