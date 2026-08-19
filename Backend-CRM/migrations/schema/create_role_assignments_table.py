"""
Database migration script to create user_role_assignments table.
Run this script to add the UserRoleAssignment table to your database.
This table links users to roles (CRA, Study Manager, Medical Monitor) with specific site/study access.
"""
import asyncio
import sys
import os
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


async def create_role_assignments_table():
    """Create the user_role_assignments table."""
    print("============================================================")
    print("User Role Assignments Table Migration")
    print("============================================================")
    
    # Handle Docker hostname issue - replace 'postgres:' with 'localhost:' if running outside Docker
    db_url_to_use = settings.database_url
    if 'postgres:' in db_url_to_use and 'localhost' not in db_url_to_use and '127.0.0.1' not in db_url_to_use:
        db_url_to_use = db_url_to_use.replace('postgres:', 'localhost:')
        print("  [INFO] Replaced Docker hostname 'postgres' with 'localhost' for local execution")
    
    # Show database info (masked for security)
    if '@' in db_url_to_use:
        db_info = db_url_to_use.split('@')[-1]
    else:
        db_info = "configured database"
    print(f"Database: {db_info}")
    
    # Create a temporary engine with the corrected URL
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
    
    # Test connection first
    print("\n  Testing database connection...")
    try:
        async with TempAsyncSessionLocal() as test_session:
            await test_session.execute(text("SELECT 1"))
            print("  [OK] Database connection successful")
    except Exception as conn_error:
        print(f"\n  [ERROR] Cannot connect to database: {conn_error}")
        print("\n  Troubleshooting:")
        print("    1. Make sure PostgreSQL is running")
        print("    2. Check your DATABASE_URL environment variable")
        print("    3. If using Docker, make sure the database container is running")
        print("    4. If 'postgres' hostname doesn't resolve, try 'localhost' or '127.0.0.1'")
        masked_url = db_url_to_use.replace('crm_pass@', '***@') if 'crm_pass@' in db_url_to_use else db_url_to_use[:50] + "..."
        print(f"\n  Current DATABASE_URL: {masked_url}")
        await temp_engine.dispose()
        sys.exit(1)
    
    async with TempAsyncSessionLocal() as session:
        try:
            # First, update the UserRole enum type to include new roles
            print("\n  Updating UserRole enum type...")
            
            # Check if enum exists and add new values if they don't exist
            check_enum = text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = 'userrole'
                );
            """)
            result = await session.execute(check_enum)
            enum_exists = result.scalar()
            
            if enum_exists:
                # Add new enum values if they don't exist
                add_cra = text("""
                    DO $$ BEGIN
                        ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'cra';
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                """)
                add_study_manager = text("""
                    DO $$ BEGIN
                        ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'study_manager';
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                """)
                add_medical_monitor = text("""
                    DO $$ BEGIN
                        ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'medical_monitor';
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                """)
                
                try:
                    await session.execute(add_cra)
                    print("    [OK] Added 'cra' to UserRole enum")
                except Exception as e:
                    print(f"    [INFO] 'cra' may already exist: {e}")
                
                try:
                    await session.execute(add_study_manager)
                    print("    [OK] Added 'study_manager' to UserRole enum")
                except Exception as e:
                    print(f"    [INFO] 'study_manager' may already exist: {e}")
                
                try:
                    await session.execute(add_medical_monitor)
                    print("    [OK] Added 'medical_monitor' to UserRole enum")
                except Exception as e:
                    print(f"    [INFO] 'medical_monitor' may already exist: {e}")
                
                # CRITICAL: Commit enum changes before using them in CREATE TABLE
                # PostgreSQL requires new enum values to be committed before use
                await session.commit()
                print("    [OK] Committed enum changes")
            else:
                print("    [WARN] UserRole enum not found. It should be created by SQLAlchemy.")
            
            # Create the user_role_assignments table
            table_name = "user_role_assignments"
            check_table = text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = '{table_name}'
                );
            """)
            result = await session.execute(check_table)
            table_exists = result.scalar()
            
            if table_exists:
                print(f"\n  [SKIP] Table '{table_name}' already exists")
            else:
                print(f"\n  Creating table '{table_name}'...")
                
                table_sql = f"""
                    CREATE TABLE {table_name} (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id VARCHAR(255) NOT NULL,
                        role userrole NOT NULL,
                        site_id UUID,
                        study_id UUID,
                        assigned_by VARCHAR(255),
                        assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        
                        CONSTRAINT fk_user_role_user
                            FOREIGN KEY(user_id) 
                            REFERENCES users(user_id)
                            ON DELETE CASCADE,
                        CONSTRAINT fk_user_role_site
                            FOREIGN KEY(site_id) 
                            REFERENCES sites(id)
                            ON DELETE CASCADE,
                        CONSTRAINT fk_user_role_study
                            FOREIGN KEY(study_id) 
                            REFERENCES studies(id)
                            ON DELETE CASCADE,
                        CONSTRAINT chk_role_type CHECK (
                            role IN ('cra', 'study_manager', 'medical_monitor')
                        )
                    )
                """
                
                await session.execute(text(table_sql))
                
                # Create indexes
                indexes = [
                    f"CREATE INDEX ix_user_role_assignments_user_id ON {table_name} (user_id)",
                    f"CREATE INDEX ix_user_role_assignments_role ON {table_name} (role)",
                    f"CREATE INDEX ix_user_role_assignments_site_id ON {table_name} (site_id)",
                    f"CREATE INDEX ix_user_role_assignments_study_id ON {table_name} (study_id)",
                    f"CREATE INDEX ix_user_role_assignments_user_role ON {table_name} (user_id, role)"
                ]
                
                for index_sql in indexes:
                    await session.execute(text(index_sql))
                
                print(f"  [OK] Table '{table_name}' created successfully!")
            
            await session.commit()
            print("\n============================================================")
            print("[SUCCESS] User role assignments table created successfully!")
            print("============================================================")
            print("\nRole Access Rules:")
            print("  - CRA: Has access to specific sites and studies assigned to them")
            print("  - Study Manager: Has site-level access, all studies in assigned sites are accessible")
            print("  - Medical Monitor: Same as CRA - has access to specific sites and studies assigned")
            
        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] Failed to create table: {e}")
            import traceback
            traceback.print_exc()
            print("\nMake sure:")
            print("  1. Your database is running")
            print("  2. Database connection settings are correct")
            print("  3. You have proper permissions to create tables")
            print("  4. The 'users', 'sites', and 'studies' tables exist")
            await temp_engine.dispose()
            sys.exit(1)
        finally:
            await temp_engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(create_role_assignments_table())
    except KeyboardInterrupt:
        print("\nMigration interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

