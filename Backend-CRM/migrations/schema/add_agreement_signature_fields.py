"""
Migration script to add signature fields to agreements table and create agreement_signed_documents table.
"""
import asyncio
from sqlalchemy import text
from app.db import AsyncSessionLocal

async def migrate():
    """Add signature fields and create signed documents table."""
    async with AsyncSessionLocal() as db:
        try:
            # Add signature fields to agreements table
            await db.execute(text("""
                ALTER TABLE agreements 
                ADD COLUMN IF NOT EXISTS zoho_request_id VARCHAR(255),
                ADD COLUMN IF NOT EXISTS signature_status VARCHAR(50)
            """))
            
            # Create agreement_signed_documents table
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS agreement_signed_documents (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    agreement_id UUID NOT NULL,
                    file_path VARCHAR(500) NOT NULL,
                    signed_at TIMESTAMP WITH TIME ZONE,
                    downloaded_from_zoho_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    zoho_request_id VARCHAR(255),
                    CONSTRAINT fk_agreement_signed_documents_agreement 
                        FOREIGN KEY(agreement_id) REFERENCES agreements(id) ON DELETE CASCADE
                )
            """))
            
            # Create index for faster lookups
            await db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_agreement_signed_documents_agreement_id 
                ON agreement_signed_documents(agreement_id)
            """))
            
            await db.commit()
            print("✅ Successfully added signature fields and created agreement_signed_documents table")
        except Exception as e:
            await db.rollback()
            print(f"❌ Migration failed: {str(e)}")
            raise

if __name__ == "__main__":
    asyncio.run(migrate())
