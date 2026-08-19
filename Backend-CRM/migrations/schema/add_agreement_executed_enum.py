"""
Migration script to add 'agreement_executed' to workflow_step_name enum.
Run this script to update the PostgreSQL enum type.
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.config import settings


async def add_agreement_executed_enum():
    """
    Add 'agreement_executed' value to workflow_step_name enum in PostgreSQL.
    """
    # Create async engine
    database_url = settings.database_url
    engine = create_async_engine(
        database_url,
        echo=False,
        future=True,
    )

    # Create session factory
    TempAsyncSessionLocal = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with TempAsyncSessionLocal() as session:
        try:
            # Add 'agreement_executed' to workflow_step_name enum
            add_enum_value = """
                DO $$ 
                BEGIN
                    -- Check if the value already exists
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_enum 
                        WHERE enumlabel = 'agreement_executed' 
                        AND enumtypid = (
                            SELECT oid FROM pg_type WHERE typname = 'workflow_step_name'
                        )
                    ) THEN
                        ALTER TYPE workflow_step_name ADD VALUE 'agreement_executed';
                    END IF;
                END $$;
            """
            
            print("Adding 'agreement_executed' to workflow_step_name enum...")
            await session.execute(text(add_enum_value))
            await session.commit()
            print("✓ Successfully added 'agreement_executed' to workflow_step_name enum")
            
        except Exception as e:
            print(f"✗ Error adding enum value: {str(e)}")
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(add_agreement_executed_enum())
