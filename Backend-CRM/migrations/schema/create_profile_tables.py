"""
Database migration script to create profile-related tables.
Run this script to add the profile tables to your database.
"""
import asyncio
import sys
from sqlalchemy import text
from app.db import AsyncSessionLocal, engine
from app.config import settings


async def create_profile_tables():
    """Create profile-related tables."""
    print("=" * 60)
    print("Profile Tables Migration")
    print("=" * 60)
    print(f"Database: {settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url}")
    print()
    
    tables = [
        {
            'name': 'rd_studies',
            'sql': """
                CREATE TABLE IF NOT EXISTS rd_studies (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id VARCHAR(255) NOT NULL,
                    study_title VARCHAR(500) NOT NULL,
                    nct_number VARCHAR(50),
                    asset VARCHAR(255),
                    indication VARCHAR(255),
                    enrollment INTEGER,
                    phases VARCHAR(50),
                    start_date TIMESTAMP WITH TIME ZONE,
                    completion_date TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    
                    CONSTRAINT fk_rd_studies_user
                        FOREIGN KEY(user_id) 
                        REFERENCES users(user_id)
                        ON DELETE CASCADE
                );
            """
        },
        {
            'name': 'iis_studies',
            'sql': """
                CREATE TABLE IF NOT EXISTS iis_studies (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id VARCHAR(255) NOT NULL,
                    study_title VARCHAR(500) NOT NULL,
                    asset VARCHAR(255),
                    indication VARCHAR(255),
                    phases VARCHAR(50),
                    enrollment INTEGER,
                    enrollment_start_date TIMESTAMP WITH TIME ZONE,
                    completion_date TIMESTAMP WITH TIME ZONE,
                    other_associated_hcp_ids JSONB DEFAULT '[]',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    
                    CONSTRAINT fk_iis_studies_user
                        FOREIGN KEY(user_id) 
                        REFERENCES users(user_id)
                        ON DELETE CASCADE
                );
            """
        },
        {
            'name': 'events',
            'sql': """
                CREATE TABLE IF NOT EXISTS events (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id VARCHAR(255) NOT NULL,
                    event_name VARCHAR(500) NOT NULL,
                    internal_external VARCHAR(20) NOT NULL,
                    event_type VARCHAR(100),
                    date_of_event TIMESTAMP WITH TIME ZONE,
                    event_description TEXT,
                    event_report TEXT,
                    relevant_internal_stakeholders JSONB DEFAULT '[]',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    
                    CONSTRAINT fk_events_user
                        FOREIGN KEY(user_id) 
                        REFERENCES users(user_id)
                        ON DELETE CASCADE
                );
            """
        },
        {
            'name': 'user_profiles',
            'sql': """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(255),
                    address TEXT,
                    phone VARCHAR(50),
                    email VARCHAR(255),
                    affiliation VARCHAR(500),
                    specialty VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    
                    CONSTRAINT fk_user_profiles_user
                        FOREIGN KEY(user_id) 
                        REFERENCES users(user_id)
                        ON DELETE CASCADE
                );
            """
        }
    ]
    
    async with AsyncSessionLocal() as session:
        try:
            for table_info in tables:
                table_name = table_info['name']
                create_sql = table_info['sql']
                
                # Check if table already exists
                check_table = text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = '{table_name}'
                    );
                """)
                result = await session.execute(check_table)
                table_exists = result.scalar()
                
                if table_exists:
                    print(f"  [SKIP] Table '{table_name}' already exists")
                    continue
                
                # Create table
                await session.execute(text(create_sql))
                
                # Create indexes for performance
                if table_name == 'rd_studies':
                    await session.execute(text("CREATE INDEX IF NOT EXISTS ix_rd_studies_user_id ON rd_studies (user_id);"))
                elif table_name == 'iis_studies':
                    await session.execute(text("CREATE INDEX IF NOT EXISTS ix_iis_studies_user_id ON iis_studies (user_id);"))
                elif table_name == 'events':
                    await session.execute(text("CREATE INDEX IF NOT EXISTS ix_events_user_id ON events (user_id);"))
                    await session.execute(text("CREATE INDEX IF NOT EXISTS ix_events_date ON events (date_of_event);"))
                
                await session.commit()
                print(f"  [OK] Table '{table_name}' created successfully!")
            
            print()
            print("=" * 60)
            print("[SUCCESS] All profile tables created successfully!")
            print("=" * 60)
            
        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] Failed to create tables: {e}")
            import traceback
            traceback.print_exc()
            print("\nMake sure:")
            print("  1. Your database is running")
            print("  2. Database connection settings are correct")
            print("  3. You have proper permissions to create tables")
            sys.exit(1)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    # Fix encoding for Windows console
    if sys.platform == 'win32':
        try:
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
        except:
            pass
    
    asyncio.run(create_profile_tables())

