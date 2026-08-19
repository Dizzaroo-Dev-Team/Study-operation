"""
Simple database migration script to create site_profile table using SQLAlchemy Base metadata.
Run this script to add the SiteProfile table to your database.
"""
import asyncio
import sys
from app.db import init_db, engine
from app.models import Base, SiteProfile

async def create_site_profile_table():
    """Create the site_profile table using SQLAlchemy Base metadata."""
    print("=" * 60)
    print("Site Profile Table Migration (Simple Method)")
    print("=" * 60)
    
    try:
        # Initialize database connection
        print("\nInitializing database connection...")
        await init_db()
        
        # Create all tables defined in Base (this will only create SiteProfile if it doesn't exist)
        print("Creating site_profiles table...")
        async with engine.begin() as conn:
            # Create only the SiteProfile table
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn, 
                    tables=[SiteProfile.__table__]
                )
            )
        
        print("[SUCCESS] Migration completed successfully!")
        print("The site_profiles table has been created.")
        
    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Close the engine
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_site_profile_table())
