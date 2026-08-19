"""
Migration script to create study_templates and agreement_documents tables,
and add is_legacy field to agreements table.
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


async def create_template_tables():
    """Create study_templates and agreement_documents tables, and update agreements table."""
    print("=" * 70)
    print("Creating Template and Agreement Document Tables")
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
            # Create template_type enum
            # ------------------------------------------------------------------
            create_template_type_enum = """
                DO $$ BEGIN
                    CREATE TYPE template_type AS ENUM (
                        'CDA',
                        'CTA',
                        'BUDGET',
                        'OTHER'
                    );
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """
            
            print("  Creating template_type enum (if needed)...")
            await session.execute(text(create_template_type_enum))
            await session.commit()
            
            # ------------------------------------------------------------------
            # Add is_legacy column to agreements table
            # ------------------------------------------------------------------
            add_is_legacy_column = """
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'agreements' 
                        AND column_name = 'is_legacy'
                    ) THEN
                        ALTER TABLE agreements 
                        ADD COLUMN is_legacy VARCHAR(10) NOT NULL DEFAULT 'false';
                    END IF;
                END $$;
            """
            
            print("  Adding is_legacy column to agreements table (if needed)...")
            await session.execute(text(add_is_legacy_column))
            await session.commit()
            
            # ------------------------------------------------------------------
            # Create study_templates table
            # ------------------------------------------------------------------
            create_study_templates_table = """
                CREATE TABLE IF NOT EXISTS study_templates (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    study_id UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
                    template_name VARCHAR(255) NOT NULL,
                    template_type template_type NOT NULL,
                    document_html TEXT NOT NULL,
                    created_by VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    is_active VARCHAR(10) NOT NULL DEFAULT 'true',
                    CONSTRAINT chk_study_template_is_active CHECK (is_active IN ('true', 'false'))
                );
            """
            
            print("  Creating study_templates table (if needed)...")
            await session.execute(text(create_study_templates_table))
            await session.commit()
            
            # ------------------------------------------------------------------
            # Create agreement_documents table
            # ------------------------------------------------------------------
            create_agreement_documents_table = """
                CREATE TABLE IF NOT EXISTS agreement_documents (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    agreement_id UUID NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
                    version_number INTEGER NOT NULL,
                    document_html TEXT NOT NULL,
                    created_from_template_id UUID REFERENCES study_templates(id) ON DELETE SET NULL,
                    created_by VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    is_signed_version VARCHAR(10) NOT NULL DEFAULT 'false',
                    CONSTRAINT uq_agreement_document_version UNIQUE (agreement_id, version_number),
                    CONSTRAINT chk_agreement_document_is_signed CHECK (is_signed_version IN ('true', 'false'))
                );
            """
            
            print("  Creating agreement_documents table (if needed)...")
            await session.execute(text(create_agreement_documents_table))
            await session.commit()
            
            # ------------------------------------------------------------------
            # Create indexes
            # ------------------------------------------------------------------
            create_indexes = [
                "CREATE INDEX IF NOT EXISTS idx_study_templates_study_id ON study_templates(study_id);",
                "CREATE INDEX IF NOT EXISTS idx_study_templates_is_active ON study_templates(is_active);",
                "CREATE INDEX IF NOT EXISTS idx_agreement_documents_agreement_id ON agreement_documents(agreement_id);",
                "CREATE INDEX IF NOT EXISTS idx_agreement_documents_template_id ON agreement_documents(created_from_template_id);",
            ]
            
            print("  Creating indexes (if needed)...")
            for index_sql in create_indexes:
                await session.execute(text(index_sql))
            await session.commit()
            
            print()
            print("=" * 70)
            print("[SUCCESS] Tables created / verified successfully.")
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
    asyncio.run(create_template_tables())
