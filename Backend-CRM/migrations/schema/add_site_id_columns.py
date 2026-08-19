"""
Database migration script to add site_id columns to conversations and threads tables.
Run this script to add the site_id column to your database.
"""
import asyncio
import sys
from sqlalchemy import text
from app.db import AsyncSessionLocal
from app.config import settings


async def add_site_id_columns():
    """Add site_id columns to conversations and threads tables."""
    print("============================================================")
    print("Site ID Columns Migration")
    print("============================================================")
    print(f"Database: {settings.database_url.split('@')[-1]}")
    
    async with AsyncSessionLocal() as session:
        try:
            # Check if site_id column exists in conversations table
            check_conv = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'conversations' AND column_name = 'site_id'
                );
            """)
            result = await session.execute(check_conv)
            conv_has_site_id = result.scalar()
            
            if not conv_has_site_id:
                print("  Adding site_id column to conversations table...")
                await session.execute(text("ALTER TABLE conversations ADD COLUMN site_id VARCHAR(100);"))
                print("  [OK] site_id column added to conversations table!")
            else:
                print("  [SKIP] site_id column already exists in conversations table")
            
            # Check if site_id column exists in threads table
            check_thread = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'threads' AND column_name = 'site_id'
                );
            """)
            result = await session.execute(check_thread)
            thread_has_site_id = result.scalar()
            
            if not thread_has_site_id:
                print("  Adding site_id column to threads table...")
                await session.execute(text("ALTER TABLE threads ADD COLUMN site_id VARCHAR(100);"))
                print("  [OK] site_id column added to threads table!")
            else:
                print("  [SKIP] site_id column already exists in threads table")
            
            await session.commit()
            print("\n============================================================")
            print("[SUCCESS] All site_id columns added successfully!")
            print("============================================================")
            
        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] Failed to add columns: {e}")
            print("\nMake sure:")
            print("  1. Your database is running")
            print("  2. Database connection settings are correct")
            print("  3. You have proper permissions to alter tables")
            sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(add_site_id_columns())
    except KeyboardInterrupt:
        print("\nMigration interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        sys.exit(1)

