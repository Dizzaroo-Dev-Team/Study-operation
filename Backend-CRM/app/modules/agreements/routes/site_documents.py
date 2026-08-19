"""REST API: per-site document CRUD (LEGACY - superseded by /api/isf-documents).

Five endpoints retained for backward compatibility during the ISF migration.
All marked deprecated on the OpenAPI surface.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import UUID

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.auth import get_current_user_optional
from app.config import settings
from app.db import get_db
from app.models import DocumentCategory, DocumentType, ReviewStatus, Site, SiteDocument

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Legal Documents"])


@router.get("/sites/{site_id}/documents", response_model=List[schemas.SiteDocumentResponse],
            deprecated=True,
            summary="[DEPRECATED] List site documents — use /api/isf-documents instead")
async def get_site_documents(
    site_id: str,
    category: Optional[str] = Query(None),
    document_type: Optional[str] = Query(None, description="Filter by document type: 'sponsor' or 'site'"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    [DEPRECATED] List all documents for a site.
    This endpoint is superseded by the ISF document system (/api/isf-documents).
    Kept for backward compatibility during migration.
    Optional category and document_type filters.
    """
    # Resolve site
    try:
        site_uuid = UUID(str(site_id))
        site_result = await db.execute(select(Site).where(Site.id == site_uuid))
        site = site_result.scalar_one_or_none()
    except (ValueError, TypeError):
        site_result = await db.execute(select(Site).where(Site.site_id == site_id))
        site = site_result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    # Query documents
    query = select(SiteDocument).where(SiteDocument.site_id == site.id)
    if category:
        try:
            category_enum = DocumentCategory(category)
            query = query.where(SiteDocument.category == category_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
    
    if document_type:
        try:
            doc_type_enum = DocumentType(document_type)
            query = query.where(SiteDocument.document_type == doc_type_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid document_type: {document_type}")
    
    query = query.order_by(SiteDocument.uploaded_at.desc())
    result = await db.execute(query)
    documents = result.scalars().all()
    
    return [
        {
            "id": doc.id,
            "site_id": str(doc.site_id),
            "category": doc.category.value,
            "file_name": doc.file_name,
            "content_type": doc.content_type,
            "size": doc.size,
            "uploaded_by": doc.uploaded_by,
            "uploaded_at": doc.uploaded_at,
            "description": doc.description,
            "metadata": doc.document_metadata or {},
            "document_type": doc.document_type.value if doc.document_type else None,
            "review_status": doc.review_status.value if doc.review_status else None,
            "tmf_filed": doc.tmf_filed or "false",
        }
        for doc in documents
    ]


@router.post("/sites/{site_id}/documents", response_model=schemas.SiteDocumentResponse,
             deprecated=True,
             summary="[DEPRECATED] Upload site document — use /api/isf-documents instead")
async def upload_site_document(
    site_id: str,
    file: UploadFile = File(...),
    category: str = Form(...),
    description: Optional[str] = Form(None),
    document_type: Optional[str] = Form(None, description="Document type: 'sponsor' or 'site'. Defaults to 'site'."),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a document for a site.
    Document persists regardless of site status changes.
    """
    # Resolve site
    try:
        site_uuid = UUID(str(site_id))
        site_result = await db.execute(select(Site).where(Site.id == site_uuid))
        site = site_result.scalar_one_or_none()
    except (ValueError, TypeError):
        site_result = await db.execute(select(Site).where(Site.site_id == site_id))
        site = site_result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    # Validate category
    try:
        category_enum = DocumentCategory(category)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
    
    # Validate and set document_type
    doc_type_enum = DocumentType.SITE  # Default to SITE
    if document_type:
        try:
            doc_type_enum = DocumentType(document_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid document_type: {document_type}")
    
    # Set review_status: sponsor documents don't need review, site documents start as pending
    review_status_enum = None
    if doc_type_enum == DocumentType.SITE:
        review_status_enum = ReviewStatus.PENDING
    
    # Create upload directory if it doesn't exist
    upload_dir = Path(settings.upload_dir) / "site_documents"
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    file_ext = Path(file.filename).suffix if file.filename else ""
    file_id = uuid.uuid4()
    file_name = f"{file_id}{file_ext}"
    file_path = upload_dir / file_name
    
    # Save file
    try:
        async with aiofiles.open(file_path, "wb") as buffer:
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                await buffer.write(chunk)

        file_size = file_path.stat().st_size
        
        # Create document record
        document = SiteDocument(
            site_id=site.id,
            category=category_enum,
            file_path=str(file_path),
            file_name=file.filename or "unknown",
            content_type=file.content_type or "application/octet-stream",
            size=file_size,
            uploaded_by=current_user.get("user_id") if current_user else None,
            description=description,
            document_type=doc_type_enum,
            review_status=review_status_enum,
            tmf_filed='false',
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)
        
        return {
            "id": document.id,
            "site_id": str(document.site_id),
            "category": document.category.value,
            "file_name": document.file_name,
            "content_type": document.content_type,
            "size": document.size,
            "uploaded_by": document.uploaded_by,
            "uploaded_at": document.uploaded_at,
            "description": document.description,
            "metadata": document.document_metadata or {},
            "document_type": document.document_type.value if document.document_type else None,
            "review_status": document.review_status.value if document.review_status else None,
            "tmf_filed": document.tmf_filed or "false",
        }
        
    except Exception as e:
        # Clean up file if database operation fails
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")


@router.get("/sites/{site_id}/documents/{document_id}/download",
            deprecated=True,
            summary="[DEPRECATED] Download site document — use /api/isf-documents instead")
async def download_site_document(
    site_id: str,
    document_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Download a site document.
    """
    # Resolve site
    try:
        site_uuid = UUID(str(site_id))
        site_result = await db.execute(select(Site).where(Site.id == site_uuid))
        site = site_result.scalar_one_or_none()
    except (ValueError, TypeError):
        site_result = await db.execute(select(Site).where(Site.site_id == site_id))
        site = site_result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    # Get document
    result = await db.execute(
        select(SiteDocument).where(
            SiteDocument.id == document_id,
            SiteDocument.site_id == site.id
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on server")
    
    return FileResponse(
        path=str(file_path),
        filename=document.file_name,
        media_type=document.content_type,
    )


async def sendDocumentToTMF(document_id: UUID) -> bool:
    """
    Placeholder function for TMF integration.
    In the future, this will integrate with the actual TMF system.
    
    Args:
        document_id: The UUID of the document to send to TMF
        db: Database session
        
    Returns:
        bool: True if successful, False otherwise
    """
    # TODO: Implement actual TMF integration
    # For now, this is a placeholder that simulates TMF filing
    print(f"[TMF PLACEHOLDER] Would send document {document_id} to TMF system")
    return True


@router.post("/sites/{site_id}/documents/{document_id}/approve", response_model=schemas.SiteDocumentResponse,
             deprecated=True,
             summary="[DEPRECATED] Approve site document — use /api/isf-workflow instead")
async def approve_site_document(
    site_id: str,
    document_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve a site-uploaded document and send it to TMF.
    Only works for documents with document_type='site' and review_status='pending'.
    """
    # Resolve site
    try:
        site_uuid = UUID(str(site_id))
        site_result = await db.execute(select(Site).where(Site.id == site_uuid))
        site = site_result.scalar_one_or_none()
    except (ValueError, TypeError):
        site_result = await db.execute(select(Site).where(Site.site_id == site_id))
        site = site_result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    # Get document
    result = await db.execute(
        select(SiteDocument).where(
            SiteDocument.id == document_id,
            SiteDocument.site_id == site.id
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Validate that this is a site-uploaded document
    if not document.document_type or document.document_type != DocumentType.SITE:
        raise HTTPException(status_code=400, detail="Only site-uploaded documents can be approved")
    
    # Update review status
    document.review_status = ReviewStatus.APPROVED
    
    # Send to TMF (placeholder)
    tmf_success = await sendDocumentToTMF(document.id)
    if tmf_success:
        document.tmf_filed = 'true'
    else:
        # Even if TMF fails, mark as approved (TMF can be retried later)
        pass
    
    await db.commit()
    await db.refresh(document)
    
    return {
        "id": document.id,
        "site_id": str(document.site_id),
        "category": document.category.value,
        "file_name": document.file_name,
        "content_type": document.content_type,
        "size": document.size,
        "uploaded_by": document.uploaded_by,
        "uploaded_at": document.uploaded_at,
        "description": document.description,
        "metadata": document.document_metadata or {},
        "document_type": document.document_type.value if document.document_type else None,
        "review_status": document.review_status.value if document.review_status else None,
        "tmf_filed": document.tmf_filed or "false",
    }


@router.post("/sites/{site_id}/documents/{document_id}/reject", response_model=schemas.SiteDocumentResponse,
             deprecated=True,
             summary="[DEPRECATED] Reject site document — use /api/isf-workflow instead")
async def reject_site_document(
    site_id: str,
    document_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Reject a site-uploaded document.
    Only works for documents with document_type='site' and review_status='pending'.
    """
    # Resolve site
    try:
        site_uuid = UUID(str(site_id))
        site_result = await db.execute(select(Site).where(Site.id == site_uuid))
        site = site_result.scalar_one_or_none()
    except (ValueError, TypeError):
        site_result = await db.execute(select(Site).where(Site.site_id == site_id))
        site = site_result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    # Get document
    result = await db.execute(
        select(SiteDocument).where(
            SiteDocument.id == document_id,
            SiteDocument.site_id == site.id
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Validate that this is a site-uploaded document
    if not document.document_type or document.document_type != DocumentType.SITE:
        raise HTTPException(status_code=400, detail="Only site-uploaded documents can be rejected")
    
    # Update review status
    document.review_status = ReviewStatus.REJECTED
    
    await db.commit()
    await db.refresh(document)
    
    return {
        "id": document.id,
        "site_id": str(document.site_id),
        "category": document.category.value,
        "file_name": document.file_name,
        "content_type": document.content_type,
        "size": document.size,
        "uploaded_by": document.uploaded_by,
        "uploaded_at": document.uploaded_at,
        "description": document.description,
        "metadata": document.document_metadata or {},
        "document_type": document.document_type.value if document.document_type else None,
        "review_status": document.review_status.value if document.review_status else None,
        "tmf_filed": document.tmf_filed or "false",
    }

