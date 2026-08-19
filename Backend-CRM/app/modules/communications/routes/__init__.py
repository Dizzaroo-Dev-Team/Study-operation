"""communications HTTP route layer - messages, threads, conversations, email webhooks."""
from __future__ import annotations

from fastapi import APIRouter

from .communications import router as _communications_router
from .email_webhook import router as _email_webhook_router

router = APIRouter()
router.include_router(_communications_router)
router.include_router(_email_webhook_router)

__all__ = ["router"]
