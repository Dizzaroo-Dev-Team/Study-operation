"""
Database migration script to create thread_attachments table.
Run this script to add the thread_attachments table to your database.
"""
import asyncio
import sys
from sqlalchemy import text
from app.db import AsyncSessionLocal, engine
from app.config import settings


async def create_thread_attachments_table():
    """Create the thread_attachments table."""
    print("Creating thread_attachments table...")
    
    async with AsyncSessionLocal() as session:
        try:
            # Check if table already exists
            check_table = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'thread_attachments'
                );
            """)
            result = await session.execute(check_table)
            table_exists = result.scalar()
            
            if table_exists:
                print("  [WARNING] Table 'thread_attachments' already exists. Skipping creation.")
                return
            
            # Create table
            create_table = text("""
                CREATE TABLE thread_attachments (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                    thread_message_id UUID REFERENCES thread_messages(id) ON DELETE SET NULL,
                    attachment_id UUID NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    CONSTRAINT fk_thread_attachments_thread FOREIGN KEY (thread_id) REFERENCES threads(id),
                    CONSTRAINT fk_thread_attachments_message FOREIGN KEY (thread_message_id) REFERENCES thread_messages(id),
                    CONSTRAINT fk_thread_attachments_attachment FOREIGN KEY (attachment_id) REFERENCES attachments(id)
                );
            """)
            
            await session.execute(create_table)
            
            # Create indexes for better query performance
            create_indexes = text("""
                CREATE INDEX idx_thread_attachments_thread_id ON thread_attachments(thread_id);
                CREATE INDEX idx_thread_attachments_attachment_id ON thread_attachments(attachment_id);
                CREATE INDEX idx_thread_attachments_thread_message_id ON thread_attachments(thread_message_id);
            """)
            
            await session.execute(create_indexes)
            await session.commit()
            
            print("  [OK] Table 'thread_attachments' created successfully!")
            print("  [OK] Indexes created successfully!")
            
        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] Failed to create table: {e}")
            print("\nMake sure:")
            print("  1. Your database is running")
            print("  2. Database connection settings are correct")
            print("  3. You have proper permissions to create tables")
            sys.exit(1)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    print("=" * 60)
    print("Thread Attachments Table Migration")
    print("=" * 60)
    print(f"Database: {settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url}")
    print()
    
    asyncio.run(create_thread_attachments_table())
    
    print("\n" + "=" * 60)
    print("Migration completed!")
    print("=" * 60)

