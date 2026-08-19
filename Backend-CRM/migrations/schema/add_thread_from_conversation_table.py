"""
Migration script to add thread_from_conversations table.
Run this script to add the new table for linking threads created from conversations.
"""
import asyncio
import sys
import os
from pathlib import Path

from dotenv import load_dotenv
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

async def add_thread_from_conversation_table():
    db_url_to_use = settings.database_url
    if 'postgres:' in db_url_to_use and 'localhost' not in db_url_to_use and '127.0.0.1' not in db_url_to_use:
        db_url_to_use = db_url_to_use.replace('postgres:', 'localhost:')
        print("Note: Using localhost instead of Docker service name")
    
    print("Connecting to database...")
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

    print(f"Database URL: {db_url_to_use.replace('crm_pass@', '***@')}")
    print("Creating thread_from_conversations table...")
    
    async with TempAsyncSessionLocal() as session:
        try:
            # Check if table already exists
            check_query = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = current_schema() 
                    AND table_name = 'thread_from_conversations'
                )
            """)
            result = await session.execute(check_query)
            table_exists = result.scalar()
            
            if table_exists:
                print("[OK] Table thread_from_conversations already exists. No migration needed.")
                await session.commit()
                await temp_engine.dispose()
                return
            
            # Create the table
            print("  Creating thread_from_conversations table...")
            await session.execute(text("""
                CREATE TABLE thread_from_conversations (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    source_message_ids JSONB NOT NULL,
                    created_by VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            print("    [OK] Table created")
            
            # Create indexes
            print("  Creating indexes...")
            await session.execute(text("""
                CREATE INDEX idx_thread_from_conv_thread_id ON thread_from_conversations(thread_id)
            """))
            await session.execute(text("""
                CREATE INDEX idx_thread_from_conv_conversation_id ON thread_from_conversations(conversation_id)
            """))
            print("    [OK] Indexes created")
            
            await session.commit()
            print("\n[SUCCESS] Migration completed!")
            print("   The thread_from_conversations table has been created.")
            
        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] Migration failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            await temp_engine.dispose()

if __name__ == "__main__":
    asyncio.run(add_thread_from_conversation_table())

