"""Assistant HTTP route layer."""
from __future__ import annotations

from fastapi import APIRouter

from app.modules.assistant.live_eval.routes import router as live_eval_router
from app.modules.assistant.memory.routes import router as memory_router

from .assistant import router as _assistant_router

# One aggregated router mounted by app.main under /api. Transport endpoints
# (stream/message/approve/cancel) plus the Orbit-memory surface and the
# read-only live-eval score surface.
router = APIRouter()
router.include_router(_assistant_router)
router.include_router(memory_router)
router.include_router(live_eval_router)

__all__ = ["router"]
