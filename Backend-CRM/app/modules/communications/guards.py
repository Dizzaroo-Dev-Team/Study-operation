"""Shared write/access guards for the Communications module (Stage-2 A2).

ONE enforcement pattern, applied to routes via FastAPI ``dependencies=[...]``:

  * ``require_conversation_member`` — authenticated AND can access the conversation
  * ``require_conversation_admin``  — authenticated AND (conversation creator OR privileged)
  * ``require_thread_member``       — authenticated AND can access the thread

The guard runs before the route body and raises 403/404, closing the unlocked
doors uniformly.

The object-access decision reuses the existing checkers in ``app.crud`` — no new
policy. (The conversation checker is itself membership-aware, so guards yield
study-scoped write access.)
"""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.auth import get_current_user_optional
from app.db import get_db


def _require_user_id(current_user: Optional[dict]) -> str:
    user_id = (current_user or {}).get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Authentication required")
    return user_id


async def require_conversation_member(
    conversation_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Authenticated + can access the conversation."""
    user_id = _require_user_id(current_user)
    conv = await crud.get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not await crud.check_user_can_access_conversation_by_role(
        db, user_id, conv, user_email=(current_user or {}).get("email")
    ):
        raise HTTPException(
            status_code=403, detail="You don't have access to this conversation"
        )


async def require_conversation_admin(
    conversation_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Authenticated + (conversation creator OR privileged).

    Used for the ACL-mutating routes (grant/revoke/update-access) where merely
    being able to read the conversation is not enough to manage who else can.
    """
    user_id = _require_user_id(current_user)
    conv = await crud.get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    created_by = str(
        (conv.get("created_by") if isinstance(conv, dict) else getattr(conv, "created_by", None))
        or ""
    ).strip()
    is_privileged = bool((current_user or {}).get("is_privileged"))
    if created_by == str(user_id) or is_privileged:
        return
    raise HTTPException(
        status_code=403, detail="Only the conversation owner can manage access"
    )


async def require_thread_member(
    thread_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Authenticated + can access the thread."""
    user_id = _require_user_id(current_user)
    thread = await crud.get_thread(db, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not await crud.check_user_can_access_thread(
        db, user_id, thread, user_email=(current_user or {}).get("email")
    ):
        raise HTTPException(
            status_code=403, detail="You don't have access to this thread"
        )


__all__ = [
    "require_conversation_member",
    "require_conversation_admin",
    "require_thread_member",
]
