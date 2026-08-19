"""
Database migration script to create site workflow and documents tables.

This script is ADDITIVE ONLY – it does not modify or remove any existing
tables or columns. It introduces:

- site_workflow_steps    (workflow step state per site)
- site_documents         (document storage per site)

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


async def create_site_workflow_tables():
    """Create site workflow and documents tables (additive, idempotent)."""
    print("=" * 70)
    print("Site Workflow & Documents Tables Migration")
    print("=" * 70)
    
    # Handle Docker service name when running from host
    db_url_to_use = settings.database_url
    if 'postgres:' in db_url_to_use and 'localhost' not in db_url_to_use and '127.0.0.1' not in db_url_to_use:
        db_url_to_use = db_url_to_use.replace('postgres:', 'localhost:')
        print("Note: Using localhost instead of Docker service name for connection")
    
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
            # site_workflow_steps – workflow step state per site
            # ------------------------------------------------------------------
            # Check and create types if they don't exist (execute separately)
            create_workflow_step_name_type = """
                DO $$ BEGIN
                    CREATE TYPE workflow_step_name AS ENUM (
                        'site_identification',
                        'cda_execution',
                        'feasibility',
                        'site_selection_outcome'
                    );
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """
            
            create_step_status_type = """
                DO $$ BEGIN
                    CREATE TYPE step_status AS ENUM (
                        'not_started',
                        'in_progress',
                        'completed',
                        'locked'
                    );
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """
            
            create_workflow_steps_table = """
                CREATE TABLE IF NOT EXISTS site_workflow_steps (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
                    step_name workflow_step_name NOT NULL,
                    status step_status NOT NULL DEFAULT 'not_started',
                    step_data JSONB DEFAULT '{}'::JSONB,
                    completed_at TIMESTAMP WITH TIME ZONE,
                    completed_by VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_site_workflow_step UNIQUE (site_id, step_name)
                )
            """
            
            create_workflow_steps_indexes = [
                "CREATE INDEX IF NOT EXISTS ix_site_workflow_steps_site_id ON site_workflow_steps (site_id)",
                "CREATE INDEX IF NOT EXISTS ix_site_workflow_steps_step_name ON site_workflow_steps (step_name)",
                "CREATE INDEX IF NOT EXISTS ix_site_workflow_steps_status ON site_workflow_steps (status)",
            ]

            # ------------------------------------------------------------------
            # site_documents – document storage per site
            # ------------------------------------------------------------------
            create_document_category_type = """
                DO $$ BEGIN
                    CREATE TYPE document_category AS ENUM (
                        'investigator_cv',
                        'signed_cda',
                        'cta',
                        'irb_package',
                        'feasibility_questionnaire',
                        'feasibility_response',
                        'onsite_visit_report',
                        'site_visibility_report',
                        'other'
                    );
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """
            
            create_site_documents_table = """
                CREATE TABLE IF NOT EXISTS site_documents (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
                    category document_category NOT NULL,
                    file_path VARCHAR(500) NOT NULL,
                    file_name VARCHAR(255) NOT NULL,
                    content_type VARCHAR(100) NOT NULL,
                    size INTEGER NOT NULL,
                    uploaded_by VARCHAR(255),
                    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    description TEXT,
                    metadata JSONB DEFAULT '{}'::JSONB
                )
            """
            
            create_site_documents_indexes = [
                "CREATE INDEX IF NOT EXISTS ix_site_documents_site_id ON site_documents (site_id)",
                "CREATE INDEX IF NOT EXISTS ix_site_documents_category ON site_documents (category)",
                "CREATE INDEX IF NOT EXISTS ix_site_documents_uploaded_at ON site_documents (uploaded_at DESC)",
            ]

            print("  Creating site_workflow_steps and site_documents (if needed)...")
            
            # Create types first (using DO blocks for IF NOT EXISTS) - execute separately
            await session.execute(text(create_workflow_step_name_type))
            await session.execute(text(create_step_status_type))
            await session.execute(text(create_document_category_type))
            
            # Create tables
            await session.execute(text(create_workflow_steps_table))
            await session.execute(text(create_site_documents_table))
            
            # Create indexes separately
            for index_sql in create_workflow_steps_indexes:
                await session.execute(text(index_sql))
            for index_sql in create_site_documents_indexes:
                await session.execute(text(index_sql))

            await session.commit()
            print()
            print("=" * 70)
            print("[SUCCESS] Site workflow and documents tables created / verified successfully.")
            print("=" * 70)

        except Exception as e:
            await session.rollback()
            print()
            print("=" * 70)
            print(f"[ERROR] Failed to create tables: {e}")
            print("=" * 70)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            await temp_engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_site_workflow_tables())
