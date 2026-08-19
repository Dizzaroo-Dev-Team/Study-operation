"""
ISF Auth router — thin adapter over the CRM's existing user/auth system.

Endpoints used by the ISF frontend (isfDocument.service.js):
  GET  /api/isf/auth/me         → current user from JWT
  GET  /api/isf/auth/users      → paginated user list (from CRM DB)
  POST /api/isf/auth/login      → not used in integrated mode; returns error

All hardcoded mock users removed — every response comes from real data.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from datetime import datetime, timezone

from app.db import get_db
from app import crud
from app.modules.isf.models.user import UserResponse, UserRole
from app.modules.isf.utils.auth import get_current_user, _map_role

router = APIRouter()


def _crm_user_to_isf(u) -> UserResponse:
    """Convert a CRM SQLAlchemy User row to an ISF UserResponse."""
    crm_role = getattr(u, "role", "participant") or "participant"
    isf_role = _map_role(crm_role)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    return UserResponse(
        id=str(u.id),
        user_name=getattr(u, "name", None) or u.email.split("@")[0],
        email=u.email,
        role=isf_role,
        permissions=_permissions_for(isf_role),
        assigned_studies=[],   # resolved from CRM context, not stored here
        is_active=getattr(u, "is_active", True),
        created_at=getattr(u, "created_at", now) or now,
        updated_at=getattr(u, "updated_at", now) or now,
    )


def _permissions_for(role: UserRole) -> List[str]:
    base = ["read_documents"]
    if role in (UserRole.SYSTEM_ADMIN, UserRole.STUDY_LEAD, UserRole.QC_LEAD, UserRole.APPROVER):
        base += ["write_documents", "approve_documents", "admin"]
    elif role in (UserRole.SITE_MANAGER, UserRole.DATA_MANAGER, UserRole.REVIEWER):
        base += ["write_documents"]
    return base


@router.post("/login")
async def login():
    """
    Login is handled by the CRM's own /api/auth/login endpoint.
    This stub returns a clear error so the ISF frontend is never confused.
    """
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Login is managed by the CRM. Use /api/auth/login instead.",
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: UserResponse = Depends(get_current_user),
):
    """Return the currently authenticated CRM user as an ISF UserResponse."""
    return current_user


@router.get("/users", response_model=List[UserResponse])
async def get_users(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: UserResponse = Depends(get_current_user),
):
    """
    Return paginated CRM users as ISF UserResponse objects.
    Used by isfDocument.service.js to resolve the uploader's user ID.
    """
    try:
        skip = (page - 1) * limit
        users = await crud.list_users(db, limit=limit, offset=skip)
        return [_crm_user_to_isf(u) for u in users]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch users: {exc}",
        )
