"""
document_versioning.py — ONE consistent "latest version / next version / add version"
helper for AgreementDocument. Today each route does this math ad-hoc; this is the
single source so unified flows agree. Additive — wraps the existing AgreementDocument
model; no behavior change to legacy routes (they may adopt it later).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgreementDocument


async def latest_document(db: AsyncSession, agreement_id) -> Optional[AgreementDocument]:
    rows = (await db.execute(
        select(AgreementDocument).where(AgreementDocument.agreement_id == agreement_id)
    )).scalars().all()
    return max(rows, key=lambda d: d.version_number or 0) if rows else None


async def next_version_number(db: AsyncSession, agreement_id) -> int:
    latest = await latest_document(db, agreement_id)
    return (latest.version_number or 0) + 1 if latest else 1


async def add_document_version(
    db: AsyncSession, agreement_id, file_path: str, *,
    is_signed: bool = False, created_by: Optional[str] = None,
    template_id=None, document_file_url: Optional[str] = None,
) -> AgreementDocument:
    """Create the next AgreementDocument version (flushes; caller owns the commit)."""
    version = await next_version_number(db, agreement_id)
    doc = AgreementDocument(
        agreement_id=agreement_id,
        version_number=version,
        document_file_path=file_path,
        document_file_url=document_file_url,
        created_from_template_id=template_id,
        created_by=created_by,
        is_signed_version="true" if is_signed else "false",
    )
    db.add(doc)
    await db.flush()
    return doc
