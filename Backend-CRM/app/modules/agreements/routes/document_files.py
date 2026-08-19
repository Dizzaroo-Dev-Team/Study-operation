"""REST API: agreement document-file download endpoints (DOCX from local fs or Azure)."""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user_optional
from app.config import settings
from app.db import get_db
from app.models import (
    Agreement,
    AgreementDocument,
    AgreementReviewDocument,
    AgreementReviewToken,
    AgreementStatus as AgreementStatusEnum,
)
from app.modules.agreements.aggregator import (
    _extract_blob_seq,
    _latest_agreement_document,
    _latest_document_for_version,
    _latest_signed_agreement_document,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Legal Documents"])


@router.get("/agreements/{agreement_id}/document-file")
async def get_agreement_document_file(
    agreement_id: UUID,
    version: Optional[int] = None,
    document_id: Optional[UUID] = None,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get agreement document DOCX file for ONLYOFFICE.
    
    Returns:
        DOCX file response
    """
    from fastapi.responses import FileResponse
    
    # Get agreement and documents
    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement_id)
        .options(selectinload(Agreement.documents))
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    if not agreement.documents:
        raise HTTPException(status_code=404, detail="No document found")
    
    # Get document (explicit id, latest for version, or latest overall)
    if document_id is not None:
        document = next((d for d in agreement.documents if d.id == document_id), None)
    elif version:
        document = _latest_document_for_version(agreement.documents, version)
    else:
        if agreement.status in (
            AgreementStatusEnum.REVIEWED_AND_SIGNED,
            AgreementStatusEnum.FULLY_SIGNED,
        ):
            document = _latest_signed_agreement_document(agreement.documents) or _latest_agreement_document(agreement.documents)
        elif agreement.status == AgreementStatusEnum.EXECUTED:
            document = _latest_signed_agreement_document(agreement.documents) or _latest_agreement_document(agreement.documents)
        else:
            document = _latest_agreement_document(agreement.documents)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document version not found")
    
    if not hasattr(document, 'document_file_path') or not document.document_file_path:
        raise HTTPException(status_code=404, detail="Document file not found")

    logger.info(
        "Serving agreement document-file (refresh/render): agreement_id=%s document_id=%s version=%s path=%s blob_seq=%s",
        agreement_id,
        document.id,
        document.version_number,
        document.document_file_path,
        _extract_blob_seq(document.document_file_path),
    )
    
    _path_str = str(document.document_file_path or "").lower()
    _is_pdf = _path_str.endswith(".pdf")
    _media_type = "application/pdf" if _is_pdf else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    _file_ext = "pdf" if _is_pdf else "docx"

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }

    doc_url = getattr(document, 'document_file_url', None)
    from app.utils.azure_storage import get_document_storage
    storage = get_document_storage()
    # Azure-first retrieval when storage is configured. This ensures documents
    # created from templates are consistently served from Blob.
    if storage and (doc_url or settings.azure_storage_connection_string):
        blob_bytes = await storage.download_file(document.document_file_path)
        if blob_bytes:
            import io
            return StreamingResponse(
                io.BytesIO(blob_bytes),
                media_type=_media_type,
                headers={
                    **headers,
                    "Content-Disposition": f'attachment; filename="agreement_{agreement_id}_v{document.version_number}.{_file_ext}"',
                },
            )
        if doc_url:
            raise HTTPException(status_code=404, detail="Document not found in Azure storage")

    file_path = Path(document.document_file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Document file not found at: {document.document_file_path}")

    return FileResponse(
        path=str(file_path),
        media_type=_media_type,
        filename=f"agreement_{agreement_id}_v{document.version_number}.{_file_ext}",
        headers=headers
    )


@router.get("/agreements/{agreement_id}/review-document-file")
async def get_review_document_file(
    agreement_id: UUID,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Get review document DOCX file for ONLYOFFICE (external reviewers).
    
    This endpoint serves the review copy, not the main document.
    External reviewers edit this copy, which is then compared with the main document.
    
    Returns:
        DOCX file response (review copy)
    """
    from fastapi.responses import FileResponse
    
    # Validate token
    token_result = await db.execute(
        select(AgreementReviewToken)
        .where(AgreementReviewToken.token == token)
        .where(AgreementReviewToken.agreement_id == agreement_id)
        .where(AgreementReviewToken.is_active == 'true')
    )
    review_token = token_result.scalar_one_or_none()
    
    if not review_token:
        raise HTTPException(status_code=403, detail="Invalid or expired review token")
    
    if review_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=403, detail="Review token has expired")
    
    # Get review document
    review_doc_result = await db.execute(
        select(AgreementReviewDocument)
        .where(AgreementReviewDocument.review_token_id == review_token.id)
        .where(AgreementReviewDocument.is_submitted == 'false')
    )
    review_document = review_doc_result.scalar_one_or_none()
    
    if not review_document:
        raise HTTPException(status_code=404, detail="Review document not found. The review may have already been submitted.")
    
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }

    _rfp = review_document.review_file_path
    from app.utils.azure_storage import get_document_storage as _gds_rvf
    _rvf_storage = _gds_rvf()
    if _rvf_storage and _rfp and _rfp.startswith("agreement_reviews/"):
        blob_bytes = await _rvf_storage.download_file(_rfp)
        if blob_bytes:
            import io
            return StreamingResponse(
                io.BytesIO(blob_bytes),
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    **headers,
                    "Content-Disposition": f'attachment; filename="agreement_review_{agreement_id}.docx"',
                },
            )
        raise HTTPException(status_code=404, detail="Review document not found in Azure")

    review_file_path = Path(_rfp)
    if not review_file_path.exists():
        raise HTTPException(status_code=404, detail="Review document file not found")

    return FileResponse(
        path=str(review_file_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"agreement_review_{agreement_id}.docx",
        headers=headers
    )

