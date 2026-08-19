"""
Database migration script to add field_mappings column to study_templates table.
Run this script to add the field_mappings field to existing templates.
"""
import asyncio
import sys
from sqlalchemy import text
from app.db import AsyncSessionLocal
from app.config import settings


async def add_field_mappings_column():
    """Add field_mappings column to study_templates table."""
    print("=" * 70)
    print("Add field_mappings to study_templates")
    print("=" * 70)
    db_info = settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url
    print(f"Database: {db_info}")
    print()
    
    async with AsyncSessionLocal() as session:
        try:
            # Check if column already exists
            check_column = text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'study_templates' 
                    AND column_name = 'field_mappings'
                )
            """)
            result = await session.execute(check_column)
            column_exists = result.scalar()
            
            if column_exists:
                print("[INFO] Column field_mappings already exists. Skipping.")
            else:
                # Add field_mappings column
                add_column_sql = """
                    ALTER TABLE study_templates
                    ADD COLUMN field_mappings JSON;
                """
                await session.execute(text(add_column_sql))
                print("[SUCCESS] Column field_mappings added successfully.")
            
            await session.commit()
            print()
            print("=" * 70)
            print("[SUCCESS] Migration completed successfully.")
            print("=" * 70)
            
        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] Migration failed: {e}")
            import traceback
            traceback.print_exc()
            print("\nMake sure:")
            print("  1. Your database is running")
            print("  2. Database connection settings are correct")
            print("  3. You have permissions to alter tables")
            sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(add_field_mappings_column())
    except KeyboardInterrupt:
        print("\nMigration interrupted by user.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nAn unexpected error occurred: {exc}")
        sys.exit(1)
