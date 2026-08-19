"""REST API: budget template CRUD, cascade lookup, resolve, totals, status, reset, policy refactor."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.modules.site_budgeting.db_models import (
    BudgetLineItem,
    BudgetPolicyDocument,
    BudgetTemplate,
    CostElement,
)
from app.modules.site_budgeting.dependencies import require_site_budgeting
from app.modules.site_budgeting.repositories import budgeting_repository as repo
from app.modules.site_budgeting.services import (
    ai_budget_service,
    audit_service,
    budget_service,
    budget_totals_cache,
    cost_service,
)
from app.modules.site_budgeting.utils.request_cache import RequestMemo
from app.modules.site_budgeting.validators.schemas import (
    BudgetTemplateCreate,
    BudgetTemplateStatusUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Site Budgeting"])


def _memo() -> RequestMemo:
    return RequestMemo()


@router.get("/templates/effective")
async def get_effective_template_endpoint(
    trial_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
    country_code: Optional[str] = Query(None),
    site_id: Optional[UUID] = Query(None),
):
    """
    Return the effective template for (trial, country, site) in the cascade,
    creating COUNTRY/SITE children on demand when missing.
    """
    try:
        tmpl = await budget_service.get_effective_template(
            db,
            trial_id=trial_id,
            country_code=country_code,
            site_id=site_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    await db.commit()
    return {"id": str(tmpl.id)}


@router.get("/trials/{trial_id}/templates")
async def list_templates_for_trial(
    trial_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
    level: Optional[str] = Query(None),
    country_code: Optional[str] = Query(None),
    site_id: Optional[UUID] = Query(None),
):
    rows = await repo.list_templates_for_trial(
        db,
        trial_id,
        level=level,
        country_code=country_code,
        site_id=site_id,
    )
    return [
        {
            "id": str(t.id),
            "trial_id": str(t.trial_id),
            "site_id": str(t.site_id) if t.site_id else None,
            "parent_template_id": str(t.parent_template_id) if t.parent_template_id else None,
            "name": t.name,
            "status": t.status,
            "enrollment_planned": t.enrollment_planned,
            "target_currency_code": t.target_currency_code,
            "template_level": t.template_level,
            "country_code": t.country_code,
        }
        for t in rows
    ]


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    body: BudgetTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    # Cross-study guard: the caller must be entitled to the target trial's study
    # (owner or grant). `trial_id` is a FK to `studies.id`, which == the
    # local_resources._id used by the entitlement gate. require_site_budgeting is
    # only a global feature flag, so without this a non-entitled user could create
    # a budget in another study.
    from app.integrations.iam.membership import user_can_act_in_study
    if not await user_can_act_in_study((user or {}).get("user_id"), str(body.trial_id)):
        raise HTTPException(status_code=403, detail="You are not entitled to this study.")

    # Infer template_level when not supplied: if site_id -> SITE, if parent exists -> COUNTRY, else TRIAL.
    lvl = (body.template_level or "").upper().strip() or None
    if lvl is None:
        if body.site_id:
            lvl = "SITE"
        elif body.parent_template_id:
            lvl = "COUNTRY"
        else:
            lvl = "TRIAL"

    # Idempotent: only one TRIAL template per trial (no site).
    # Return existing if present - avoids race conditions from concurrent creates
    # (e.g. React StrictMode double-mount) producing duplicate TRIAL templates.
    if lvl == "TRIAL" and not body.site_id:
        existing_trial = await budget_service._find_trial_template(db, body.trial_id)
        if existing_trial is not None:
            return {"id": str(existing_trial.id)}

    t = BudgetTemplate(
        trial_id=body.trial_id,
        site_id=body.site_id,
        parent_template_id=body.parent_template_id,
        name=body.name,
        enrollment_planned=body.enrollment_planned,
        target_currency_code=body.target_currency_code,
        template_level=lvl,
    )
    db.add(t)
    try:
        await db.flush()
    except IntegrityError:
        # Race window: another request created the TRIAL template between our check and flush.
        await db.rollback()
        if lvl == "TRIAL" and not body.site_id:
            existing_trial = await budget_service._find_trial_template(db, body.trial_id)
            if existing_trial is not None:
                return {"id": str(existing_trial.id)}
        raise
    await audit_service.write_audit(
        db,
        entity_type="budget_template",
        entity_id=t.id,
        action="CREATE",
        cascade_level=lvl,
        user_id=user.get("user_id"),
        new_value={"name": body.name, "trial_id": str(body.trial_id), "template_level": lvl},
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {"id": str(t.id)}


@router.patch("/templates/{template_id}", status_code=200)
async def patch_template(
    template_id: UUID,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    changed: dict[str, Any] = {}
    if "enrollment_planned" in body:
        val = body["enrollment_planned"]
        tmpl.enrollment_planned = int(val) if val not in (None, "", "null") else None
        changed["enrollment_planned"] = tmpl.enrollment_planned
    if "name" in body and str(body["name"]).strip():
        tmpl.name = str(body["name"]).strip()
        changed["name"] = tmpl.name
    if "target_currency_code" in body and str(body["target_currency_code"]).strip():
        tmpl.target_currency_code = str(body["target_currency_code"]).strip().upper()
        changed["target_currency_code"] = tmpl.target_currency_code
    if changed:
        await audit_service.write_audit(
            db, entity_type="budget_template", entity_id=template_id,
            action="UPDATE", user_id=user.get("user_id"), new_value=changed,
        )
        await db.commit()
        budget_totals_cache.clear_all()
    return {"id": str(template_id), **changed}


@router.get("/templates/{template_id}/resolve")
async def resolve_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
    country_code: Optional[str] = Query(None),
    site_id: Optional[UUID] = Query(None),
):
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    memo = _memo()
    resolved = await budget_service.resolve_budget_line_items(
        db, template_id, country_code=country_code, site_id=site_id, memo=memo
    )
    lines = []
    for row in resolved:
        r = {**row, "factored_unit_cost": row.get("unit_cost_computed"), "currency": tmpl.target_currency_code}
        lines.append(r)
    return {
        "template_id": str(template_id),
        "cost_version_label": tmpl.cost_version_label,
        "locked_pricing": cost_service.is_budget_locked(tmpl),
        "lines": lines,
    }


@router.get("/templates/{template_id}/total")
async def template_total(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
    country_code: Optional[str] = Query(None),
    site_id: Optional[UUID] = Query(None),
):
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    memo = _memo()
    return await budget_service.compute_budget_totals(
        db,
        template_id,
        trial_id=tmpl.trial_id,
        country_code=country_code,
        site_id=site_id,
        memo=memo,
    )


@router.patch("/templates/{template_id}/status")
async def update_template_status(
    template_id: UUID,
    body: BudgetTemplateStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """Advance the budget template through the state machine (draft -> under_review -> approved -> executed)."""
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    # Cross-study guard: caller must be entitled to the template's trial's study
    # (owner or grant). Regulated state-machine action; without this a non-entitled
    # user could advance another study's budget. `trial_id` == studies.id == resource id.
    from app.integrations.iam.membership import user_can_act_in_study
    if not await user_can_act_in_study((user or {}).get("user_id"), str(tmpl.trial_id)):
        raise HTTPException(status_code=403, detail="You are not entitled to this study.")

    valid_statuses = {"draft", "under_review", "approved", "executed", "amended", "archived"}
    new_status = body.status.lower().strip()
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}")

    old_status = tmpl.status
    tmpl.status = new_status

    # B5: Snapshot locked_exchange_rate_date on APPROVED -> EXECUTED transition (guide section 3.4, decision #6).
    # Locking at EXECUTED ensures exchange rates captured at contract execution, not just approval.
    if new_status == "executed" and old_status in ("approved",):
        from datetime import date as _date
        tmpl.locked_exchange_rate_date = _date.today()

    await db.flush()
    await audit_service.write_audit(
        db,
        entity_type="budget_template",
        entity_id=tmpl.id,
        action="STATUS_CHANGE",
        cascade_level=getattr(tmpl, "template_level", None),
        field_name="status",
        user_id=user.get("user_id"),
        old_value={"status": old_status},
        new_value={
            "status": new_status,
            "locked_exchange_rate_date": str(tmpl.locked_exchange_rate_date) if tmpl.locked_exchange_rate_date else None,
        },
    )
    await db.commit()
    budget_totals_cache.clear_all()

    # Kafka: publish BUDGET_APPROVED to the Data Platform when a SITE-level
    # budget template is approved. TRIAL/COUNTRY templates have no site_id, so
    # they are skipped. Best-effort & self-guarded — never breaks the commit.
    if new_status == "approved" and getattr(tmpl, "site_id", None):
        try:
            from app.integrations.milestones_kafka import publish_site_milestone, SiteMilestone

            await publish_site_milestone(
                SiteMilestone.BUDGET_APPROVED, site_id=str(tmpl.site_id)
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "update_template_status: BUDGET_APPROVED milestone hook failed for template %s",
                tmpl.id,
            )

    return {"id": str(tmpl.id), "status": tmpl.status, "locked_exchange_rate_date": str(tmpl.locked_exchange_rate_date) if tmpl.locked_exchange_rate_date else None}


@router.delete("/templates/{template_id}/reset-trial-budget", status_code=200)
async def reset_trial_budget(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    Wipe every budget artefact for the trial that owns this template, EXCEPT the
    TRIAL-level template itself (kept so the Study tab stays interactive without
    needing a re-create round-trip).

    Cleared:
      - All visits, matrix cells, line items, milestones, notes for any template of this trial
      - All COUNTRY + SITE templates for this trial
      - All policy documents for this trial
      - All trial_factor_configuration rows for this trial
    """
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    trial_id = tmpl.trial_id

    # asyncpg rejects multi-statement prepared queries - issue each DELETE separately,
    # ordered to satisfy FK dependencies.
    params = {"tid": trial_id}
    statements = [
        """DELETE FROM budget_visit_matrix
           WHERE budget_line_item_id IN (
               SELECT id FROM budget_line_item
               WHERE budget_template_id IN (
                   SELECT id FROM budget_template WHERE trial_id = :tid
               )
           )""",
        """DELETE FROM budget_line_item
           WHERE budget_template_id IN (
               SELECT id FROM budget_template WHERE trial_id = :tid
           )""",
        """DELETE FROM budget_milestone
           WHERE budget_template_id IN (
               SELECT id FROM budget_template WHERE trial_id = :tid
           )""",
        """DELETE FROM budget_note
           WHERE budget_template_id IN (
               SELECT id FROM budget_template WHERE trial_id = :tid
           )""",
        "DELETE FROM visit_schedule WHERE trial_id = :tid",
        "DELETE FROM trial_factor_configuration WHERE trial_id = :tid",
        "DELETE FROM budget_template WHERE trial_id = :tid AND template_level IN ('COUNTRY', 'SITE')",
    ]
    for sql in statements:
        await db.execute(text(sql), params)
    await db.execute(delete(BudgetPolicyDocument).where(BudgetPolicyDocument.trial_id == trial_id))
    await db.commit()
    budget_totals_cache.clear_all()
    return {"trial_id": str(trial_id), "cleared": True}


# --- Budget refactor: apply country-specific no-charge rules from policy docs ---

@router.post("/templates/{template_id}/budget/refactor")
async def refactor_budget_from_policy(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    Country-only. Reads every policy document uploaded for this country, asks the LLM
    which cost elements are NOT charged in this country, then applies the rules by
    inserting/updating COUNTRY-level BudgetLineItem rows with `is_excluded=True`. The
    parent (TRIAL) data is untouched - only this country's view changes.
    """
    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    level = (tmpl.template_level or "").upper()
    if level != "COUNTRY":
        raise HTTPException(status_code=400, detail="Refactor is only supported at COUNTRY level")
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

    # Resolve the parent (TRIAL) ancestor's line items so we know which elements exist.
    cursor = tmpl
    seen: set = set()
    trial_tpl = None
    while cursor and cursor.id not in seen:
        seen.add(cursor.id)
        if (cursor.template_level or "").upper() == "TRIAL":
            trial_tpl = cursor
            break
        if not cursor.parent_template_id:
            break
        cursor = await db.get(BudgetTemplate, cursor.parent_template_id)
    if trial_tpl is None:
        raise HTTPException(status_code=400, detail="Could not locate TRIAL template for this trial")

    parent_lines = (await db.execute(
        select(BudgetLineItem).where(BudgetLineItem.budget_template_id == trial_tpl.id)
    )).scalars().all()
    if not parent_lines:
        raise HTTPException(status_code=400, detail="TRIAL template has no line items to refactor")

    # Build name -> cost_element_id lookup of available elements
    ce_by_id: dict[UUID, Any] = {}
    name_to_ceid: dict[str, UUID] = {}
    for li in parent_lines:
        ce = await db.get(CostElement, li.cost_element_id)
        if ce is None:
            continue
        ce_by_id[ce.id] = ce
        name_to_ceid[ce.name] = ce.id

    available_names = list(name_to_ceid.keys())
    payload = [(d.document_data, d.file_name) for d in docs]
    try:
        rules = await ai_budget_service.extract_budget_rules_from_policy(
            payload, country_code=cc, available_element_names=available_names,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("[BUDGET_REFACTOR] LLM call failed")
        raise HTTPException(status_code=502, detail=f"Refactor failed: {e}")

    # Clear any prior policy-driven rows on this COUNTRY template (both excluded
    # and policy-included) so re-running gives a clean snapshot of THIS LLM run.
    await db.execute(
        delete(BudgetLineItem).where(
            BudgetLineItem.budget_template_id == template_id,
            (BudgetLineItem.is_excluded == True) | (BudgetLineItem.is_policy_included == True),  # noqa: E712
        )
    )
    await db.flush()

    # Apply rules.
    excluded: list[dict[str, Any]] = []
    included: list[dict[str, Any]] = []
    last_sort = (
        await db.execute(
            select(BudgetLineItem.sort_order)
            .where(BudgetLineItem.budget_template_id == template_id)
            .order_by(BudgetLineItem.sort_order.desc())
            .limit(1)
        )
    ).scalar_one_or_none() or 0
    next_sort = int(last_sort)

    # Refresh name->ce_id since auto-created elements during this loop may need to be reused.
    async def _resolve_ce(name: str) -> Optional[UUID]:
        nm = (name or "").strip()
        if not nm:
            return None
        # Reuse anything already in the catalog by case-insensitive name match
        ce = (await db.execute(
            select(CostElement).where(func.lower(CostElement.name) == nm.lower())
        )).scalar_one_or_none()
        if ce is not None:
            return ce.id
        # Auto-create a new cost element for the inclusion (cost defaults to $0).
        new_ce = CostElement(
            code=f"POLICY-{uuid.uuid4().hex[:8].upper()}",
            name=nm[:255],
            description=f"Policy-mandated for {cc}",
            unit_of_measure="Per Patient",
            element_type="ATOMIC",
            cost_type="PASS_THROUGH",
            is_active=True,
        )
        db.add(new_ce)
        await db.flush()
        return new_ce.id

    # milestone-destination include rules are skipped here - they belong in the
    # Milestones section (generate_milestones_from_policy), not the visit matrix.
    milestone_skipped: list[dict[str, Any]] = []
    for r in rules:
        action = r.get("action", "exclude")
        name = r["element_name"]
        if action == "include" and r.get("destination") == "milestone":
            milestone_skipped.append({"element_name": name, "reason": r.get("reason")})
            continue
        if action == "exclude":
            ce_id = name_to_ceid.get(name)
            if ce_id is None:
                continue
            existing = (
                await db.execute(
                    select(BudgetLineItem).where(
                        BudgetLineItem.budget_template_id == template_id,
                        BudgetLineItem.cost_element_id == ce_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.is_excluded = True
                existing.is_policy_included = False
            else:
                next_sort += 10
                db.add(BudgetLineItem(
                    budget_template_id=template_id,
                    cost_element_id=ce_id,
                    is_excluded=True,
                    is_policy_included=False,
                    sort_order=next_sort,
                ))
            excluded.append({"element_name": name, "reason": r.get("reason")})
        else:  # include
            ce_id = await _resolve_ce(name)
            if ce_id is None:
                continue
            existing = (
                await db.execute(
                    select(BudgetLineItem).where(
                        BudgetLineItem.budget_template_id == template_id,
                        BudgetLineItem.cost_element_id == ce_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.is_excluded = False
                existing.is_policy_included = True
            else:
                next_sort += 10
                db.add(BudgetLineItem(
                    budget_template_id=template_id,
                    cost_element_id=ce_id,
                    is_excluded=False,
                    is_policy_included=True,
                    sort_order=next_sort,
                ))
            included.append({"element_name": name, "reason": r.get("reason")})
        await db.flush()

    await audit_service.write_audit(
        db,
        entity_type="budget_template",
        entity_id=template_id,
        action="UPDATE",
        user_id=user.get("user_id"),
        new_value={
            "source": "policy_refactor",
            "country": cc,
            "doc_count": len(docs),
            "excluded": [e["element_name"] for e in excluded],
            "included": [e["element_name"] for e in included],
            "milestone_items": [e["element_name"] for e in milestone_skipped],
        },
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {
        "country_code": cc,
        "doc_count": len(docs),
        "rules_applied": len(excluded) + len(included),
        "excluded": excluded,
        "included": included,
        "milestone_items": milestone_skipped,
    }
