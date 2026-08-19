"""REST API: external webhooks (mock provider for test SMS/Email, Zoho Sign placeholder)."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.config import settings
from app.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Legal Documents"])


@router.post("/webhooks/mock_provider")
async def webhook_mock_provider(
    payload: schemas.WebhookPayload,
    x_mock_token: Optional[str] = Header(None, alias="X-MOCK-TOKEN")
):
    # Validate token
    if x_mock_token != settings.mock_provider_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Enqueue webhook processing task
    from app.workers.tasks import process_webhook_task
    process_webhook_task.delay(payload.dict())
    
    return {"status": "accepted"}


@router.post("/webhooks/zoho-sign")
async def zoho_sign_webhook(
    request: Request,
):
    """
    Phase 3: Zoho Sign is no longer an active dependency.

    This endpoint is intentionally disabled to guarantee we never react to
    Zoho events or attempt to download documents from Zoho.
    """
    logger.info("Rejected Zoho webhook (disabled): Zoho Sign is no longer active")
    raise HTTPException(status_code=410, detail="Zoho Sign webhook is disabled (internal signing only).")
