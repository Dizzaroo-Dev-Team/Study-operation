"""
Add Save Document feature fields to AgreementReviewDocument model.

This migration adds:
- saved_review_url: URL to the saved review document in Azure
- saved_review_path: Blob path to the saved review document  
- saved_at: When the review document was last saved

These fields support the new "Save Document" functionality in the review workflow.
"""

from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

def upgrade(connection):
    """Add the new save document fields to agreement_review_documents table."""
    
    try:
        # Check if columns already exist
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'agreement_review_documents' 
            AND column_name IN ('saved_review_url', 'saved_review_path', 'saved_at')
        """)).fetchall()
        
        existing_columns = [row[0] for row in result]
        
        # Add saved_review_url column if it doesn't exist
        if 'saved_review_url' not in existing_columns:
            connection.execute(text("""
                ALTER TABLE agreement_review_documents 
                ADD COLUMN saved_review_url TEXT
            """))
            logger.info("Added saved_review_url column to agreement_review_documents")
        
        # Add saved_review_path column if it doesn't exist
        if 'saved_review_path' not in existing_columns:
            connection.execute(text("""
                ALTER TABLE agreement_review_documents 
                ADD COLUMN saved_review_path TEXT
            """))
            logger.info("Added saved_review_path column to agreement_review_documents")
        
        # Add saved_at column if it doesn't exist
        if 'saved_at' not in existing_columns:
            connection.execute(text("""
                ALTER TABLE agreement_review_documents 
                ADD COLUMN saved_at TIMESTAMP WITH TIME ZONE
            """))
            logger.info("Added saved_at column to agreement_review_documents")
        
        logger.info("Successfully added Save Document fields to agreement_review_documents table")
        
    except Exception as e:
        logger.exception(f"Failed to add Save Document fields: {e}")
        raise


def downgrade(connection):
    """Remove the new save document fields from agreement_review_documents table."""
    
    try:
        # Drop the new columns if they exist
        connection.execute(text("""
            ALTER TABLE agreement_review_documents 
            DROP COLUMN IF EXISTS saved_review_url,
            DROP COLUMN IF EXISTS saved_review_path,
            DROP COLUMN IF EXISTS saved_at
        """))
        
        logger.info("Successfully removed Save Document fields from agreement_review_documents table")
        
    except Exception as e:
        logger.exception(f"Failed to remove Save Document fields: {e}")
        raise


if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    # Simple SQL execution for migration
    import psycopg2
    from app.config import settings
    
    try:
        # Connect to database
        conn = psycopg2.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            database=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD
        )
        cursor = conn.cursor()
        
        # Execute upgrade
        upgrade(conn)
        conn.commit()
        print("Migration completed successfully")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        if 'conn' in locals():
            conn.rollback()
        raise
    finally:
        if 'conn' in locals():
            conn.close()
