"""REST API: budget milestones (per-template) + milestone library + AI-generated milestones."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.modules.site_budgeting.db_models import (
    BudgetMilestone,
    BudgetPolicyDocument,
    BudgetTemplate,
    MilestoneLibraryItem,
)
from app.modules.site_budgeting.dependencies import require_site_budgeting
from app.modules.site_budgeting.repositories import budgeting_repository as repo
from app.modules.site_budgeting.services import (
    ai_budget_service,
    audit_service,
    budget_totals_cache,
    factor_service,
)
from app.modules.site_budgeting.utils.request_cache import RequestMemo
from app.modules.site_budgeting.validators.schemas import (
    BudgetMilestoneCreate,
    BudgetMilestoneUpdate,
    MilestoneFromLibraryBody,
    MilestoneLibraryCreate,
    MilestoneLibraryUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Site Budgeting"])


# --- Per-template milestone CRUD --------------------------------------------

@router.post("/templates/{template_id}/milestones", status_code=status.HTTP_201_CREATED)
async def create_milestone(
    template_id: UUID,
    body: BudgetMilestoneCreate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    m = BudgetMilestone(
        budget_template_id=template_id,
        name=body.name,
        unit_cost=body.unit_cost,
        quantity=body.quantity,
        payment_trigger=body.payment_trigger,
        sort_order=body.sort_order,
    )
    db.add(m)
    await db.flush()
    await audit_service.write_audit(
        db,
        entity_type="budget_milestone",
        entity_id=m.id,
        action="CREATE",
        user_id=user.get("user_id"),
        new_value={"name": body.name, "unit_cost": str(body.unit_cost)},
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {"id": str(m.id)}


@router.get("/templates/{template_id}/milestones")
async def list_milestones(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    Milestones are stored split by scope:
      - Universal milestones live on the TRIAL template with country_code IS NULL
      - Country-specific milestones live on the COUNTRY template with country_code = ISO3

    Returned combined view:
      - TRIAL level   -> only universal (TRIAL rows)
      - COUNTRY level -> universals (from TRIAL ancestor) + country-specific (on this COUNTRY template)
      - SITE level    -> universals (from TRIAL ancestor) + country-specific (from COUNTRY ancestor)
    """
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    # Walk the parent chain once to discover ancestor template ids by level.
    trial_tid: Optional[UUID] = None
    country_tid: Optional[UUID] = None
    cursor = tmpl
    seen: set = set()
    while cursor and cursor.id not in seen:
        seen.add(cursor.id)
        lvl = (cursor.template_level or "").upper()
        if lvl == "TRIAL":
            trial_tid = cursor.id
        elif lvl == "COUNTRY":
            country_tid = cursor.id
        if not cursor.parent_template_id:
            break
        cursor = await db.get(BudgetTemplate, cursor.parent_template_id)

    combined: list[BudgetMilestone] = []
    level = (tmpl.template_level or "").upper()

    if trial_tid is not None:
        r = await db.execute(
            select(BudgetMilestone)
            .where(BudgetMilestone.budget_template_id == trial_tid, BudgetMilestone.country_code.is_(None))
            .order_by(BudgetMilestone.sort_order)
        )
        combined.extend(r.scalars().all())

    if level in ("COUNTRY", "SITE") and country_tid is not None:
        r = await db.execute(
            select(BudgetMilestone)
            .where(BudgetMilestone.budget_template_id == country_tid, BudgetMilestone.country_code.isnot(None))
            .order_by(BudgetMilestone.sort_order)
        )
        combined.extend(r.scalars().all())

    rows = combined

    # Apply country/site factor cascade to milestone unit_cost.
    # TRIAL level -> no factor. COUNTRY -> country factor. SITE -> country x site factors.
    country_code = tmpl.country_code if tmpl.template_level in ("COUNTRY", "SITE") else None
    site_id = tmpl.site_id if tmpl.template_level == "SITE" else None
    target_currency = tmpl.target_currency_code or "USD"
    memo = RequestMemo()

    async def _factored(m: BudgetMilestone) -> Decimal:
        if country_code is None and site_id is None:
            return m.unit_cost
        try:
            result = await factor_service.compute_final_unit_cost(
                db,
                element_id=m.element_id or m.id,
                trial_id=tmpl.trial_id,
                country_code=country_code,
                site_id=site_id,
                target_currency=target_currency,
                base_amount=m.unit_cost,
                base_currency=target_currency,
                memo=memo,
            )
            return Decimal(result.converted_amount)
        except Exception:
            return m.unit_cost

    out: list[dict[str, Any]] = []
    for m in rows:
        factored = await _factored(m)
        out.append(
            {
                "id": str(m.id),
                "name": m.name,
                "unit_cost": format(factored.quantize(Decimal("0.01")), "f"),
                "base_unit_cost": format(m.unit_cost.quantize(Decimal("0.01")), "f"),
                "quantity": format(getattr(m, "quantity", Decimal("1")) or Decimal("1"), "f"),
                "payment_trigger": getattr(m, "payment_trigger", None),
                "sort_order": m.sort_order,
                "country_code": getattr(m, "country_code", None),
                "scope": "country" if getattr(m, "country_code", None) else "universal",
            }
        )
    return out


@router.patch("/templates/{template_id}/milestones/{milestone_id}")
async def patch_milestone(
    template_id: UUID,
    milestone_id: UUID,
    body: BudgetMilestoneUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    r = await db.execute(
        select(BudgetMilestone).where(
            BudgetMilestone.id == milestone_id,
            BudgetMilestone.budget_template_id == template_id,
        )
    )
    m = r.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Milestone not found")

    old = {"name": m.name, "unit_cost": str(m.unit_cost), "payment_trigger": getattr(m, "payment_trigger", None)}
    set_fields = body.model_fields_set
    if "name" in set_fields and body.name is not None:
        m.name = body.name
    if "unit_cost" in set_fields and body.unit_cost is not None:
        m.unit_cost = body.unit_cost
    if "quantity" in set_fields and body.quantity is not None:
        m.quantity = body.quantity
    if "sort_order" in set_fields and body.sort_order is not None:
        m.sort_order = body.sort_order
    if "payment_trigger" in set_fields:
        m.payment_trigger = body.payment_trigger  # allows clearing to null

    await db.flush()
    await audit_service.write_audit(
        db,
        entity_type="budget_milestone",
        entity_id=m.id,
        action="UPDATE",
        user_id=user.get("user_id"),
        old_value=old,
        new_value={"name": m.name, "unit_cost": str(m.unit_cost)},
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {"id": str(m.id)}


@router.delete("/templates/{template_id}/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_milestone(
    template_id: UUID,
    milestone_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    r = await db.execute(
        select(BudgetMilestone).where(
            BudgetMilestone.id == milestone_id,
            BudgetMilestone.budget_template_id == template_id,
        )
    )
    m = r.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Milestone not found")
    await db.delete(m)
    await audit_service.write_audit(
        db,
        entity_type="budget_milestone",
        entity_id=milestone_id,
        action="DELETE",
        user_id=user.get("user_id"),
        old_value={"name": m.name, "unit_cost": str(m.unit_cost)},
    )
    await db.commit()
    budget_totals_cache.clear_all()


# --- AI-generated milestones ------------------------------------------------

@router.post("/templates/{template_id}/milestones/generate")
async def generate_milestones(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    Generate milestones based on the template's level:
      - TRIAL    -> ask LLM to pick universal milestones from the cost-element catalog
      - COUNTRY  -> fetch all stored policy docs for this country, ask LLM to extract
                    country-specific milestones, persist on COUNTRY template
      - SITE     -> not supported (milestones inherit from country)

    Re-running wipes the previous AI-generated rows for that scope and re-inserts.
    """
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    level = (tmpl.template_level or "").upper()
    if level == "SITE":
        raise HTTPException(status_code=400, detail="Milestones inherit from country at site level")

    async def _next_sort(tid: UUID) -> int:
        last = (
            await db.execute(
                select(BudgetMilestone.sort_order)
                .where(BudgetMilestone.budget_template_id == tid)
                .order_by(BudgetMilestone.sort_order.desc())
                .limit(1)
            )
        ).scalar_one_or_none() or 0
        return int(last) + 10

    if level == "TRIAL":
        # Whole catalog -> LLM -> universal milestones
        elements = await repo.list_cost_elements(db)
        catalog: list[dict[str, Any]] = []
        for el in elements:
            latest = await repo.get_latest_cost_version(db, el.id)
            catalog.append({
                "code": el.code,
                "name": el.name,
                "category": el.category.name if el.category else None,
                "cost_type": el.cost_type,
                "base_unit_cost": str(latest.base_unit_cost) if latest else "0",
            })

        try:
            extracted = await ai_budget_service.generate_milestones_from_catalog(catalog)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception("[MILESTONES] catalog generation failed")
            raise HTTPException(status_code=502, detail=f"Milestone generation failed: {e}")

        # Wipe old universals on this TRIAL template, then insert fresh
        await db.execute(
            delete(BudgetMilestone).where(
                BudgetMilestone.budget_template_id == tmpl.id,
                BudgetMilestone.country_code.is_(None),
            )
        )
        await db.flush()

        sort = (await _next_sort(tmpl.id))
        for item in extracted:
            db.add(BudgetMilestone(
                budget_template_id=tmpl.id,
                name=item["name"],
                unit_cost=Decimal(str(item.get("unit_cost") or 0)),
                quantity=Decimal("1"),
                payment_trigger=item.get("payment_trigger"),
                sort_order=sort,
                country_code=None,
            ))
            sort += 10

        await db.flush()
        await audit_service.write_audit(
            db,
            entity_type="budget_milestone",
            entity_id=tmpl.id,
            action="CREATE",
            user_id=user.get("user_id"),
            new_value={"source": "cost_catalog", "universal": len(extracted)},
        )
        await db.commit()
        budget_totals_cache.clear_all()
        return {"universal": len(extracted), "by_country": {}, "total": len(extracted)}

    # COUNTRY level
    cc = (tmpl.country_code or "").strip().upper()
    if not cc:
        raise HTTPException(status_code=400, detail="Country template missing country_code")

    docs = (await db.execute(
        select(BudgetPolicyDocument)
        .where(
            BudgetPolicyDocument.trial_id == tmpl.trial_id,
            BudgetPolicyDocument.country_code == cc,
        )
        .order_by(BudgetPolicyDocument.uploaded_at)
    )).scalars().all()
    if not docs:
        raise HTTPException(
            status_code=400,
            detail=f"No policy documents uploaded for country {cc}. Upload one in the Policy Docs tab first.",
        )

    payload = [(d.document_data, d.file_name) for d in docs]
    try:
        extracted = await ai_budget_service.generate_milestones_from_policy(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("[MILESTONES] country-doc generation failed")
        raise HTTPException(status_code=502, detail=f"Milestone generation failed: {e}")

    # Wipe old country-specific rows for this country on this COUNTRY template
    await db.execute(
        delete(BudgetMilestone).where(
            BudgetMilestone.budget_template_id == tmpl.id,
            BudgetMilestone.country_code == cc,
        )
    )
    await db.flush()

    sort = (await _next_sort(tmpl.id))
    for item in extracted:
        db.add(BudgetMilestone(
            budget_template_id=tmpl.id,
            name=item["name"],
            unit_cost=Decimal(str(item.get("unit_cost") or 0)),
            quantity=Decimal("1"),
            payment_trigger=item.get("payment_trigger"),
            sort_order=sort,
            country_code=cc,
        ))
        sort += 10

    await db.flush()
    await audit_service.write_audit(
        db,
        entity_type="budget_milestone",
        entity_id=tmpl.id,
        action="CREATE",
        user_id=user.get("user_id"),
        new_value={"source": "policy_documents", "country": cc, "doc_count": len(docs), "milestones": len(extracted)},
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {"universal": 0, "by_country": {cc: len(extracted)}, "total": len(extracted)}


# --- Milestone library -------------------------------------------------------

def _lib_item_out(item: MilestoneLibraryItem) -> dict:
    return {
        "id": str(item.id),
        "name": item.name,
        "default_amount": str(item.default_amount) if item.default_amount is not None else None,
        "payment_trigger": item.payment_trigger,
        "category": item.category,
        "sort_order": item.sort_order,
        "is_active": item.is_active,
    }


@router.get("/milestone-library")
async def list_milestone_library(
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    """List active milestone library items, optionally filtered by category."""
    q = select(MilestoneLibraryItem).where(MilestoneLibraryItem.is_active == True)
    if category:
        q = q.where(MilestoneLibraryItem.category == category)
    q = q.order_by(MilestoneLibraryItem.sort_order, MilestoneLibraryItem.name)
    result = await db.execute(q)
    return [_lib_item_out(i) for i in result.scalars().all()]


@router.post("/milestone-library", status_code=status.HTTP_201_CREATED)
async def create_milestone_library_item(
    body: MilestoneLibraryCreate,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    """Create a new milestone library item (admin use)."""
    item = MilestoneLibraryItem(
        name=body.name,
        default_amount=body.default_amount,
        payment_trigger=body.payment_trigger,
        category=body.category,
        sort_order=body.sort_order,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _lib_item_out(item)


@router.patch("/milestone-library/{item_id}")
async def update_milestone_library_item(
    item_id: UUID,
    body: MilestoneLibraryUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    result = await db.execute(select(MilestoneLibraryItem).where(MilestoneLibraryItem.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Library item not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return _lib_item_out(item)


@router.delete("/milestone-library/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_milestone_library_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    result = await db.execute(select(MilestoneLibraryItem).where(MilestoneLibraryItem.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Library item not found")
    item.is_active = False
    await db.commit()


@router.post("/templates/{template_id}/milestones/from-library", status_code=status.HTTP_201_CREATED)
async def add_milestone_from_library(
    template_id: UUID,
    body: MilestoneFromLibraryBody,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    Add a milestone to a template by picking from the library.
    Uses amount_override if provided, otherwise uses library item's default_amount.
    Raises 400 if no amount is available.
    """
    tmpl = await db.get(BudgetTemplate, template_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")

    lib_result = await db.execute(
        select(MilestoneLibraryItem).where(MilestoneLibraryItem.id == body.library_item_id)
    )
    lib_item = lib_result.scalar_one_or_none()
    if lib_item is None:
        raise HTTPException(status_code=404, detail="Library item not found")

    amount = body.amount_override if body.amount_override is not None else lib_item.default_amount
    if amount is None:
        raise HTTPException(
            status_code=400,
            detail="This milestone has no default amount - provide amount_override"
        )

    existing = await db.execute(
        select(BudgetMilestone.sort_order)
        .where(BudgetMilestone.budget_template_id == template_id)
        .order_by(BudgetMilestone.sort_order.desc())
        .limit(1)
    )
    last_order = existing.scalar_one_or_none() or 0

    milestone = BudgetMilestone(
        budget_template_id=template_id,
        element_id=lib_item.id if hasattr(lib_item, "id") else None,
        name=lib_item.name,
        unit_cost=amount,
        quantity=body.quantity or Decimal("1"),
        payment_trigger=lib_item.payment_trigger,
        sort_order=last_order + 10,
    )
    db.add(milestone)
    budget_totals_cache.clear_all()
    await db.commit()
    await db.refresh(milestone)
    return {
        "id": str(milestone.id),
        "name": milestone.name,
        "unit_cost": str(milestone.unit_cost),
        "quantity": str(milestone.quantity),
        "payment_trigger": milestone.payment_trigger,
        "sort_order": milestone.sort_order,
    }


# --- Bulk auto-populate milestones from library -----------------------------

class BulkMilestoneBody(BaseModel):
    library_item_ids: list[UUID]          # items to add; empty = add ALL active items
    amount_overrides: dict[str, str] = {}  # item_id (str) -> amount string


@router.post("/templates/{template_id}/milestones/bulk-from-library", status_code=status.HTTP_200_OK)
async def bulk_milestones_from_library(
    template_id: UUID,
    body: BulkMilestoneBody,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    Add multiple library milestones to a template in one call.
    - If library_item_ids is empty -> adds ALL active library items.
    - Skips items with no amount (no default and no override provided).
    - Skips items already present in the template (dedup by name).
    """
    tmpl = await db.get(BudgetTemplate, template_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")

    if body.library_item_ids:
        lib_q = await db.execute(
            select(MilestoneLibraryItem).where(
                MilestoneLibraryItem.id.in_(body.library_item_ids),
                MilestoneLibraryItem.is_active == True,
            ).order_by(MilestoneLibraryItem.sort_order)
        )
    else:
        lib_q = await db.execute(
            select(MilestoneLibraryItem)
            .where(MilestoneLibraryItem.is_active == True)
            .order_by(MilestoneLibraryItem.sort_order)
        )
    lib_items = lib_q.scalars().all()

    existing_q = await db.execute(
        select(BudgetMilestone.name).where(BudgetMilestone.budget_template_id == template_id)
    )
    existing_names = {n.lower() for n in existing_q.scalars().all()}

    order_q = await db.execute(
        select(BudgetMilestone.sort_order)
        .where(BudgetMilestone.budget_template_id == template_id)
        .order_by(BudgetMilestone.sort_order.desc()).limit(1)
    )
    last_order = order_q.scalar_one_or_none() or 0

    added = 0
    skipped_no_amount = 0
    skipped_duplicate = 0

    for item in lib_items:
        if item.name.lower() in existing_names:
            skipped_duplicate += 1
            continue

        override_str = body.amount_overrides.get(str(item.id))
        amount = Decimal(override_str) if override_str else item.default_amount
        if amount is None:
            skipped_no_amount += 1
            continue

        last_order += 10
        db.add(BudgetMilestone(
            budget_template_id=template_id,
            name=item.name,
            unit_cost=amount,
            quantity=Decimal("1"),
            payment_trigger=item.payment_trigger,
            sort_order=last_order,
        ))
        existing_names.add(item.name.lower())
        added += 1

    await db.commit()
    budget_totals_cache.clear_all()

    return {"added": added, "skipped_duplicate": skipped_duplicate, "skipped_no_amount": skipped_no_amount}
