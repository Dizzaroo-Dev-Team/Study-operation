"""
Migration script to fix study_templates table schema:
1. Make document_html nullable (it's a legacy field)
2. Add template_content JSONB column if missing
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


async def fix_template_schema():
    """Fix study_templates table schema to make document_html nullable and add template_content."""
    print("=" * 70)
    print("Fixing Template Schema")
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
            # Add template_content column if missing
            # ------------------------------------------------------------------
            add_template_content_column = """
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'study_templates' 
                        AND column_name = 'template_content'
                    ) THEN
                        ALTER TABLE study_templates 
                        ADD COLUMN template_content JSONB NOT NULL DEFAULT '{}'::jsonb;
                    END IF;
                END $$;
            """
            
            print("  Adding template_content column to study_templates (if needed)...")
            await session.execute(text(add_template_content_column))
            await session.commit()
            
            # ------------------------------------------------------------------
            # Make document_html nullable
            # ------------------------------------------------------------------
            make_document_html_nullable = """
                DO $$ 
                BEGIN
                    -- Check if column exists and is NOT NULL
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'study_templates' 
                        AND column_name = 'document_html'
                        AND is_nullable = 'NO'
                    ) THEN
                        -- First, set any NULL values to empty string
                        UPDATE study_templates 
                        SET document_html = '' 
                        WHERE document_html IS NULL;
                        
                        -- Then alter column to allow NULL
                        ALTER TABLE study_templates 
                        ALTER COLUMN document_html DROP NOT NULL;
                        
                        RAISE NOTICE 'Made document_html nullable';
                    ELSE
                        RAISE NOTICE 'document_html is already nullable or does not exist';
                    END IF;
                END $$;
            """
            
            print("  Making document_html nullable (if needed)...")
            await session.execute(text(make_document_html_nullable))
            await session.commit()
            
            print()
            print("=" * 70)
            print("[SUCCESS] Schema fixes applied successfully.")
            print("=" * 70)

        except Exception as e:
            await session.rollback()
            print()
            print("=" * 70)
            print(f"[ERROR] Failed to fix schema: {e}")
            print("=" * 70)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            await temp_engine.dispose()


if __name__ == "__main__":
    asyncio.run(fix_template_schema())
