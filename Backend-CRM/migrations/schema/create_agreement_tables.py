"""
Database migration script to create Agreement Workflow tables.

This script creates:
- agreements (main agreement table)
- agreement_versions (version history)
- agreement_comments (comments and system logging)

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


async def create_agreement_tables():
    """Create agreement workflow tables (additive, idempotent)."""
    print("=" * 70)
    print("Agreement Workflow Tables Migration")
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
            # Create ENUM types
            # ------------------------------------------------------------------
            create_agreement_status_type = """
                DO $$ BEGIN
                    CREATE TYPE agreement_status AS ENUM (
                        'DRAFT',
                        'UNDER_REVIEW',
                        'UNDER_NEGOTIATION',
                        'READY_FOR_SIGNATURE',
                        'SENT_FOR_SIGNATURE',
                        'EXECUTED',
                        'CLOSED'
                    );
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """
            
            create_comment_type_enum = """
                DO $$ BEGIN
                    CREATE TYPE comment_type AS ENUM (
                        'INTERNAL',
                        'EXTERNAL',
                        'SYSTEM'
                    );
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """
            
            print("  Creating enum types (if needed)...")
            await session.execute(text(create_agreement_status_type))
            await session.execute(text(create_comment_type_enum))
            await session.commit()
            
            # ------------------------------------------------------------------
            # Create agreements table
            # ------------------------------------------------------------------
            create_agreements_table = """
                CREATE TABLE IF NOT EXISTS agreements (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
                    title VARCHAR(500) NOT NULL,
                    status agreement_status NOT NULL DEFAULT 'DRAFT',
                    created_by VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    current_version_id UUID
                )
            """
            
            create_agreements_indexes = [
                "CREATE INDEX IF NOT EXISTS ix_agreements_site_id ON agreements (site_id)",
                "CREATE INDEX IF NOT EXISTS ix_agreements_status ON agreements (status)",
                "CREATE INDEX IF NOT EXISTS ix_agreements_created_at ON agreements (created_at DESC)",
            ]
            
            # ------------------------------------------------------------------
            # Create agreement_versions table
            # ------------------------------------------------------------------
            create_agreement_versions_table = """
                CREATE TABLE IF NOT EXISTS agreement_versions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    agreement_id UUID NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
                    version_number INTEGER NOT NULL,
                    file_path VARCHAR(500),
                    document_html TEXT,
                    uploaded_by VARCHAR(255),
                    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    is_signed_version VARCHAR(10) NOT NULL DEFAULT 'false',
                    is_external_visible VARCHAR(10) NOT NULL DEFAULT 'false',
                    CONSTRAINT uq_agreement_version UNIQUE (agreement_id, version_number)
                )
            """
            
            create_agreement_versions_indexes = [
                "CREATE INDEX IF NOT EXISTS ix_agreement_versions_agreement_id ON agreement_versions (agreement_id)",
                "CREATE INDEX IF NOT EXISTS ix_agreement_versions_version_number ON agreement_versions (agreement_id, version_number)",
            ]
            
            # ------------------------------------------------------------------
            # Create agreement_comments table
            # ------------------------------------------------------------------
            create_agreement_comments_table = """
                CREATE TABLE IF NOT EXISTS agreement_comments (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    agreement_id UUID NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
                    version_id UUID REFERENCES agreement_versions(id) ON DELETE SET NULL,
                    comment_type comment_type NOT NULL,
                    content TEXT NOT NULL,
                    created_by VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """
            
            create_agreement_comments_indexes = [
                "CREATE INDEX IF NOT EXISTS ix_agreement_comments_agreement_id ON agreement_comments (agreement_id)",
                "CREATE INDEX IF NOT EXISTS ix_agreement_comments_version_id ON agreement_comments (version_id)",
                "CREATE INDEX IF NOT EXISTS ix_agreement_comments_created_at ON agreement_comments (created_at DESC)",
            ]
            
            # ------------------------------------------------------------------
            # Add foreign key constraint for current_version_id
            # ------------------------------------------------------------------
            add_current_version_fk = """
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint 
                        WHERE conname = 'fk_agreements_current_version'
                    ) THEN
                        ALTER TABLE agreements 
                        ADD CONSTRAINT fk_agreements_current_version 
                        FOREIGN KEY (current_version_id) 
                        REFERENCES agreement_versions(id) 
                        ON DELETE SET NULL;
                    END IF;
                END $$;
            """
            
            print("  Creating tables (if needed)...")
            await session.execute(text(create_agreements_table))
            await session.execute(text(create_agreement_versions_table))
            await session.execute(text(create_agreement_comments_table))
            
            print("  Adding foreign key constraints (if needed)...")
            await session.execute(text(add_current_version_fk))
            
            print("  Creating indexes (if needed)...")
            for index_sql in create_agreements_indexes:
                await session.execute(text(index_sql))
            for index_sql in create_agreement_versions_indexes:
                await session.execute(text(index_sql))
            for index_sql in create_agreement_comments_indexes:
                await session.execute(text(index_sql))

            await session.commit()
            print()
            print("=" * 70)
            print("[SUCCESS] Agreement workflow tables created / verified successfully.")
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
    asyncio.run(create_agreement_tables())
