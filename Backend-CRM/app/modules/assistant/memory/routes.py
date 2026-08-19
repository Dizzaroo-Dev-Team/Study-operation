"""Orbit memory HTTP surface — session-open load + user controls.

All routes are guarded by ``get_current_user`` and scoped to that user's id, so
memory can never be read or mutated across users. Mutations (edit / delete /
exclude) are audited like any other write.

  GET    /assistant/memory/context   welcome-back payload (memory + last-session)
  GET    /assistant/memory           list the user's memories (management UI)
  PATCH  /assistant/memory/{id}      edit an item's text
  POST   /assistant/memory/{id}/exclude   opt an item out (kept, never surfaced)
  DELETE /assistant/memory/{id}      delete an item
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import crud
from app.auth import get_current_user
from app.db import AsyncSessionLocal, transactional
from app.modules.assistant.memory import phi_filter, repository as repo, service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant/memory", tags=["Assistant"])


class MemoryEditIn(BaseModel):
    text: str


async def _entitled_study_codes(current_user: dict) -> set[str]:
    """The study-code tokens the user is CURRENTLY entitled to — used to drop
    stale study references from memory at load. Reuses the guarded studies route
    (IAM entitlement is its source of truth), so we never surface a lost-access
    study."""
    codes: set[str] = set()
    try:
        from app.modules.sites.routes.sites import list_studies

        studies = await list_studies(current_user=current_user)
        for s in studies or []:
            for field in (s.get("study_id"), s.get("name")):
                if not field:
                    continue
                codes.add(str(field).upper())
                tok = phi_filter.extract_study_reference(str(field).upper())
                if tok:
                    codes.add(tok)
    except Exception:  # noqa: BLE001 — on failure, be safe: drop all refs (empty set)
        logger.exception("assistant memory: entitled-studies lookup failed")
    return codes


@router.get("/context")
async def memory_context(current_user: dict = Depends(get_current_user)):
    """Welcome-back payload for session open — a single memory read + entitlement
    re-check. Deliberately does NOT include any "what needs attention" counts;
    the frontend fetches those live/guarded so live data is never remembered."""
    user_id = current_user["user_id"]
    entitled = await _entitled_study_codes(current_user)
    return await service.build_welcome_back(user_id, entitled_codes=entitled)


@router.get("")
async def list_memories(current_user: dict = Depends(get_current_user)):
    """All of the user's memory items (including excluded) for the controls UI."""
    items = await repo.list_memory(current_user["user_id"], include_excluded=True)
    return [
        {
            "id": str(it.id),
            "type": it.type,
            "text": it.text,
            "salience": it.salience,
            "hits": it.hits,
            "excluded": bool(it.excluded),
            "created_at": it.created_at.isoformat() if it.created_at else None,
        }
        for it in items
    ]


async def _load_owned(db, memory_id: str, user_id: str):
    try:
        mid = UUID(memory_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Memory not found")
    item = await repo.get_memory(db, mid, user_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return item


@router.patch("/{memory_id}")
async def edit_memory(
    memory_id: str, body: MemoryEditIn, current_user: dict = Depends(get_current_user)
):
    """Edit an item's text. Rejected if the new text reads as PHI/record content."""
    user_id = current_user["user_id"]
    new_text = (body.text or "").strip()
    if not phi_filter.is_safe_memory(new_text):
        raise HTTPException(status_code=400, detail="Text is empty or looks like sensitive content")
    async with AsyncSessionLocal() as db:
        async with transactional(db):
            item = await _load_owned(db, memory_id, user_id)
            item.text = new_text[:500]
            await crud.create_audit_log(
                db, user=user_id, action="assistant.memory.edit",
                target_type="assistant_memory", target_id=memory_id,
                details={"via": "orbit_memory"},
            )
    return {"status": "updated"}


@router.post("/{memory_id}/exclude")
async def exclude_memory(memory_id: str, current_user: dict = Depends(get_current_user)):
    """Opt an item out — kept for provenance but never surfaced or re-derived."""
    user_id = current_user["user_id"]
    async with AsyncSessionLocal() as db:
        async with transactional(db):
            item = await _load_owned(db, memory_id, user_id)
            item.excluded = True
            await crud.create_audit_log(
                db, user=user_id, action="assistant.memory.exclude",
                target_type="assistant_memory", target_id=memory_id,
                details={"via": "orbit_memory"},
            )
    return {"status": "excluded"}


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, current_user: dict = Depends(get_current_user)):
    """Delete an item outright."""
    user_id = current_user["user_id"]
    async with AsyncSessionLocal() as db:
        async with transactional(db):
            item = await _load_owned(db, memory_id, user_id)
            await db.delete(item)
            await crud.create_audit_log(
                db, user=user_id, action="assistant.memory.delete",
                target_type="assistant_memory", target_id=memory_id,
                details={"via": "orbit_memory"},
            )
    return {"status": "deleted"}
