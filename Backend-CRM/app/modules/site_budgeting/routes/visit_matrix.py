"""REST API: visit matrix (generate/get/patch/resolved) + budget line items + amendment marks."""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from pymongo.errors import PyMongoError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.modules.site_budgeting.db_models import (
    BudgetLineItem,
    BudgetTemplate,
    BudgetVisitMatrix,
    VisitSchedule,
)
from app.modules.site_budgeting.dependencies import require_site_budgeting
from app.modules.site_budgeting.repositories import budgeting_repository as repo
from app.modules.site_budgeting.services import (
    audit_service,
    budget_service,
    budget_totals_cache,
)
from app.modules.site_budgeting.validators.schemas import (
    AmendmentMarkBody,
    BudgetLineItemCreate,
    BudgetLineItemUpdate,
    VisitMatrixPatch,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Site Budgeting"])


class VisitMatrixGenerateBody(BaseModel):
    study_id: str
    treatment_duration: Optional[int] = None
    followup_duration: Optional[int] = None
    unscheduled_visits: int = 0


@router.post("/templates/{template_id}/visit-matrix/generate")
async def generate_visit_matrix(
    template_id: UUID,
    body: VisitMatrixGenerateBody,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    Pull SOA from MongoDB, run the existing AI mapping pipeline, write visits + line items +
    matrix cells, then append N unscheduled visits. Replaces the two-step preview/apply flow
    from the UI's perspective.
    """
    try:
        result = await budget_service.generate_visit_matrix_from_soa(
            db,
            template_id=template_id,
            study_id=body.study_id.strip(),
            treatment_duration=body.treatment_duration,
            followup_duration=body.followup_duration,
            unscheduled_visits=int(body.unscheduled_visits or 0),
        )
    except ValueError as e:
        # Business errors (template/SoA not found, bad input) → 400 with the message.
        raise HTTPException(status_code=400, detail=str(e))
    except (RuntimeError, PyMongoError) as e:
        # SoA cluster unconfigured (RuntimeError) or unreachable (pymongo) — this
        # is infrastructure, not the caller's fault. Surface a clean 503 with an
        # actionable message instead of a bare 500, and log the real cause.
        logger.warning(
            "[SOA_MONGO] visit-matrix generate failed for template %s: %s",
            template_id, e,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "The Schedule of Activities (SoA) database is unavailable. "
                "Verify the SoA service is configured and reachable, then retry."
            ),
        )

    await audit_service.write_audit(
        db,
        entity_type="budget_visit_matrix",
        entity_id=template_id,
        action="CREATE",
        user_id=user.get("user_id"),
        new_value={
            "source": "soa_generate",
            "study_id": body.study_id,
            "treatment_duration": body.treatment_duration,
            "followup_duration": body.followup_duration,
            "unscheduled_visits": body.unscheduled_visits,
            "visits_inserted": result.get("visits_inserted", 0),
            "visit_counts": result.get("visit_counts", []),
        },
    )
    await db.commit()
    return result


@router.get("/templates/{template_id}/visit-matrix")
async def get_visit_matrix(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    visits = await db.execute(select(VisitSchedule).where(VisitSchedule.budget_template_id == template_id))
    visit_rows = visits.scalars().all()

    matrix = await repo.load_visit_matrix_for_template(db, template_id)
    return {
        "visits": [
            {
                "id": str(v.id),
                "visit_code": v.visit_code,
                "visit_name": v.visit_name,
                "visit_order": v.visit_order,
            }
            for v in visit_rows
        ],
        "cells": [
            {
                "id": str(m.id),
                "budget_line_item_id": str(m.budget_line_item_id),
                "visit_schedule_id": str(m.visit_schedule_id),
                "units": str(m.units),
                "is_excluded": getattr(m, "is_excluded", False),
            }
            for m in matrix
        ],
    }


@router.get("/templates/{template_id}/visit-matrix/resolved")
async def get_visit_matrix_resolved(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    visits = await db.execute(
        select(VisitSchedule)
        .where(VisitSchedule.budget_template_id == template_id)
        .order_by(VisitSchedule.visit_order, VisitSchedule.id)
    )
    visit_rows = visits.scalars().all()
    # Cascade: walk parent chain (SITE -> COUNTRY -> TRIAL) until we find a template with visits.
    if not visit_rows:
        cursor = tmpl
        seen: set = set()
        while cursor.parent_template_id and cursor.id not in seen:
            seen.add(cursor.id)
            cursor = await db.get(BudgetTemplate, cursor.parent_template_id)
            if cursor is None:
                break
            parent_visits = await db.execute(
                select(VisitSchedule)
                .where(VisitSchedule.budget_template_id == cursor.id)
                .order_by(VisitSchedule.visit_order, VisitSchedule.id)
            )
            visit_rows = parent_visits.scalars().all()
            if visit_rows:
                break
    cells = await budget_service.resolve_visit_matrix(db, template_id)
    return {
        "template_id": str(template_id),
        "visits": [
            {
                "id": str(v.id),
                "visit_code": v.visit_code,
                "visit_name": v.visit_name,
                "visit_order": v.visit_order,
            }
            for v in visit_rows
        ],
        "cells": cells,
    }


@router.post("/templates/{template_id}/amendment-mark-review")
async def mark_amendment_review(
    template_id: UUID,
    body: AmendmentMarkBody,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """After trial-level template changes, flag overridden child lines on affected elements."""
    n = await budget_service.propagate_trial_amendment_to_children(db, template_id, body.element_ids)
    await audit_service.write_audit(
        db,
        entity_type="budget_template",
        entity_id=template_id,
        action="UPDATE",
        user_id=user.get("user_id"),
        new_value={"amendment_mark_review": [str(x) for x in body.element_ids], "lines_flagged": n},
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {"marked": n}


@router.patch("/templates/{template_id}/visit-matrix")
async def patch_visit_matrix(
    template_id: UUID,
    body: VisitMatrixPatch,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    for c in body.cells:
        r = await db.execute(
            select(BudgetVisitMatrix).where(
                BudgetVisitMatrix.budget_line_item_id == c.budget_line_item_id,
                BudgetVisitMatrix.visit_schedule_id == c.visit_schedule_id,
            )
        )
        cell = r.scalar_one_or_none()
        old = str(cell.units) if cell else None
        if cell:
            cell.units = c.units
            if c.is_excluded is not None:
                cell.is_excluded = c.is_excluded
        else:
            cell = BudgetVisitMatrix(
                budget_line_item_id=c.budget_line_item_id,
                visit_schedule_id=c.visit_schedule_id,
                units=c.units,
                is_excluded=bool(c.is_excluded) if c.is_excluded is not None else False,
            )
            db.add(cell)
        await db.flush()
        await audit_service.write_audit(
            db,
            entity_type="budget_visit_matrix",
            entity_id=cell.id,
            action="UPDATE" if old is not None else "CREATE",
            user_id=user.get("user_id"),
            old_value={"units": old} if old else None,
            new_value={"units": str(c.units), "is_excluded": getattr(cell, "is_excluded", False)},
        )

    await db.commit()
    budget_totals_cache.clear_all()
    return {"status": "ok"}


@router.post("/templates/{template_id}/line-items", status_code=status.HTTP_201_CREATED)
async def create_line_item(
    template_id: UUID,
    body: BudgetLineItemCreate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    li = BudgetLineItem(
        budget_template_id=template_id,
        cost_element_id=body.cost_element_id,
        sort_order=body.sort_order,
    )
    db.add(li)
    await db.flush()
    await audit_service.write_audit(
        db,
        entity_type="budget_line_item",
        entity_id=li.id,
        action="CREATE",
        user_id=user.get("user_id"),
        new_value={"cost_element_id": str(body.cost_element_id)},
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {"id": str(li.id)}


@router.patch("/templates/{template_id}/line-items/{line_item_id}")
async def patch_line_item(
    template_id: UUID,
    line_item_id: UUID,
    body: BudgetLineItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    r = await db.execute(
        select(BudgetLineItem).where(
            BudgetLineItem.id == line_item_id,
            BudgetLineItem.budget_template_id == template_id,
        )
    )
    li = r.scalar_one_or_none()
    if not li:
        raise HTTPException(status_code=404, detail="Line item not found")

    old = {
        "is_excluded": li.is_excluded,
        "override_unit_cost": str(li.override_unit_cost) if li.override_unit_cost is not None else None,
        "override_currency_code": li.override_currency_code,
        "override_quantity": str(li.override_quantity) if li.override_quantity is not None else None,
        "needs_review": getattr(li, "needs_review", False),
        "sort_order": li.sort_order,
    }
    # Use model_fields_set to distinguish "field omitted" from "field explicitly set to null"
    set_fields = body.model_fields_set
    if "is_excluded" in set_fields and body.is_excluded is not None:
        li.is_excluded = body.is_excluded
    if "override_unit_cost" in set_fields:
        li.override_unit_cost = body.override_unit_cost  # allows clearing to null
    if "override_currency_code" in set_fields:
        li.override_currency_code = body.override_currency_code
    if "override_quantity" in set_fields:
        li.override_quantity = body.override_quantity
    if "needs_review" in set_fields and body.needs_review is not None:
        li.needs_review = body.needs_review
    if "sort_order" in set_fields and body.sort_order is not None:
        li.sort_order = body.sort_order

    await db.flush()
    await audit_service.write_audit(
        db,
        entity_type="budget_line_item",
        entity_id=li.id,
        action="UPDATE",
        user_id=user.get("user_id"),
        old_value=old,
        new_value={
            "is_excluded": li.is_excluded,
            "override_unit_cost": str(li.override_unit_cost) if li.override_unit_cost is not None else None,
            "override_currency_code": li.override_currency_code,
            "override_quantity": str(li.override_quantity) if li.override_quantity is not None else None,
            "needs_review": getattr(li, "needs_review", False),
            "sort_order": li.sort_order,
        },
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {"id": str(li.id)}
