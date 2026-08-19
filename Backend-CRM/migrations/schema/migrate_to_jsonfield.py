"""
Migration script to add JSON fields to study_templates and agreement_documents tables.
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


async def migrate_to_jsonfield():
    """Add JSON fields to templates and documents tables."""
    print("=" * 70)
    print("Migrating to JSONField for Template and Document Storage")
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
            # Add template_content column to study_templates
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
                        ADD COLUMN template_content JSONB;
                    END IF;
                END $$;
            """
            
            print("  Adding template_content column to study_templates (if needed)...")
            await session.execute(text(add_template_content_column))
            await session.commit()
            
            # ------------------------------------------------------------------
            # Add document_content column to agreement_documents
            # ------------------------------------------------------------------
            add_document_content_column = """
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'agreement_documents' 
                        AND column_name = 'document_content'
                    ) THEN
                        ALTER TABLE agreement_documents 
                        ADD COLUMN document_content JSONB;
                    END IF;
                END $$;
            """
            
            print("  Adding document_content column to agreement_documents (if needed)...")
            await session.execute(text(add_document_content_column))
            await session.commit()
            
            # ------------------------------------------------------------------
            # Create agreement_inline_comments table
            # ------------------------------------------------------------------
            create_inline_comments_table = """
                CREATE TABLE IF NOT EXISTS agreement_inline_comments (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    agreement_id UUID NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
                    document_id UUID NOT NULL REFERENCES agreement_documents(id) ON DELETE CASCADE,
                    comment_text TEXT NOT NULL,
                    position_reference JSONB,
                    comment_type comment_type NOT NULL,
                    created_by VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """
            
            print("  Creating agreement_inline_comments table (if needed)...")
            await session.execute(text(create_inline_comments_table))
            await session.commit()
            
            # ------------------------------------------------------------------
            # Create indexes
            # ------------------------------------------------------------------
            create_indexes = [
                "CREATE INDEX IF NOT EXISTS idx_inline_comments_agreement_id ON agreement_inline_comments(agreement_id);",
                "CREATE INDEX IF NOT EXISTS idx_inline_comments_document_id ON agreement_inline_comments(document_id);",
            ]
            
            print("  Creating indexes (if needed)...")
            for index_sql in create_indexes:
                await session.execute(text(index_sql))
            await session.commit()
            
            print()
            print("=" * 70)
            print("[SUCCESS] Migration completed successfully.")
            print("=" * 70)
            print()
            print("Note: Existing document_html fields are preserved for legacy support.")
            print("New documents should use template_content/document_content (JSONB).")

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
    asyncio.run(migrate_to_jsonfield())
