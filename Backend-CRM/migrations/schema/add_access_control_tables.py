"""
Migration script to add access control features to conversations.
This adds:
1. New columns to conversations table (is_restricted, is_confidential, etc.)
2. Users table
3. ConversationAccess table

Run this script to add the new tables and columns.
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

async def add_access_control_tables():
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
    print("Starting database migration for access control...")
    
    async with TempAsyncSessionLocal() as session:
        try:
            # 1. Add columns to conversations table
            print("\n1. Adding columns to conversations table...")
            
            # Check existing columns
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = current_schema() 
                AND table_name = 'conversations'
            """)
            result = await session.execute(check_query)
            existing_columns = [row[0] for row in result.fetchall()]
            
            columns_to_add = {
                'is_restricted': "ALTER TABLE conversations ADD COLUMN is_restricted VARCHAR(10) NOT NULL DEFAULT 'false'",
                'is_confidential': "ALTER TABLE conversations ADD COLUMN is_confidential VARCHAR(10) NOT NULL DEFAULT 'false'",
                'created_by': "ALTER TABLE conversations ADD COLUMN created_by VARCHAR(255)",
                'sponsor_id': "ALTER TABLE conversations ADD COLUMN sponsor_id VARCHAR(255)",
                'access_level': "ALTER TABLE conversations ADD COLUMN access_level VARCHAR(50) NOT NULL DEFAULT 'public'",
                'privileged_users': "ALTER TABLE conversations ADD COLUMN privileged_users JSONB DEFAULT '[]'::jsonb"
            }
            
            for col_name, alter_sql in columns_to_add.items():
                if col_name not in existing_columns:
                    print(f"  Adding {col_name} column...")
                    await session.execute(text(alter_sql))
                    print(f"    [OK] {col_name} column added")
                else:
                    print(f"  [SKIP] {col_name} column already exists")
            
            # 2. Create users table
            print("\n2. Creating users table...")
            check_table = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = current_schema() 
                    AND table_name = 'users'
                )
            """)
            result = await session.execute(check_table)
            table_exists = result.scalar()
            
            if not table_exists:
                print("  Creating users table...")
                await session.execute(text("""
                    CREATE TABLE users (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id VARCHAR(255) UNIQUE NOT NULL,
                        name VARCHAR(255),
                        email VARCHAR(255),
                        role VARCHAR(50) NOT NULL DEFAULT 'participant',
                        is_privileged VARCHAR(10) NOT NULL DEFAULT 'false',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                print("    [OK] users table created")
                
                # Create index
                await session.execute(text("CREATE INDEX idx_users_user_id ON users(user_id)"))
                print("    [OK] Index created on user_id")
            else:
                print("  [SKIP] users table already exists")
            
            # 3. Create conversation_access table
            print("\n3. Creating conversation_access table...")
            check_table = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = current_schema() 
                    AND table_name = 'conversation_access'
                )
            """)
            result = await session.execute(check_table)
            table_exists = result.scalar()
            
            if not table_exists:
                print("  Creating conversation_access table...")
                await session.execute(text("""
                    CREATE TABLE conversation_access (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                        user_id VARCHAR(255) NOT NULL,
                        access_type VARCHAR(50) NOT NULL DEFAULT 'read',
                        granted_by VARCHAR(255),
                        granted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                print("    [OK] conversation_access table created")
                
                # Create indexes
                await session.execute(text("CREATE INDEX idx_conv_access_conv_id ON conversation_access(conversation_id)"))
                await session.execute(text("CREATE INDEX idx_conv_access_user_id ON conversation_access(user_id)"))
                print("    [OK] Indexes created")
            else:
                print("  [SKIP] conversation_access table already exists")
            
            await session.commit()
            print("\n[SUCCESS] Database migration completed!")
            print("   Access control features are now available.")
            
        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] Migration failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            await temp_engine.dispose()

if __name__ == "__main__":
    asyncio.run(add_access_control_tables())

