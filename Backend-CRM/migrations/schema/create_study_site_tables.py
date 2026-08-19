"""
Database migration script to create study and site tables.
Run this script to add the Study, Site, and UserSite tables to your database.
"""
import asyncio
import sys
from sqlalchemy import text
from app.db import AsyncSessionLocal
from app.config import settings


async def create_study_site_tables():
    """Create the study and site related tables."""
    print("============================================================")
    print("Study and Site Tables Migration")
    print("============================================================")
    print(f"Database: {settings.database_url.split('@')[-1]}")
    
    async with AsyncSessionLocal() as session:
        try:
            tables_to_create = {
                "studies": {
                    "table": """
                        CREATE TABLE studies (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            study_id VARCHAR(100) UNIQUE NOT NULL,
                            name VARCHAR(500) NOT NULL,
                            description TEXT,
                            status VARCHAR(50),
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        )
                    """,
                    "indexes": [
                        "CREATE INDEX ix_studies_study_id ON studies (study_id)"
                    ]
                },
                "sites": {
                    "table": """
                        CREATE TABLE sites (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            site_id VARCHAR(100) UNIQUE NOT NULL,
                            study_id UUID NOT NULL,
                            name VARCHAR(500) NOT NULL,
                            code VARCHAR(100),
                            location VARCHAR(500),
                            principal_investigator VARCHAR(255),
                            address TEXT,
                            city VARCHAR(255),
                            country VARCHAR(255),
                            status VARCHAR(50),
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            
                            CONSTRAINT fk_site_study
                                FOREIGN KEY(study_id) 
                                REFERENCES studies(id)
                                ON DELETE CASCADE
                        )
                    """,
                    "indexes": [
                        "CREATE INDEX ix_sites_site_id ON sites (site_id)",
                        "CREATE INDEX ix_sites_study_id ON sites (study_id)"
                    ]
                },
                "user_sites": {
                    "table": """
                        CREATE TABLE user_sites (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            user_id VARCHAR(255) NOT NULL,
                            site_id UUID NOT NULL,
                            role VARCHAR(50),
                            assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            
                            CONSTRAINT fk_user_site_user
                                FOREIGN KEY(user_id) 
                                REFERENCES users(user_id)
                                ON DELETE CASCADE,
                            CONSTRAINT fk_user_site_site
                                FOREIGN KEY(site_id) 
                                REFERENCES sites(id)
                                ON DELETE CASCADE,
                            CONSTRAINT uq_user_site UNIQUE(user_id, site_id)
                        )
                    """,
                    "indexes": [
                        "CREATE INDEX ix_user_sites_user_id ON user_sites (user_id)",
                        "CREATE INDEX ix_user_sites_site_id ON user_sites (site_id)"
                    ]
                }
            }

            for table_name, table_def in tables_to_create.items():
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
                else:
                    print(f"  Creating table '{table_name}'...")
                    await session.execute(text(table_def["table"]))
                    
                    # Create indexes
                    for index_sql in table_def["indexes"]:
                        await session.execute(text(index_sql))
                    
                    print(f"  [OK] Table '{table_name}' created successfully!")
            
            await session.commit()
            print("\n============================================================")
            print("[SUCCESS] All study and site tables created successfully!")
            print("============================================================")
            
        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] Failed to create tables: {e}")
            print("\nMake sure:")
            print("  1. Your database is running")
            print("  2. Database connection settings are correct")
            print("  3. You have proper permissions to create tables")
            sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(create_study_site_tables())
    except KeyboardInterrupt:
        print("\nMigration interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        sys.exit(1)

