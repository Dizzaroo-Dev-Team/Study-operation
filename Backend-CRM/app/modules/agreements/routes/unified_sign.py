"""
unified_sign.py — the NEW unified signing endpoint group: /api/agreements/{id}/sign/*

Compliant-by-design (built from the harvested otp.py core via the unified_signing
service). This is the permanent product signing path (the former WORKFLOW_UNIFIED
gate was removed — it is always on). Dispatch is owner-only; request-otp / submit are
token-authenticated.

  POST /agreements/{id}/sign/dispatch     (owner-only) — send the secure link to the open slot(s)
  POST /agreements/{id}/sign/request-otp  (token)      — email a one-time code (lockout-protected)
  POST /agreements/{id}/sign/submit       (token)      — verify code + record the manifested signature
  GET  /agreements/{id}/sign/status       (auth)       — slot states for the panel
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db, transactional
from app.models import Agreement
from app.modules.agreements.services import unified_signing
from app.modules.workflows import service as wf_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class DispatchRequest(BaseModel):
    recipients: dict[str, str] = Field(default_factory=dict)  # {slot_id: email}


class RequestOtpRequest(BaseModel):
    token: str


class SubmitRequest(BaseModel):
    token: str
    otp: str
    signer_name: str
    signer_title: Optional[str] = None
    meaning: Optional[str] = None  # signer-affirmed intent


@router.post("/agreements/{agreement_id}/sign/dispatch")
async def sign_dispatch(agreement_id: UUID, payload: DispatchRequest, request: Request,
                        current_user: dict = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """Owner action (creator-owns): send the secure signing link to the open slot(s)."""
    agreement = await db.get(Agreement, agreement_id)
    if agreement is None:
        raise HTTPException(status_code=404, detail="Agreement not found.")
    owner = await wf_service.is_agreement_owner(db, str(agreement_id), current_user.get("user_id"))
    if not owner["is_owner"]:
        raise HTTPException(status_code=403, detail="Only the agreement creator may send for signature.")
    async with transactional(db):
        result = await unified_signing.dispatch(
            db, agreement, payload.recipients, created_by=current_user.get("user_id"))
    return result


@router.post("/agreements/{agreement_id}/sign/request-otp")
async def sign_request_otp(agreement_id: UUID, payload: RequestOtpRequest,
                           db: AsyncSession = Depends(get_db)):
    """Signer action (token-authed): email a one-time code. Manages its own commit."""
    return await unified_signing.request_otp(db, str(agreement_id), payload.token)


@router.post("/agreements/{agreement_id}/sign/submit")
async def sign_submit(agreement_id: UUID, payload: SubmitRequest, request: Request,
                      db: AsyncSession = Depends(get_db)):
    """Signer action (token-authed): verify the code (lockout + failed-attempt audit)
    and record the manifested signature. Manages its own commit."""
    return await unified_signing.submit(
        db, str(agreement_id), payload.token, payload.otp,
        payload.signer_name, payload.signer_title, payload.meaning, _ip(request))


@router.post("/agreements/{agreement_id}/sign/attach-executed")
async def sign_attach_executed(agreement_id: UUID, request: Request,
                               file: UploadFile = File(...),
                               current_user: dict = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    """Owner action (creator-owns): the agreement was signed OFFLINE — attach the executed
    document. Records it as the signed version and completes the engine signing step (so the
    workflow advances to executed, firing the completion bridge, e.g. CDA -> site readiness).
    General alternative to OTP e-signing; any agreement type."""
    agreement = await db.get(Agreement, agreement_id)
    if agreement is None:
        raise HTTPException(status_code=404, detail="Agreement not found.")
    owner = await wf_service.is_agreement_owner(db, str(agreement_id), current_user.get("user_id"))
    if not owner["is_owner"]:
        raise HTTPException(status_code=403, detail="Only the agreement creator may attach the executed document.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    async with transactional(db):
        return await unified_signing.attach_executed(
            db, agreement, data, file.filename, by=current_user.get("user_id"))


@router.get("/agreements/{agreement_id}/sign/status")
async def sign_status(agreement_id: UUID, current_user: dict = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """Slot states for the signing panel."""
    return await unified_signing.status(db, str(agreement_id))
