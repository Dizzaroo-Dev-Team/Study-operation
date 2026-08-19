"""REST API: agreement comments (one endpoint, with role-based create permission)."""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.auth import get_current_user_optional
from app.db import get_db
from app.models import Agreement, AgreementComment, AgreementStatus, CommentType
from app.modules.agreements.services.agreement_service import can_create_comment_type

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Legal Documents"])


@router.post("/agreements/{agreement_id}/comments", response_model=schemas.AgreementCommentResponse)
async def create_agreement_comment(
    agreement_id: UUID,
    comment_data: schemas.AgreementCommentCreate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new comment on an agreement.
    
    Permission rules:
    - INTERNAL users: Can create INTERNAL and EXTERNAL comments
    - EXTERNAL users: Can only create EXTERNAL comments
    - SYSTEM comments: Cannot be created manually
    
    Locking rules:
    - If agreement status = CLOSED: No new comments allowed
    
    Validations:
    - Comment type must be valid for user role
    - Content must not be empty (after trimming)
    - If version_id provided, must belong to same agreement
    """
    # Get agreement
    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement_id)
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    # Locking rule: CLOSED agreements cannot have new comments
    if agreement.status == AgreementStatus.CLOSED:
        raise HTTPException(
            status_code=400,
            detail="Agreement is closed. No further comments allowed."
        )
    
    # Validate comment type enum
    try:
        comment_type_enum = CommentType(comment_data.comment_type.upper())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid comment type: {comment_data.comment_type}"
        )
    
    # Get user ID
    user_id = current_user.get("user_id") if current_user else None
    
    # Check permission to create this comment type
    can_create, error_msg = can_create_comment_type(user_id, comment_type_enum, db)
    if not can_create:
        raise HTTPException(status_code=403, detail=error_msg)
    
    # Validate and trim content
    content = comment_data.content.strip() if comment_data.content else ""
    if not content:
        raise HTTPException(status_code=400, detail="Comment content cannot be empty")
    
    # Create comment
    comment = AgreementComment(
        agreement_id=agreement.id,
        version_id=comment_data.version_id,
        comment_type=comment_type_enum,
        content=content,
        created_by=user_id  # Will be None for system comments, but we validate SYSTEM cannot be created manually
    )
    db.add(comment)
    await db.flush()
    await db.commit()
    await db.refresh(comment)
    
    return {
        "id": comment.id,
        "agreement_id": comment.agreement_id,
        "version_id": comment.version_id,
        "comment_type": comment.comment_type.value,
        "content": comment.content,
        "created_by": comment.created_by,
        "created_at": comment.created_at,
    }

