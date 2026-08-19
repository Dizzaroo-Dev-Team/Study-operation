"""REST API: per-trial policy documents (PDF/DOCX stored in Postgres BYTEA)."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.modules.site_budgeting.db_models import BudgetPolicyDocument
from app.modules.site_budgeting.dependencies import require_site_budgeting

router = APIRouter(tags=["Site Budgeting"])


@router.post("/trials/{trial_id}/policy-documents")
async def upload_policy_document(
    trial_id: UUID,
    country_code: str = Query(..., description="ISO-3 country code, e.g. BRA"),
    policy_document: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """Store a policy PDF/DOCX in PostgreSQL BYTEA, scoped to (trial, country)."""
    cc = country_code.strip().upper()[:3]
    if not cc:
        raise HTTPException(status_code=400, detail="country_code is required")

    blob = await policy_document.read()
    if not blob:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    row = BudgetPolicyDocument(
        trial_id=trial_id,
        country_code=cc,
        file_name=policy_document.filename or "policy.pdf",
        mime_type=policy_document.content_type or "application/octet-stream",
        file_size=len(blob),
        document_data=blob,
        uploaded_by=user.get("user_id"),
    )
    db.add(row)
    await db.flush()
    await db.commit()
    return {
        "id": str(row.id),
        "country_code": row.country_code,
        "file_name": row.file_name,
        "file_size": row.file_size,
        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
    }


@router.get("/trials/{trial_id}/policy-documents")
async def list_policy_documents(
    trial_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    """Metadata only - bytes excluded for payload size."""
    rows = (await db.execute(
        select(
            BudgetPolicyDocument.id,
            BudgetPolicyDocument.country_code,
            BudgetPolicyDocument.file_name,
            BudgetPolicyDocument.mime_type,
            BudgetPolicyDocument.file_size,
            BudgetPolicyDocument.uploaded_at,
        )
        .where(BudgetPolicyDocument.trial_id == trial_id)
        .order_by(BudgetPolicyDocument.country_code, BudgetPolicyDocument.uploaded_at.desc())
    )).all()
    return [
        {
            "id": str(r.id),
            "country_code": r.country_code,
            "file_name": r.file_name,
            "mime_type": r.mime_type,
            "file_size": r.file_size,
            "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
        }
        for r in rows
    ]


@router.delete("/trials/{trial_id}/policy-documents/{doc_id}", status_code=204)
async def delete_policy_document(
    trial_id: UUID,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    row = (await db.execute(
        select(BudgetPolicyDocument).where(
            BudgetPolicyDocument.id == doc_id,
            BudgetPolicyDocument.trial_id == trial_id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Policy document not found")
    await db.delete(row)
    await db.commit()
    return None


@router.get("/trials/{trial_id}/policy-documents/{doc_id}/download")
async def download_policy_document(
    trial_id: UUID,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    row = (await db.execute(
        select(BudgetPolicyDocument).where(
            BudgetPolicyDocument.id == doc_id,
            BudgetPolicyDocument.trial_id == trial_id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Policy document not found")
    return Response(
        content=row.document_data,
        media_type=row.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{row.file_name}"'},
    )
