"""
Database migration script to create feasibility request and response tables.

Run this script to add the feasibility_requests and feasibility_responses tables to your database.

Usage:
    python create_feasibility_request_tables.py
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


async def create_feasibility_request_tables():
    """Create feasibility_requests and feasibility_responses tables (additive, idempotent)."""
    print("=" * 70)
    print("Feasibility Request Tables Migration")
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
            # Check if tables already exist
            check_requests_sql = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'feasibility_requests'
                )
            """)
            result = await session.execute(check_requests_sql)
            requests_table_exists = result.scalar()

            check_responses_sql = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'feasibility_responses'
                )
            """)
            result = await session.execute(check_responses_sql)
            responses_table_exists = result.scalar()

            if requests_table_exists and responses_table_exists:
                print("✅ Tables 'feasibility_requests' and 'feasibility_responses' already exist")
                print("   Skipping table creation.")
                await session.commit()
                return

            # Create feasibility_requests table
            if not requests_table_exists:
                print("📝 Creating table 'feasibility_requests'...")
                create_requests_table_sql = text("""
                    CREATE TABLE feasibility_requests (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        study_site_id UUID NOT NULL,
                        email VARCHAR(255) NOT NULL,
                        token VARCHAR(255) UNIQUE NOT NULL,
                        status VARCHAR(50) NOT NULL DEFAULT 'sent',
                        expires_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        
                        CONSTRAINT fk_feasibility_requests_study_site
                            FOREIGN KEY(study_site_id) 
                            REFERENCES study_sites(id)
                            ON DELETE CASCADE
                    )
                """)
                await session.execute(create_requests_table_sql)
                print("✅ Table 'feasibility_requests' created successfully!")

                # Create indexes for feasibility_requests
                print("📝 Creating indexes for 'feasibility_requests'...")
                indexes = [
                    "CREATE INDEX ix_feasibility_requests_study_site_id ON feasibility_requests (study_site_id)",
                    "CREATE INDEX ix_feasibility_requests_token ON feasibility_requests (token)",
                    "CREATE INDEX ix_feasibility_requests_status ON feasibility_requests (status)",
                    "CREATE INDEX ix_feasibility_requests_email ON feasibility_requests (email)",
                ]
                for index_sql in indexes:
                    await session.execute(text(index_sql))
                print("✅ Indexes for 'feasibility_requests' created successfully!")

            # Create feasibility_responses table
            if not responses_table_exists:
                print("📝 Creating table 'feasibility_responses'...")
                create_responses_table_sql = text("""
                    CREATE TABLE feasibility_responses (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        request_id UUID NOT NULL,
                        question_text TEXT NOT NULL,
                        question_id UUID,
                        answer TEXT NOT NULL,
                        section VARCHAR(255),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        
                        CONSTRAINT fk_feasibility_responses_request
                            FOREIGN KEY(request_id) 
                            REFERENCES feasibility_requests(id)
                            ON DELETE CASCADE
                    )
                """)
                await session.execute(create_responses_table_sql)
                print("✅ Table 'feasibility_responses' created successfully!")

                # Create indexes for feasibility_responses
                print("📝 Creating indexes for 'feasibility_responses'...")
                indexes = [
                    "CREATE INDEX ix_feasibility_responses_request_id ON feasibility_responses (request_id)",
                    "CREATE INDEX ix_feasibility_responses_question_id ON feasibility_responses (question_id)",
                ]
                for index_sql in indexes:
                    await session.execute(text(index_sql))
                print("✅ Indexes for 'feasibility_responses' created successfully!")

            await session.commit()
            print()
            print("=" * 70)
            print("✅ Migration completed successfully!")
            print("=" * 70)

        except Exception as e:
            await session.rollback()
            print(f"❌ Error creating tables: {e}")
            print(f"   Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            await temp_engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_feasibility_request_tables())
