"""
Migration script to add is_external_visible column to agreement_versions table.
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


async def add_external_visible_column():
    """Add is_external_visible column to agreement_versions table."""
    print("=" * 70)
    print("Adding is_external_visible column to agreement_versions")
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
            # Add column if it doesn't exist
            add_column_sql = """
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'agreement_versions' 
                        AND column_name = 'is_external_visible'
                    ) THEN
                        ALTER TABLE agreement_versions 
                        ADD COLUMN is_external_visible VARCHAR(10) NOT NULL DEFAULT 'false';
                    END IF;
                END $$;
            """
            
            print("  Adding is_external_visible column (if needed)...")
            await session.execute(text(add_column_sql))
            await session.commit()
            
            print()
            print("=" * 70)
            print("[SUCCESS] Column added / verified successfully.")
            print("=" * 70)

        except Exception as e:
            await session.rollback()
            print()
            print("=" * 70)
            print(f"[ERROR] Failed to add column: {e}")
            print("=" * 70)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            await temp_engine.dispose()


if __name__ == "__main__":
    asyncio.run(add_external_visible_column())
