"""REST API: per-budget-template freeform notes."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.modules.site_budgeting.db_models import BudgetNote
from app.modules.site_budgeting.dependencies import require_site_budgeting
from app.modules.site_budgeting.repositories import budgeting_repository as repo
from app.modules.site_budgeting.services import audit_service
from app.modules.site_budgeting.validators.schemas import BudgetNoteCreate

router = APIRouter(tags=["Site Budgeting"])


@router.post("/templates/{template_id}/notes", status_code=status.HTTP_201_CREATED)
async def create_note(
    template_id: UUID,
    body: BudgetNoteCreate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    n = BudgetNote(
        budget_template_id=template_id,
        user_id=user.get("user_id"),
        category=body.category,
        body=body.body,
    )
    db.add(n)
    await db.flush()
    await audit_service.write_audit(
        db,
        entity_type="budget_note",
        entity_id=n.id,
        action="CREATE",
        user_id=user.get("user_id"),
        new_value={"category": body.category, "body": body.body[:100]},
    )
    await db.commit()
    return {"id": str(n.id)}


@router.get("/templates/{template_id}/notes")
async def list_notes(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    r = await db.execute(
        select(BudgetNote)
        .where(BudgetNote.budget_template_id == template_id)
        .order_by(BudgetNote.created_at)
    )
    rows = r.scalars().all()
    return [
        {
            "id": str(n.id),
            "category": getattr(n, "category", None),
            "body": n.body,
            "user_id": n.user_id,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in rows
    ]


@router.delete("/templates/{template_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    template_id: UUID,
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    r = await db.execute(
        select(BudgetNote).where(
            BudgetNote.id == note_id,
            BudgetNote.budget_template_id == template_id,
        )
    )
    n = r.scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404, detail="Note not found")
    await db.delete(n)
    await audit_service.write_audit(
        db,
        entity_type="budget_note",
        entity_id=note_id,
        action="DELETE",
        user_id=user.get("user_id"),
    )
    await db.commit()
