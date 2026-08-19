"""REST API: Template clause composition + materialisation.

Endpoints:
  GET    /templates/{id}/clauses                  – list clauses in template
  POST   /templates/{id}/clauses                  – insert clause
  DELETE /templates/{id}/clauses/{tc_id}          – remove clause
  PATCH  /templates/{id}/clauses/reorder          – set new sort order
  PATCH  /templates/{id}/clauses/{tc_id}/lock     – change lock/editable flags
  PATCH  /templates/{id}/clauses/{tc_id}/override – save editable override
  PATCH  /templates/{id}/clauses/{tc_id}/pin      – change pinned version
  POST   /templates/{id}/materialize              – return final Tiptap JSON doc

The save endpoint for the template canvas uses validate_locked_clauses()
server-side before accepting any content update — this is the real lock gate,
not the frontend ClauseBlock visual lock.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_optional
from app.db import get_db
from app.models.agreement import CompositionMode, StudyTemplate
from app.models.clause import Clause, ClauseVersion
from app.modules.agreements.services import template_composition_service as tcs
from app.modules.agreements.services.clause_materializer import materialize_template

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Clause Library"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class InsertClauseBody(BaseModel):
    clause_id:  UUID
    sort_order: Optional[int] = None


class ReorderBody(BaseModel):
    ordered_ids: List[UUID]  # TemplateClause IDs in desired order


class LockUpdateBody(BaseModel):
    is_locked:   bool
    is_editable: bool


class OverrideBody(BaseModel):
    override_content_json: Dict[str, Any]


class PinVersionBody(BaseModel):
    clause_version_id: UUID


class ValidateSaveBody(BaseModel):
    """Used by the frontend canvas to server-validate locked clauses before saving."""
    document_json: Dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_composed_template(db: AsyncSession, template_id: UUID) -> StudyTemplate:
    result = await db.execute(
        select(StudyTemplate).where(StudyTemplate.id == template_id)
    )
    tmpl = result.scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if tmpl.composition_mode != CompositionMode.CLAUSE_COMPOSED:
        raise HTTPException(
            status_code=400,
            detail=(
                "Template is not in CLAUSE_COMPOSED mode. "
                "Update composition_mode to CLAUSE_COMPOSED before adding clauses."
            ),
        )
    return tmpl


def _serialize_tc(tc: Any) -> dict:
    clause = tc.clause if hasattr(tc, "clause") and tc.clause else None
    pv     = tc.pinned_version if hasattr(tc, "pinned_version") and tc.pinned_version else None
    return {
        "id":                       tc.id,
        "template_id":              tc.template_id,
        "clause_id":                tc.clause_id,
        "pinned_clause_version_id": tc.pinned_clause_version_id,
        "sort_order":               tc.sort_order,
        "is_locked":                tc.is_locked == "true",
        "is_editable":              tc.is_editable == "true",
        "has_override":             tc.override_content_json is not None,
        # Denormalised clause info so the UI doesn't need a second fetch
        "clause_title":    clause.title    if clause else None,
        "clause_category": clause.category if clause else None,
        "lock_policy":     (
            clause.lock_policy.value
            if clause and hasattr(clause.lock_policy, "value")
            else (clause.lock_policy if clause else None)
        ),
        "pinned_version_number": pv.version_number if pv else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/templates/{template_id}/clauses")
async def list_template_clauses(
    template_id: UUID,
    db:          AsyncSession = Depends(get_db),
):
    """Return ordered clause slots for a CLAUSE_COMPOSED template."""
    await _get_composed_template(db, template_id)
    clauses = await tcs.get_template_clauses(db, template_id)
    # Eagerly load relationships for the response
    for tc in clauses:
        _ = tc.clause         # noqa: triggers lazy load
        _ = tc.pinned_version  # noqa
    return [_serialize_tc(tc) for tc in clauses]


@router.post("/templates/{template_id}/clauses", status_code=201)
async def insert_clause(
    template_id:  UUID,
    body:         InsertClauseBody,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db:           AsyncSession   = Depends(get_db),
):
    """Add a clause to a template, pinned to its current published version."""
    await _get_composed_template(db, template_id)
    try:
        tc = await tcs.insert_clause_into_template(
            db,
            template_id=template_id,
            clause_id=body.clause_id,
            sort_order=body.sort_order,
        )
        await db.commit()
        await db.refresh(tc)
        _ = tc.clause
        _ = tc.pinned_version
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        await db.rollback()
        logger.exception("insert_clause: error")
        raise HTTPException(status_code=500, detail="Failed to insert clause")

    return _serialize_tc(tc)


@router.delete("/templates/{template_id}/clauses/{tc_id}", status_code=204)
async def remove_clause(
    template_id:  UUID,
    tc_id:        UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db:           AsyncSession   = Depends(get_db),
):
    await _get_composed_template(db, template_id)
    try:
        await tcs.remove_clause_from_template(db, tc_id)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        await db.rollback()
        logger.exception("remove_clause: error")
        raise HTTPException(status_code=500, detail="Failed to remove clause")


@router.patch("/templates/{template_id}/clauses/reorder")
async def reorder_clauses(
    template_id:  UUID,
    body:         ReorderBody,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db:           AsyncSession   = Depends(get_db),
):
    """Accept a full ordered list of TemplateClause IDs and persist the new order."""
    await _get_composed_template(db, template_id)
    try:
        await tcs.reorder_template_clauses(db, template_id, body.ordered_ids)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("reorder_clauses: error")
        raise HTTPException(status_code=500, detail="Failed to reorder clauses")

    return {"ok": True}


@router.patch("/templates/{template_id}/clauses/{tc_id}/lock")
async def update_clause_lock(
    template_id:  UUID,
    tc_id:        UUID,
    body:         LockUpdateBody,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db:           AsyncSession   = Depends(get_db),
):
    """Override the lock / editable flags for one clause slot in this template."""
    await _get_composed_template(db, template_id)
    try:
        tc = await tcs.update_clause_lock(
            db, tc_id,
            is_locked=body.is_locked,
            is_editable=body.is_editable,
        )
        await db.commit()
        await db.refresh(tc)
        _ = tc.clause
        _ = tc.pinned_version
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        await db.rollback()
        logger.exception("update_clause_lock: error")
        raise HTTPException(status_code=500, detail="Failed to update lock")

    return _serialize_tc(tc)


@router.patch("/templates/{template_id}/clauses/{tc_id}/override")
async def save_clause_override(
    template_id:  UUID,
    tc_id:        UUID,
    body:         OverrideBody,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db:           AsyncSession   = Depends(get_db),
):
    """Save a per-template content edit for an EDITABLE clause slot.

    This does NOT create a new ClauseVersion — the edit is local to this template.
    """
    await _get_composed_template(db, template_id)
    try:
        tc = await tcs.save_clause_override(
            db, tc_id,
            override_content_json=body.override_content_json,
        )
        await db.commit()
        await db.refresh(tc)
        _ = tc.clause
        _ = tc.pinned_version
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        await db.rollback()
        logger.exception("save_clause_override: error")
        raise HTTPException(status_code=500, detail="Failed to save override")

    return _serialize_tc(tc)


@router.patch("/templates/{template_id}/clauses/{tc_id}/pin")
async def pin_version(
    template_id:  UUID,
    tc_id:        UUID,
    body:         PinVersionBody,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db:           AsyncSession   = Depends(get_db),
):
    """Change which ClauseVersion this template slot is pinned to."""
    await _get_composed_template(db, template_id)
    try:
        tc = await tcs.pin_clause_version(
            db, tc_id,
            clause_version_id=body.clause_version_id,
        )
        await db.commit()
        await db.refresh(tc)
        _ = tc.clause
        _ = tc.pinned_version
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        await db.rollback()
        logger.exception("pin_version: error")
        raise HTTPException(status_code=500, detail="Failed to pin version")

    return _serialize_tc(tc)


@router.post("/templates/{template_id}/validate-locks")
async def validate_locked_clauses(
    template_id: UUID,
    body:        ValidateSaveBody,
    db:          AsyncSession = Depends(get_db),
):
    """SERVER-SIDE lock validation.

    The frontend canvas calls this before saving any document content.
    Returns HTTP 422 with violation details if locked clause content has been
    tampered with.  Returns {"ok": true} when all locks are intact.

    This is the REAL security gate — the frontend ClauseBlock visual lock is
    cosmetic only.
    """
    await _get_composed_template(db, template_id)
    violations = await tcs.validate_locked_clauses(
        db, template_id, body.document_json
    )
    if violations:
        raise HTTPException(
            status_code=422,
            detail={
                "error":      "locked_clause_violation",
                "violations": violations,
                "message":    "One or more locked clauses were modified. "
                              "Save rejected.",
            },
        )
    return {"ok": True}


@router.post("/templates/{template_id}/materialize")
async def materialize(
    template_id:  UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db:           AsyncSession   = Depends(get_db),
):
    """Materialize the template into a single Tiptap JSON document.

    The returned JSON has the same shape as AgreementDocument.document_content
    and can be directly saved as a new document version.
    No DB writes — read-only preview.
    """
    await _get_composed_template(db, template_id)
    try:
        doc = await materialize_template(db, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("materialize: error for template %s", template_id)
        raise HTTPException(status_code=500, detail="Materialisation failed")

    return {"document_json": doc}
