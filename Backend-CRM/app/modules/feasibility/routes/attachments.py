"""
Feasibility Attachment endpoints for Protocol Synopsis management.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID
from pathlib import Path
from datetime import datetime, timezone
import uuid
import os
import logging
import aiofiles

from app.db import get_db
from app.models import StudySite, FeasibilityAttachment, FeasibilityRequest, FeasibilityRequestStatus
from app.auth import get_current_user_optional
from app.config import settings
from app.utils.log_sanitize import sfmt
from app import schemas
from fastapi.responses import FileResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/feasibility-attachments/{study_site_id}", response_model=schemas.FeasibilityAttachmentResponse)
async def upload_feasibility_attachment(
    study_site_id: UUID,
    file: UploadFile = File(...),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload Protocol Synopsis attachment for a feasibility request.
    Only one attachment per study_site_id is allowed (replaces existing).
    """
    try:
        logger.info(f"Upload request received for study_site_id: {sfmt(study_site_id)}, filename: {sfmt(file.filename)}")
        
        # Verify study_site exists
        study_site_result = await db.execute(
            select(StudySite).where(StudySite.id == study_site_id)
        )
        study_site = study_site_result.scalar_one_or_none()
        
        if not study_site:
            logger.warning(f"Study site not found: {study_site_id}")
            raise HTTPException(status_code=404, detail="Study site not found")
        
        # Check if feasibility has already been submitted AND attachment already exists
        # Only prevent upload if: request is COMPLETED AND attachment already exists
        # This allows uploading Protocol Synopsis even after form submission, but prevents replacement once uploaded
        requests_result = await db.execute(
            select(FeasibilityRequest)
            .where(FeasibilityRequest.study_site_id == study_site_id)
            .where(FeasibilityRequest.status == FeasibilityRequestStatus.COMPLETED.value)
        )
        completed_request = requests_result.scalar_one_or_none()
        
        # Check if attachment already exists
        existing_attachment_result = await db.execute(
            select(FeasibilityAttachment).where(FeasibilityAttachment.study_site_id == study_site_id)
        )
        existing_attachment = existing_attachment_result.scalar_one_or_none()
        
        # Only prevent if BOTH conditions are true: request is completed AND attachment exists
        if completed_request and existing_attachment:
            logger.warning(f"Cannot upload Protocol Synopsis - feasibility already completed and attachment exists for study_site_id: {study_site_id}")
            raise HTTPException(
                status_code=400,
                detail="Cannot upload Protocol Synopsis after feasibility form has been submitted and attachment already exists"
            )
        
        # Create upload directory if it doesn't exist.
        # Anchor to Backend-CRM/ (repo root) so the path is stable regardless of
        # where this module lives in the package tree.
        upload_dir_base = Path(settings.upload_dir)
        if not upload_dir_base.is_absolute():
            import pathlib
            repo_root = pathlib.Path(__file__).resolve().parents[4]  # app/modules/feasibility/routes/ -> Backend-CRM/
            upload_dir_base = repo_root / upload_dir_base

        upload_dir = upload_dir_base / "feasibility_attachments"
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        file_ext = Path(file.filename).suffix if file.filename else ""
        file_id = uuid.uuid4()
        file_name_stored = f"{file_id}{file_ext}"
        file_path = upload_dir / file_name_stored
        
        # Save file
        async with aiofiles.open(file_path, "wb") as buffer:
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                await buffer.write(chunk)

        file_size = file_path.stat().st_size
        
        # Check if attachment already exists (replace it)
        # Note: We already checked above if upload is allowed (not if completed + exists)
        existing_result = await db.execute(
            select(FeasibilityAttachment).where(FeasibilityAttachment.study_site_id == study_site_id)
        )
        existing = existing_result.scalar_one_or_none()
        
        # Additional safety check: prevent replacement if request is completed (file is immutable after submission)
        if existing and completed_request:
            # Clean up the new file since we can't replace
            if file_path.exists():
                file_path.unlink()
            logger.warning(f"Cannot replace Protocol Synopsis after completion for study_site_id: {study_site_id}")
            raise HTTPException(
                status_code=400,
                detail="Cannot replace Protocol Synopsis after feasibility form has been submitted"
            )
        
        if existing:
            # Delete old file
            old_file_path = Path(existing.file_path)
            if old_file_path.exists():
                old_file_path.unlink()
            
            # Update existing record
            existing.file_path = str(file_path)
            existing.file_name = file.filename or "unknown"
            existing.content_type = file.content_type or "application/octet-stream"
            existing.size = file_size
            existing.uploaded_by = current_user.get("user_id") if current_user else None
            existing.uploaded_at = datetime.now(timezone.utc)
            
            await db.commit()
            await db.refresh(existing)
            
            return {
                "id": existing.id,
                "study_site_id": existing.study_site_id,
                "file_name": existing.file_name,
                "file_path": existing.file_path,
                "content_type": existing.content_type,
                "size": existing.size,
                "uploaded_by": existing.uploaded_by,
                "uploaded_at": existing.uploaded_at
            }
        else:
            # Create new attachment record
            attachment = FeasibilityAttachment(
                study_site_id=study_site_id,
                file_path=str(file_path),
                file_name=file.filename or "unknown",
                content_type=file.content_type or "application/octet-stream",
                size=file_size,
                uploaded_by=current_user.get("user_id") if current_user else None
            )
            db.add(attachment)
            await db.commit()
            await db.refresh(attachment)
            
            return {
                "id": attachment.id,
                "study_site_id": attachment.study_site_id,
                "file_name": attachment.file_name,
                "file_path": attachment.file_path,
                "content_type": attachment.content_type,
                "size": attachment.size,
                "uploaded_by": attachment.uploaded_by,
                "uploaded_at": attachment.uploaded_at
            }
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 400, 404)
        raise
    except Exception as e:
        # Clean up file if database operation fails
        if 'file_path' in locals() and file_path.exists():
            file_path.unlink()
        logger.error(f"Error uploading attachment: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload attachment: {str(e)}")


@router.get("/feasibility-attachments/{study_site_id}", response_model=Optional[schemas.FeasibilityAttachmentResponse])
async def get_feasibility_attachment(
    study_site_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get Protocol Synopsis attachment for a study_site.
    """
    result = await db.execute(
        select(FeasibilityAttachment).where(FeasibilityAttachment.study_site_id == study_site_id)
    )
    attachment = result.scalar_one_or_none()
    
    if not attachment:
        return None
    
    return {
        "id": attachment.id,
        "study_site_id": attachment.study_site_id,
        "file_name": attachment.file_name,
        "file_path": attachment.file_path,
        "content_type": attachment.content_type,
        "size": attachment.size,
        "uploaded_by": attachment.uploaded_by,
        "uploaded_at": attachment.uploaded_at
    }


@router.get("/feasibility-attachments/{study_site_id}/download")
async def download_feasibility_attachment(
    study_site_id: UUID,
    token: Optional[str] = Query(None, description="Token for public access (no auth required)"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Download Protocol Synopsis attachment.
    Public access if token is provided, otherwise requires authentication.
    """
    # If token is provided, verify it's valid
    if token:
        request_result = await db.execute(
            select(FeasibilityRequest).where(FeasibilityRequest.token == token)
        )
        request = request_result.scalar_one_or_none()
        
        if not request:
            raise HTTPException(status_code=404, detail="Invalid token")
        
        # Use the request's study_site_id
        study_site_id = request.study_site_id
    
    result = await db.execute(
        select(FeasibilityAttachment).where(FeasibilityAttachment.study_site_id == study_site_id)
    )
    attachment = result.scalar_one_or_none()
    
    if not attachment:
        raise HTTPException(status_code=404, detail="Protocol Synopsis not found")
    
    file_path = Path(attachment.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on server")
    
    return FileResponse(
        path=str(file_path),
        filename=attachment.file_name,
        media_type=attachment.content_type
    )


@router.delete("/feasibility-attachments/{study_site_id}")
async def delete_feasibility_attachment(
    study_site_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete Protocol Synopsis attachment.
    Only allowed if feasibility form has not been sent yet.
    """
    # Verify study_site exists
    study_site_result = await db.execute(
        select(StudySite).where(StudySite.id == study_site_id)
    )
    study_site = study_site_result.scalar_one_or_none()
    
    if not study_site:
        raise HTTPException(status_code=404, detail="Study site not found")
    
    # Check if feasibility has already been sent
    requests_result = await db.execute(
        select(FeasibilityRequest)
        .where(FeasibilityRequest.study_site_id == study_site_id)
        .where(FeasibilityRequest.status == FeasibilityRequestStatus.COMPLETED.value)
    )
    completed_request = requests_result.scalar_one_or_none()
    
    if completed_request:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete Protocol Synopsis after feasibility form has been submitted"
        )
    
    result = await db.execute(
        select(FeasibilityAttachment).where(FeasibilityAttachment.study_site_id == study_site_id)
    )
    attachment = result.scalar_one_or_none()
    
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    # Delete file
    file_path = Path(attachment.file_path)
    if file_path.exists():
        file_path.unlink()
    
    # Delete database record
    await db.delete(attachment)
    await db.commit()
    
    return {"message": "Protocol Synopsis deleted successfully"}
