"""
Copy studies and sites data from local database to Neon production database.

This script:
1. Reads all studies and sites from local database
2. Clears existing data in Neon (optional, can be disabled)
3. Inserts the data into Neon database

Usage:
    Set environment variables:
    - LOCAL_DATABASE_URL (or DATABASE_URL for local)
    - NEON_DATABASE_URL (for Neon production)
    
    Then run: python copy_studies_sites_to_neon.py
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


async def copy_studies_sites_to_neon():
    """Copy studies and sites from local to Neon."""
    print("=" * 70)
    print("Copy Studies & Sites: Local → Neon")
    print("=" * 70)
    print()
    
    # Get connection strings
    local_db_url = os.getenv("LOCAL_DATABASE_URL") or os.getenv("DATABASE_URL")
    neon_db_url = os.getenv("NEON_DATABASE_URL")
    
    if not local_db_url:
        print("❌ ERROR: LOCAL_DATABASE_URL or DATABASE_URL environment variable not set")
        print("   Example: postgresql+asyncpg://<user>:<password>@localhost:5432/crm_db")
        sys.exit(1)
    
    if not neon_db_url:
        print("❌ ERROR: NEON_DATABASE_URL environment variable not set")
        print("   Example: postgresql+asyncpg://user:pass@neon-host/dbname")
        sys.exit(1)
    
    # Clean URLs
    local_db_url = local_db_url.strip().strip('"').strip("'")
    neon_db_url = neon_db_url.strip().strip('"').strip("'")
    
    # Handle Docker service name for local
    if 'postgres:' in local_db_url and 'localhost' not in local_db_url and '127.0.0.1' not in local_db_url:
        local_db_url = local_db_url.replace('postgres:', 'localhost:')
        print("ℹ️  Converted 'postgres:' to 'localhost:' for local connection")
    
    print(f"📊 Local Database: {local_db_url.split('@')[-1] if '@' in local_db_url else local_db_url}")
    print(f"☁️  Neon Database: {neon_db_url.split('@')[-1] if '@' in neon_db_url else neon_db_url}")
    print()
    
    # Create engines
    local_engine = create_async_engine(local_db_url, echo=False)
    neon_engine = create_async_engine(neon_db_url, echo=False)
    
    local_session_maker = async_sessionmaker(local_engine, class_=AsyncSession, expire_on_commit=False)
    neon_session_maker = async_sessionmaker(neon_engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        # ------------------------------------------------------------------
        # Step 1: Read studies from local
        # ------------------------------------------------------------------
        print("📖 Reading studies from local database...")
        async with local_session_maker() as local_session:
            studies_query = text("""
                SELECT id, study_id, name, description, status, created_at, updated_at
                FROM studies
                ORDER BY created_at
            """)
            result = await local_session.execute(studies_query)
            studies_rows = result.fetchall()
        
        print(f"   Found {len(studies_rows)} studies")
        
        # ------------------------------------------------------------------
        # Step 2: Read sites from local
        # ------------------------------------------------------------------
        print("📖 Reading sites from local database...")
        async with local_session_maker() as local_session:
            sites_query = text("""
                SELECT id, site_id, study_id, name, code, location, 
                       principal_investigator, address, city, country, 
                       status, created_at, updated_at
                FROM sites
                ORDER BY created_at
            """)
            result = await local_session.execute(sites_query)
            sites_rows = result.fetchall()
        
        print(f"   Found {len(sites_rows)} sites")
        print()
        
        if len(studies_rows) == 0 and len(sites_rows) == 0:
            print("⚠️  No data found in local database!")
            return
        
        # ------------------------------------------------------------------
        # Step 3: Clear Neon tables (optional - comment out if you want to keep existing data)
        # ------------------------------------------------------------------
        print("🗑️  Clearing existing data in Neon...")
        async with neon_session_maker() as neon_session:
            # Truncate in correct order (sites first due to FK)
            await neon_session.execute(text("TRUNCATE TABLE sites RESTART IDENTITY CASCADE"))
            await neon_session.execute(text("TRUNCATE TABLE studies RESTART IDENTITY CASCADE"))
            await neon_session.commit()
        print("   ✓ Cleared")
        print()
        
        # ------------------------------------------------------------------
        # Step 4: Insert studies into Neon
        # ------------------------------------------------------------------
        print("💾 Inserting studies into Neon...")
        studies_inserted = 0
        async with neon_session_maker() as neon_session:
            for row in studies_rows:
                try:
                    insert_query = text("""
                        INSERT INTO studies (id, study_id, name, description, status, created_at, updated_at)
                        VALUES (:id, :study_id, :name, :description, :status, :created_at, :updated_at)
                        ON CONFLICT (id) DO NOTHING
                    """)
                    await neon_session.execute(insert_query, {
                        "id": row[0],
                        "study_id": row[1],
                        "name": row[2],
                        "description": row[3],
                        "status": row[4],
                        "created_at": row[5],
                        "updated_at": row[6]
                    })
                    studies_inserted += 1
                except Exception as e:
                    print(f"   ⚠️  Error inserting study {row[1]}: {e}")
            
            await neon_session.commit()
        print(f"   ✓ Inserted {studies_inserted} studies")
        
        # ------------------------------------------------------------------
        # Step 5: Insert sites into Neon
        # ------------------------------------------------------------------
        print("💾 Inserting sites into Neon...")
        sites_inserted = 0
        async with neon_session_maker() as neon_session:
            for row in sites_rows:
                try:
                    insert_query = text("""
                        INSERT INTO sites (id, site_id, study_id, name, code, location,
                                          principal_investigator, address, city, country,
                                          status, created_at, updated_at)
                        VALUES (:id, :site_id, :study_id, :name, :code, :location,
                                :principal_investigator, :address, :city, :country,
                                :status, :created_at, :updated_at)
                        ON CONFLICT (id) DO NOTHING
                    """)
                    await neon_session.execute(insert_query, {
                        "id": row[0],
                        "site_id": row[1],
                        "study_id": row[2],
                        "name": row[3],
                        "code": row[4],
                        "location": row[5],
                        "principal_investigator": row[6],
                        "address": row[7],
                        "city": row[8],
                        "country": row[9],
                        "status": row[10],
                        "created_at": row[11],
                        "updated_at": row[12]
                    })
                    sites_inserted += 1
                except Exception as e:
                    print(f"   ⚠️  Error inserting site {row[1]}: {e}")
            
            await neon_session.commit()
        print(f"   ✓ Inserted {sites_inserted} sites")
        print()
        
        # ------------------------------------------------------------------
        # Step 6: Verify data in Neon
        # ------------------------------------------------------------------
        print("✅ Verifying data in Neon...")
        async with neon_session_maker() as neon_session:
            studies_count = await neon_session.execute(text("SELECT COUNT(*) FROM studies"))
            sites_count = await neon_session.execute(text("SELECT COUNT(*) FROM sites"))
            
            neon_studies = studies_count.scalar()
            neon_sites = sites_count.scalar()
        
        print(f"   Neon now has: {neon_studies} studies, {neon_sites} sites")
        print()
        
        print("=" * 70)
        print("[SUCCESS] Data copy completed!")
        print("=" * 70)
        print(f"   Local: {len(studies_rows)} studies, {len(sites_rows)} sites")
        print(f"   Neon:  {neon_studies} studies, {neon_sites} sites")
        print("=" * 70)
        
    except Exception as e:
        print()
        print("=" * 70)
        print(f"[ERROR] Failed to copy data: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await local_engine.dispose()
        await neon_engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(copy_studies_sites_to_neon())
    except KeyboardInterrupt:
        print("\n\nMigration interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nAn unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
