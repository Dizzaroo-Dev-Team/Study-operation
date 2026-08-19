"""
unified_review.py — the unified review endpoint group: /api/agreements/{id}/review/*

Permanent product review path (the former WORKFLOW_UNIFIED gate was removed — always
on). dispatch/status are owner/auth-gated; context/respond are token-authenticated.

  POST /agreements/{id}/review/dispatch  (owner)  — send the doc to a reviewer (reuses send-for-review)
  GET  /agreements/{id}/review/context   (token)  — should the reused review page show Approve/Send-back?
  POST /agreements/{id}/review/respond   (token)  — reviewer approve / send_back -> engine advances
  GET  /agreements/{id}/review/status     (auth)  — owner panel state
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db, transactional
from app.modules.agreements.services import unified_review
from app.modules.workflows import service as wf_service

router = APIRouter()


class DispatchReviewRequest(BaseModel):
    recipient_email: str
    message: Optional[str] = None


class ParallelDispatchRequest(BaseModel):
    recipients: dict[str, str]  # {branch_id: email}


class RespondRequest(BaseModel):
    token: str
    decision: str  # "approve" | "send_back"


@router.post("/agreements/{agreement_id}/review/dispatch")
async def review_dispatch(agreement_id: UUID, payload: DispatchReviewRequest,
                          current_user: dict = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Owner (creator-owns): send the document to a reviewer."""
    owner = await wf_service.is_agreement_owner(db, str(agreement_id), current_user.get("user_id"))
    if not owner["is_owner"]:
        raise HTTPException(status_code=403, detail="Only the agreement creator may send for review.")
    # dispatch reuses send_agreement_for_review, which manages its own commit.
    return await unified_review.dispatch(db, str(agreement_id), payload.recipient_email,
                                         payload.message, current_user)


@router.get("/agreements/{agreement_id}/review/context")
async def review_context(agreement_id: UUID, token: str = Query(...),
                         db: AsyncSession = Depends(get_db)):
    """Token-gated: tells the reused review page whether to show unified actions."""
    return await unified_review.context(db, str(agreement_id), token)


@router.post("/agreements/{agreement_id}/review/respond")
async def review_respond(agreement_id: UUID, payload: RespondRequest,
                         db: AsyncSession = Depends(get_db)):
    """Reviewer (token-gated): approve / send_back -> advance the engine. Own commit."""
    return await unified_review.respond(db, str(agreement_id), payload.token, payload.decision)


@router.get("/agreements/{agreement_id}/review/status")
async def review_status(agreement_id: UUID, current_user: dict = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    return await unified_review.status(db, str(agreement_id))


@router.get("/agreements/{agreement_id}/review/parallel-status")
async def review_parallel_status(agreement_id: UUID, current_user: dict = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    """Per-reviewer status for a PARALLEL review step (owner panel). `active=false`
    when the current step isn't a parallel review (the FE then uses the single UI)."""
    return await unified_review.parallel_status(db, str(agreement_id))


@router.post("/agreements/{agreement_id}/review/parallel-dispatch")
async def review_parallel_dispatch(agreement_id: UUID, payload: ParallelDispatchRequest,
                                   current_user: dict = Depends(get_current_user),
                                   db: AsyncSession = Depends(get_db)):
    """Owner (creator-owns): send the secure review link to the open reviewer branch(es)."""
    owner = await wf_service.is_agreement_owner(db, str(agreement_id), current_user.get("user_id"))
    if not owner["is_owner"]:
        raise HTTPException(status_code=403, detail="Only the agreement creator may send for review.")
    from app.models import Agreement
    agreement = await db.get(Agreement, agreement_id)
    if agreement is None:
        raise HTTPException(status_code=404, detail="Agreement not found.")
    # send_agreement_for_review (reused per branch) manages its own commit.
    result = await unified_review.parallel_dispatch(
        db, agreement, payload.recipients, current_user=current_user)
    return result
