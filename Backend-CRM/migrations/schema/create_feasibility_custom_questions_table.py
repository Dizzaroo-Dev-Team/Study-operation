"""
Database migration script to create feasibility custom questions table.

Run this script to add the project_feasibility_custom_questions table to your database.

Usage:
    python create_feasibility_custom_questions_table.py
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


async def create_feasibility_custom_questions_table():
    """Create project_feasibility_custom_questions table (additive, idempotent)."""
    print("=" * 70)
    print("Feasibility Custom Questions Table Migration")
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
                    AND table_name = 'project_feasibility_custom_questions'
                )
            """)
            result = await session.execute(check_sql)
            table_exists = result.scalar()

            if table_exists:
                print("✅ Table 'project_feasibility_custom_questions' already exists")
                print("   Skipping table creation.")
                await session.commit()
                return

            print("📝 Creating table 'project_feasibility_custom_questions'...")

            # Create the table
            create_table_sql = text("""
                CREATE TABLE project_feasibility_custom_questions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    study_id UUID NOT NULL,
                    workflow_step VARCHAR(50) NOT NULL DEFAULT 'feasibility',
                    question_text TEXT NOT NULL,
                    section VARCHAR(255),
                    expected_response_type VARCHAR(50),
                    display_order INTEGER NOT NULL DEFAULT 0,
                    created_by VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    
                    CONSTRAINT fk_project_feasibility_custom_questions_study
                        FOREIGN KEY(study_id) 
                        REFERENCES studies(id)
                        ON DELETE CASCADE
                )
            """)
            await session.execute(create_table_sql)

            # Create indexes
            print("📝 Creating indexes...")
            indexes = [
                "CREATE INDEX ix_project_feasibility_custom_questions_study_id ON project_feasibility_custom_questions (study_id)",
                "CREATE INDEX ix_project_feasibility_custom_questions_workflow_step ON project_feasibility_custom_questions (workflow_step)",
            ]

            for index_sql in indexes:
                await session.execute(text(index_sql))

            await session.commit()
            print("✅ Table 'project_feasibility_custom_questions' created successfully!")
            print("✅ Indexes created successfully!")

        except Exception as e:
            await session.rollback()
            print(f"❌ Error creating table: {e}")
            print(f"   Error type: {type(e).__name__}")
            sys.exit(1)
        finally:
            await temp_engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_feasibility_custom_questions_table())
