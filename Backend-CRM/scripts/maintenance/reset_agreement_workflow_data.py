"""
Agreement Workflow Data Reset Script

This script safely resets ONLY agreement-related workflow data.
It does NOT affect:
- Users
- Sites
- Studies
- IAM tables
- Notice board
- Site status
- Any unrelated CRM tables

Only clears:
- Agreement
- AgreementVersion
- AgreementDocument
- AgreementComment
- AgreementInlineComment
- StudyTemplate

Usage:
    python reset_agreement_workflow_data.py --confirm-reset

Safety:
    - Requires explicit --confirm-reset flag
    - Does NOT drop tables
    - Does NOT alter schema
    - Only deletes rows
"""

import asyncio
import sys
import argparse
from pathlib import Path
from typing import Dict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings


# Tables to clear (in dependency order to respect foreign keys)
AGREEMENT_TABLES = [
    "agreement_inline_comments",  # Depends on agreement_documents
    "agreement_comments",           # Depends on agreements
    "agreement_documents",          # Depends on agreements and study_templates
    "agreement_versions",           # Depends on agreements
    "agreements",                   # Base table
    "study_templates",              # Independent but agreement-related
]


async def get_table_counts(session: AsyncSession) -> Dict[str, int]:
    """
    Get current row counts for agreement-related tables.
    """
    counts = {}
    for table in AGREEMENT_TABLES:
        try:
            result = await session.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            )
            counts[table] = result.scalar()
        except Exception as e:
            counts[table] = f"ERROR: {e}"
    return counts


async def reset_agreement_data(confirm: bool = False):
    """
    Reset agreement workflow data.
    
    Args:
        confirm: Must be True to proceed with reset
    """
    if not confirm:
        print("=" * 80)
        print("SAFETY CHECK FAILED")
        print("=" * 80)
        print()
        print("❌ Reset operation requires explicit confirmation.")
        print()
        print("To proceed, run:")
        print("  python reset_agreement_workflow_data.py --confirm-reset")
        print()
        print("This will delete ALL data from:")
        for table in AGREEMENT_TABLES:
            print(f"  - {table}")
        print()
        print("WARNING: This action cannot be undone!")
        print()
        sys.exit(1)
    
    print("=" * 80)
    print("AGREEMENT WORKFLOW DATA RESET")
    print("=" * 80)
    print()
    
    # Database connection
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
    )
    
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Get initial counts
        print("Current Data Counts:")
        print("-" * 80)
        initial_counts = await get_table_counts(session)
        for table, count in initial_counts.items():
            print(f"  {table}: {count} rows")
        print()
        
        total_rows = sum(
            count for count in initial_counts.values() 
            if isinstance(count, int)
        )
        
        if total_rows == 0:
            print("SUCCESS: No data to reset. All tables are already empty.")
            print()
            await engine.dispose()
            return
        
        print(f"WARNING: About to delete {total_rows} rows from {len(AGREEMENT_TABLES)} tables.")
        print()
        
        # Perform reset
        print("Starting reset operation...")
        print("-" * 80)
        
        deleted_counts = {}
        errors = []
        
        for table in AGREEMENT_TABLES:
            try:
                # Get count before deletion
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {table}")
                )
                before_count = result.scalar()
                
                # Delete all rows
                await session.execute(text(f"DELETE FROM {table}"))
                await session.commit()
                
                # Verify deletion
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {table}")
                )
                after_count = result.scalar()
                
                deleted_counts[table] = {
                    "before": before_count,
                    "after": after_count,
                    "deleted": before_count - after_count
                }
                
                print(f"  OK {table}: Deleted {before_count} rows")
                
            except Exception as e:
                errors.append((table, str(e)))
                print(f"  ERROR {table}: {e}")
                await session.rollback()
        
        print()
        
        # Summary
        print("=" * 80)
        print("RESET SUMMARY")
        print("=" * 80)
        print()
        
        if errors:
            print("WARNING: ERRORS ENCOUNTERED:")
            for table, error in errors:
                print(f"  ERROR {table}: {error}")
            print()
        
        print("Deletion Results:")
        print("-" * 80)
        total_deleted = 0
        for table, counts in deleted_counts.items():
            print(f"  {table}:")
            print(f"    Before: {counts['before']} rows")
            print(f"    After: {counts['after']} rows")
            print(f"    Deleted: {counts['deleted']} rows")
            total_deleted += counts['deleted']
        
        print()
        print(f"SUCCESS: Total rows deleted: {total_deleted}")
        print()
        
        # Verify final state
        print("Final Verification:")
        print("-" * 80)
        final_counts = await get_table_counts(session)
        all_empty = True
        for table, count in final_counts.items():
            if isinstance(count, int) and count > 0:
                all_empty = False
                print(f"  WARNING {table}: {count} rows remaining")
            else:
                print(f"  OK {table}: {count} rows")
        
        print()
        if all_empty:
            print("SUCCESS: Agreement workflow data reset successfully!")
            print()
            print("System is now ready for clean rebuild.")
            print("All agreement-related tables are empty.")
            print("Other CRM modules remain unaffected.")
        else:
            print("WARNING: Some tables still contain data.")
            print("Please review the errors above.")
        
        print()
        print("=" * 80)
    
    await engine.dispose()


def main():
    """
    Main entry point with argument parsing.
    """
    parser = argparse.ArgumentParser(
        description="Reset Agreement Workflow Data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview (will abort without confirmation)
  python reset_agreement_workflow_data.py
  
  # Execute reset
  python reset_agreement_workflow_data.py --confirm-reset

Safety:
  - Requires explicit --confirm-reset flag
  - Only deletes rows, does NOT drop tables
  - Only affects agreement-related tables
  - Other CRM data remains untouched
        """
    )
    
    parser.add_argument(
        "--confirm-reset",
        action="store_true",
        help="Explicit confirmation flag required to proceed with reset"
    )
    
    args = parser.parse_args()
    
    asyncio.run(reset_agreement_data(confirm=args.confirm_reset))


if __name__ == "__main__":
    main()
