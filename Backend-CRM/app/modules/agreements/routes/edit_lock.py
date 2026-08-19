"""REST API: agreement edit-lock primitives (30-minute soft lock for editor sessions)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_optional
from app.db import get_db
from app.models import Agreement

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Legal Documents"])


@router.get("/agreements/{agreement_id}/edit-lock")
async def get_edit_lock_status(
    agreement_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current edit lock status for an agreement.
    
    Returns:
        - locked: bool - Whether agreement is currently locked
        - locked_by_user_id: str | None - User ID holding the lock
        - locked_by_user_name: str | None - User name holding the lock
        - locked_at: str | None - ISO timestamp when lock was acquired
        - is_expired: bool - Whether lock has expired (30 min timeout)
        - can_acquire: bool - Whether current user can acquire lock
    """
    from datetime import timedelta
    
    agreement_result = await db.execute(
        select(Agreement).where(Agreement.id == agreement_id)
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    user_id = current_user.get("user_id") if current_user else None
    user_name = current_user.get("name") if current_user else None
    
    # Check if lock exists and is valid
    has_lock = agreement.editing_user_id is not None and agreement.editing_started_at is not None
    
    if has_lock:
        # Check if lock is expired (30 minutes timeout)
        lock_age = datetime.now(timezone.utc) - agreement.editing_started_at
        is_expired = lock_age > timedelta(minutes=30)
        
        # Check if lock is held by current user
        is_own_lock = agreement.editing_user_id == user_id
        
        return {
            "locked": not is_expired,
            "locked_by_user_id": agreement.editing_user_id if not is_expired else None,
            "locked_by_user_name": agreement.editing_user_id if not is_expired else None,  # TODO: Fetch actual user name if needed
            "locked_at": agreement.editing_started_at.isoformat() if agreement.editing_started_at and not is_expired else None,
            "is_expired": is_expired,
            "can_acquire": is_expired or is_own_lock or not has_lock,
        }
    else:
        return {
            "locked": False,
            "locked_by_user_id": None,
            "locked_by_user_name": None,
            "locked_at": None,
            "is_expired": False,
            "can_acquire": True,
        }


@router.post("/agreements/{agreement_id}/edit-lock/acquire")
async def acquire_edit_lock(
    agreement_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Acquire edit lock for an agreement.
    
    Rules:
    - If no lock exists: create lock
    - If lock exists by same user: refresh lock timestamp
    - If lock exists by different user and not expired: return error
    - If lock expired: acquire lock for current user
    
    Locks expire after 30 minutes of inactivity.
    """
    from datetime import timedelta
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found")
    
    agreement_result = await db.execute(
        select(Agreement).where(Agreement.id == agreement_id)
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    # Check if lock exists
    has_lock = agreement.editing_user_id is not None and agreement.editing_started_at is not None
    
    if has_lock:
        # Check if lock is expired
        lock_age = datetime.now(timezone.utc) - agreement.editing_started_at
        is_expired = lock_age > timedelta(minutes=30)
        
        # Check if lock is held by current user
        is_own_lock = agreement.editing_user_id == user_id
        
        if not is_expired and not is_own_lock:
            # Lock is held by another user
            raise HTTPException(
                status_code=409,
                detail=f"Agreement is currently being edited by another user (locked at {agreement.editing_started_at.isoformat()})"
            )
    
    # Acquire or refresh lock
    agreement.editing_user_id = user_id
    agreement.editing_started_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    return {
        "status": "success",
        "message": "Edit lock acquired",
        "locked_at": agreement.editing_started_at.isoformat(),
    }


@router.post("/agreements/{agreement_id}/edit-lock/release")
async def release_edit_lock(
    agreement_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Release edit lock for an agreement.
    
    Only the user holding the lock can release it, unless lock is expired.
    """
    agreement_result = await db.execute(
        select(Agreement).where(Agreement.id == agreement_id)
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    user_id = current_user.get("user_id") if current_user else None
    
    # Check if lock exists
    if agreement.editing_user_id is None:
        # No lock to release
        return {
            "status": "success",
            "message": "No lock to release",
        }
    
    # Check if lock is expired (anyone can release expired locks)
    from datetime import timedelta
    if agreement.editing_started_at:
        lock_age = datetime.now(timezone.utc) - agreement.editing_started_at
        is_expired = lock_age > timedelta(minutes=30)
    else:
        is_expired = True
    
    # Check if lock is held by current user
    is_own_lock = agreement.editing_user_id == user_id
    
    if not is_expired and not is_own_lock:
        raise HTTPException(
            status_code=403,
            detail="Cannot release lock held by another user"
        )
    
    # Release lock
    agreement.editing_user_id = None
    agreement.editing_started_at = None
    
    await db.commit()
    
    return {
        "status": "success",
        "message": "Edit lock released",
    }

