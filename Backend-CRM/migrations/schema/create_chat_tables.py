"""
Database migration script to create chat-related tables.
Run this script to add the chat_messages and chat_documents tables to your database.
"""
import asyncio
import sys
from sqlalchemy import text
from app.db import AsyncSessionLocal
from app.config import settings


async def create_chat_tables():
    """Create the chat-related tables."""
    print("============================================================")
    print("Chat Tables Migration")
    print("============================================================")
    print(f"Database: {settings.database_url.split('@')[-1]}")
    
    async with AsyncSessionLocal() as session:
        try:
            tables_to_create = {
                "chat_messages": {
                    "table": """
                        CREATE TABLE chat_messages (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            user_id VARCHAR(255) NOT NULL,
                            role VARCHAR(20) NOT NULL,
                            content TEXT NOT NULL,
                            mode VARCHAR(20) NOT NULL DEFAULT 'general',
                            document_id UUID,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            
                            CONSTRAINT fk_chat_message_user
                                FOREIGN KEY(user_id) 
                                REFERENCES users(user_id)
                                ON DELETE CASCADE
                        )
                    """,
                    "indexes": [
                        "CREATE INDEX ix_chat_messages_user_id ON chat_messages (user_id)",
                        "CREATE INDEX ix_chat_messages_created_at ON chat_messages (created_at)"
                    ]
                },
                "chat_documents": {
                    "table": """
                        CREATE TABLE chat_documents (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            user_id VARCHAR(255) NOT NULL,
                            file_path VARCHAR(500) NOT NULL,
                            filename VARCHAR(255) NOT NULL,
                            content_type VARCHAR(100) NOT NULL,
                            size INTEGER NOT NULL,
                            uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            
                            CONSTRAINT fk_chat_document_user
                                FOREIGN KEY(user_id) 
                                REFERENCES users(user_id)
                                ON DELETE CASCADE
                        )
                    """,
                    "indexes": [
                        "CREATE INDEX ix_chat_documents_user_id ON chat_documents (user_id)"
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
            print("[SUCCESS] All chat tables created successfully!")
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
        asyncio.run(create_chat_tables())
    except KeyboardInterrupt:
        print("\nMigration interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        sys.exit(1)

