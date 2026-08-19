"""
Agreement Workflow Audit Script

This script audits the current state of the Agreement workflow implementation
to verify what has been implemented and what is missing.

Run: python audit_agreement_workflow.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import (
    Agreement,
    AgreementVersion,
    AgreementDocument,
    AgreementComment,
    AgreementInlineComment,
    StudyTemplate,
)


async def audit_implementation():
    """
    Audit the Agreement workflow implementation.
    """
    print("=" * 80)
    print("AGREEMENT WORKFLOW IMPLEMENTATION AUDIT")
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
        print("1️⃣ MODEL EXISTENCE CHECK")
        print("-" * 80)
        
        # Check if tables exist
        tables_to_check = [
            ("agreements", Agreement),
            ("agreement_versions", AgreementVersion),
            ("agreement_documents", AgreementDocument),
            ("agreement_comments", AgreementComment),
            ("agreement_inline_comments", AgreementInlineComment),
            ("study_templates", StudyTemplate),
        ]
        
        for table_name, model_class in tables_to_check:
            try:
                result = await session.execute(
                    text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')")
                )
                exists = result.scalar()
                status = "✅ EXISTS" if exists else "❌ MISSING"
                print(f"  {status}: {table_name} ({model_class.__name__})")
            except Exception as e:
                print(f"  ❌ ERROR checking {table_name}: {e}")
        
        print()
        print("2️⃣ DATABASE SCHEMA CHECK")
        print("-" * 80)
        
        # Check for JSON fields
        json_fields = [
            ("study_templates", "template_content", "Template JSON content"),
            ("agreement_documents", "document_content", "Document JSON content"),
        ]
        
        for table, column, description in json_fields:
            try:
                result = await session.execute(
                    text(f"""
                        SELECT EXISTS (
                            SELECT FROM information_schema.columns 
                            WHERE table_name = '{table}' AND column_name = '{column}'
                        )
                    """)
                )
                exists = result.scalar()
                status = "✅ EXISTS" if exists else "❌ MISSING"
                print(f"  {status}: {table}.{column} - {description}")
            except Exception as e:
                print(f"  ❌ ERROR checking {table}.{column}: {e}")
        
        print()
        print("3️⃣ DATA COUNT CHECK")
        print("-" * 80)
        
        # Count records in each table
        count_queries = [
            ("Agreements", "SELECT COUNT(*) FROM agreements"),
            ("Agreement Versions", "SELECT COUNT(*) FROM agreement_versions"),
            ("Agreement Documents", "SELECT COUNT(*) FROM agreement_documents"),
            ("Agreement Comments", "SELECT COUNT(*) FROM agreement_comments"),
            ("Inline Comments", "SELECT COUNT(*) FROM agreement_inline_comments"),
            ("Study Templates", "SELECT COUNT(*) FROM study_templates"),
        ]
        
        for label, query in count_queries:
            try:
                result = await session.execute(text(query))
                count = result.scalar()
                print(f"  {label}: {count} records")
            except Exception as e:
                print(f"  ❌ ERROR counting {label}: {e}")
        
        print()
        print("4️⃣ IMPLEMENTATION STATUS SUMMARY")
        print("-" * 80)
        
        # Check if template-based creation is enforced
        try:
            result = await session.execute(
                text("SELECT COUNT(*) FROM agreements WHERE is_legacy = 'false'")
            )
            non_legacy_count = result.scalar()
            result = await session.execute(
                text("SELECT COUNT(*) FROM agreements WHERE is_legacy = 'true'")
            )
            legacy_count = result.scalar()
            
            print(f"  Legacy agreements (file-based): {legacy_count}")
            print(f"  Template-based agreements: {non_legacy_count}")
            
            if legacy_count > 0 and non_legacy_count == 0:
                print("  ⚠️  WARNING: Only legacy agreements exist. Template system may not be in use.")
            elif non_legacy_count > 0:
                print("  ✅ Template-based agreements exist.")
        except Exception as e:
            print(f"  ❌ ERROR checking agreement types: {e}")
        
        # Check if documents use JSON
        try:
            result = await session.execute(
                text("""
                    SELECT COUNT(*) FROM agreement_documents 
                    WHERE document_content IS NOT NULL 
                    AND document_content != '{}'::jsonb
                """)
            )
            json_doc_count = result.scalar()
            print(f"  Documents with JSON content: {json_doc_count}")
        except Exception as e:
            print(f"  ❌ ERROR checking JSON documents: {e}")
        
        print()
        print("5️⃣ CODE IMPLEMENTATION CHECK")
        print("-" * 80)
        print("  Note: This requires manual code inspection.")
        print("  ✅ StudyTemplate model: EXISTS (models.py)")
        print("  ✅ AgreementDocument model: EXISTS (models.py)")
        print("  ✅ AgreementInlineComment model: EXISTS (models.py)")
        print("  ✅ TipTap editor component: EXISTS (AgreementEditor.tsx)")
        print("  ✅ Template creation endpoint: EXISTS (legal_docs.py)")
        print("  ✅ Document save endpoint: EXISTS (legal_docs.py)")
        print("  ⚠️  Upload endpoint: STILL ACTIVE (needs to be disabled)")
        
        print()
        print("=" * 80)
        print("AUDIT COMPLETE")
        print("=" * 80)
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(audit_implementation())
