"""REST API: visit-schedule CRUD (per-trial canonical visits + per-template legacy)."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.modules.site_budgeting.db_models import VisitSchedule
from app.modules.site_budgeting.dependencies import require_site_budgeting
from app.modules.site_budgeting.repositories import budgeting_repository as repo
from app.modules.site_budgeting.services import audit_service, budget_totals_cache
from app.modules.site_budgeting.validators.schemas import VisitScheduleCreate

router = APIRouter(tags=["Site Budgeting"])


@router.get("/trials/{trial_id}/visits")
async def list_trial_visits(
    trial_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
    active_only: bool = Query(True),
):
    """
    C3: List canonical trial-level visits (guide section 3.5).
    Returns visit_schedule rows scoped to the trial.
    """
    q = select(VisitSchedule).where(VisitSchedule.trial_id == trial_id)
    if active_only:
        q = q.where(VisitSchedule.is_active.is_(True))
    q = q.order_by(VisitSchedule.visit_order, VisitSchedule.id)
    r = await db.execute(q)
    rows = r.scalars().all()
    return [
        {
            "id": str(v.id),
            "trial_id": str(v.trial_id) if v.trial_id else None,
            "visit_code": v.visit_code,
            "visit_name": v.visit_name,
            "visit_type": v.visit_type,
            "target_day": v.target_day,
            "window_before": v.window_before,
            "window_after": v.window_after,
            "visit_order": v.visit_order,
            "is_active": v.is_active,
            "country_code": v.country_code,
        }
        for v in rows
    ]


@router.post("/trials/{trial_id}/visits", status_code=status.HTTP_201_CREATED)
async def create_trial_visit(
    trial_id: UUID,
    body: VisitScheduleCreate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    C3: Create a canonical trial-level visit (guide section 3.5).
    Visits belong to the trial, not individual templates.
    """
    vs = VisitSchedule(
        trial_id=trial_id,
        visit_code=body.visit_code,
        visit_name=body.visit_name,
        visit_order=body.visit_order,
        visit_type=body.visit_type,
        target_day=body.target_day,
        is_active=True,
    )
    db.add(vs)
    await db.flush()
    await audit_service.write_audit(
        db,
        entity_type="visit_schedule",
        entity_id=vs.id,
        action="CREATE",
        user_id=user.get("user_id"),
        new_value={"visit_code": body.visit_code, "visit_name": body.visit_name, "trial_id": str(trial_id)},
    )
    await db.commit()
    return {"id": str(vs.id)}


@router.post("/templates/{template_id}/visits", status_code=status.HTTP_201_CREATED)
async def create_visit_schedule(
    template_id: UUID,
    body: VisitScheduleCreate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """Legacy per-template visit creation (kept for backward compat). Prefer /trials/{id}/visits."""
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    vs = VisitSchedule(
        trial_id=tmpl.trial_id,  # C3: always set trial_id
        budget_template_id=template_id,
        visit_code=body.visit_code,
        visit_name=body.visit_name,
        visit_order=body.visit_order,
        visit_type=body.visit_type,
        target_day=body.target_day,
        is_active=True,
    )
    db.add(vs)
    await db.flush()
    await audit_service.write_audit(
        db,
        entity_type="visit_schedule",
        entity_id=vs.id,
        action="CREATE",
        user_id=user.get("user_id"),
        new_value={"visit_name": body.visit_name},
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {"id": str(vs.id)}


@router.delete("/templates/{template_id}/visits/{visit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_visit(
    template_id: UUID,
    visit_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    r = await db.execute(
        select(VisitSchedule).where(
            VisitSchedule.id == visit_id,
            VisitSchedule.budget_template_id == template_id,
        )
    )
    v = r.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="Visit not found")
    await db.delete(v)
    await audit_service.write_audit(
        db,
        entity_type="visit_schedule",
        entity_id=visit_id,
        action="DELETE",
        user_id=user.get("user_id"),
        old_value={"visit_code": v.visit_code, "visit_name": v.visit_name},
    )
    await db.commit()
    budget_totals_cache.clear_all()
