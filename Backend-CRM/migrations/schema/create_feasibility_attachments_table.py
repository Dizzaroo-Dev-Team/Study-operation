"""
Database migration script to create feasibility_attachments table.

Run this script to add the feasibility_attachments table to your database.

Usage:
    python create_feasibility_attachments_table.py
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


async def create_feasibility_attachments_table():
    """Create feasibility_attachments table (additive, idempotent)."""
    print("=" * 70)
    print("Feasibility Attachments Table Migration")
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
            # Check if table already exists
            check_sql = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'feasibility_attachments'
                )
            """)
            result = await session.execute(check_sql)
            table_exists = result.scalar()

            if table_exists:
                print("✅ Table 'feasibility_attachments' already exists")
                print("   Skipping table creation.")
                await session.commit()
                return

            print("📝 Creating table 'feasibility_attachments'...")

            # Create the table
            create_table_sql = text("""
                CREATE TABLE feasibility_attachments (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    study_site_id UUID NOT NULL UNIQUE,
                    file_path VARCHAR(500) NOT NULL,
                    file_name VARCHAR(255) NOT NULL,
                    content_type VARCHAR(100) NOT NULL,
                    size INTEGER NOT NULL,
                    uploaded_by VARCHAR(255),
                    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    
                    CONSTRAINT fk_feasibility_attachments_study_site
                        FOREIGN KEY(study_site_id) 
                        REFERENCES study_sites(id)
                        ON DELETE CASCADE
                )
            """)
            await session.execute(create_table_sql)
            print("✅ Table 'feasibility_attachments' created successfully!")

            # Create indexes
            print("📝 Creating indexes...")
            indexes = [
                "CREATE INDEX ix_feasibility_attachments_study_site_id ON feasibility_attachments (study_site_id)",
            ]
            for index_sql in indexes:
                await session.execute(text(index_sql))
            print("✅ Indexes created successfully!")

            await session.commit()
            print()
            print("=" * 70)
            print("✅ Migration completed successfully!")
            print("=" * 70)

        except Exception as e:
            await session.rollback()
            print(f"❌ Error creating table: {e}")
            print(f"   Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            await temp_engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_feasibility_attachments_table())
