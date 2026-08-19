"""
Migration script to add document_file_path column to agreement_documents table.

This allows storing DOCX files alongside JSON content for ONLYOFFICE integration.
"""

import asyncio
import sys
from sqlalchemy import text
from app.db import AsyncSessionLocal
from app.config import settings

async def add_document_file_path_column():
    """Add document_file_path column to agreement_documents table."""
    print("=" * 70)
    print("Add document_file_path to AgreementDocument Table Migration")
    print("=" * 70)
    db_url_display = settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url
    print(f"Database: {db_url_display}")
    print()

    async with AsyncSessionLocal() as session:
        try:
            # Check if column exists using direct SQL query (works with async)
            check_column_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'agreement_documents' 
                AND column_name = 'document_file_path'
            """)
            
            result = await session.execute(check_column_query)
            column_exists = result.scalar_one_or_none() is not None

            if not column_exists:
                print("  Adding 'document_file_path' column to 'agreement_documents' table...")
                await session.execute(text("""
                    ALTER TABLE agreement_documents
                    ADD COLUMN document_file_path TEXT;
                """))
                print("  ✅ 'document_file_path' column added successfully.")
            else:
                print("  ⚠️ 'document_file_path' column already exists. Skipping.")
            
            await session.commit()
            print("\n" + "=" * 70)
            print("[SUCCESS] Migration completed successfully!")
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
        asyncio.run(add_document_file_path_column())
    except KeyboardInterrupt:
        print("\nMigration interrupted by user.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nAn unexpected error occurred: {exc}")
        sys.exit(1)
