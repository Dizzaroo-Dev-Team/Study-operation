"""
unified_notify.py — endpoints for the NOTIFY + BROADCAST modules:
  POST /api/agreements/{id}/notify     (auth)  — fire an in-app notification
  POST /api/agreements/{id}/broadcast  (owner) — real per-recipient delivery

Permanent product path (the former WORKFLOW_UNIFIED gate was removed — always on).
notify is auth-gated; broadcast is owner-gated.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.models import Agreement
from app.modules.agreements.services import unified_notify
from app.modules.workflows import service as wf_service

router = APIRouter()


class NotifyRequest(BaseModel):
    message: Optional[str] = None


class Recipient(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None


class BroadcastRequest(BaseModel):
    recipients: list[Recipient] = Field(default_factory=list)
    attach_document: bool = False
    message: Optional[str] = None


@router.post("/agreements/{agreement_id}/notify")
async def run_notify(agreement_id: UUID, payload: NotifyRequest,
                     current_user: dict = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    """Fire an in-app notification for this agreement (reuses create_agreement_notice)."""
    agreement = await db.get(Agreement, agreement_id)
    if agreement is None:
        raise HTTPException(status_code=404, detail="Agreement not found.")
    msg = payload.message or f"Update on '{agreement.title}'."
    return await unified_notify.notify(db, agreement, msg)


@router.post("/agreements/{agreement_id}/broadcast")
async def run_broadcast(agreement_id: UUID, payload: BroadcastRequest,
                        current_user: dict = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """Owner (creator-owns): distribute the final copy to each recipient (real email)."""
    agreement = await db.get(Agreement, agreement_id)
    if agreement is None:
        raise HTTPException(status_code=404, detail="Agreement not found.")
    owner = await wf_service.is_agreement_owner(db, str(agreement_id), current_user.get("user_id"))
    if not owner["is_owner"]:
        raise HTTPException(status_code=403, detail="Only the agreement creator may distribute the final copy.")
    return await unified_notify.broadcast(
        db, agreement, [r.model_dump() for r in payload.recipients],
        attach_document=payload.attach_document, message=payload.message)
