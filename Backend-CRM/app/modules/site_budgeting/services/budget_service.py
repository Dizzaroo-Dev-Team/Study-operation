"""Cascade resolution, visit matrix merge, totals, protocol amendment flags."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Any, Optional
from uuid import UUID

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.site_budgeting.db_models import (
    BudgetLineItem,
    BudgetPersonnelRole,
    BudgetTemplate,
    BudgetVisitMatrix,
    ConversionFactorType,
    CostElement,
    ElementCategory,
    ElementCostVersion,
    TrialFactorConfiguration,
    VisitSchedule,
)
from app.modules.site_budgeting.repositories import budgeting_repository as repo
from app.modules.site_budgeting.services import ai_budget_service, budget_totals_cache, cost_service, factor_service, mongo_service
from app.modules.site_budgeting.utils.request_cache import RequestMemo, cache_key


async def _line_rows_for_template(db: AsyncSession, template_id: UUID) -> list[BudgetLineItem]:
    r = await db.execute(
        select(BudgetLineItem)
        .options(selectinload(BudgetLineItem.cost_element))
        .where(BudgetLineItem.budget_template_id == template_id)
        .order_by(BudgetLineItem.sort_order, BudgetLineItem.id)
    )
    return list(r.scalars().all())


async def _visits_for_template(db: AsyncSession, template_id: UUID) -> list[VisitSchedule]:
    r = await db.execute(
        select(VisitSchedule)
        .where(VisitSchedule.budget_template_id == template_id)
        .order_by(VisitSchedule.visit_order, VisitSchedule.id)
    )
    return list(r.scalars().all())


async def _ensure_factor_type_registered(db: AsyncSession, trial_id: UUID, factor_type_code: str, sequence: int) -> None:
    """Auto-register a factor type for a trial if not already in TrialFactorConfiguration."""
    ft = (await db.execute(select(ConversionFactorType).where(ConversionFactorType.code == factor_type_code))).scalar_one_or_none()
    if ft is None:
        return
    existing = (
        await db.execute(select(TrialFactorConfiguration.id).where(TrialFactorConfiguration.trial_id == trial_id, TrialFactorConfiguration.factor_type_id == ft.id))
    ).scalar_one_or_none()
    if existing is None:
        db.add(TrialFactorConfiguration(trial_id=trial_id, factor_type_id=ft.id, application_sequence=sequence, is_active=True))
        await db.flush()


async def _find_trial_template(db: AsyncSession, trial_id: UUID) -> BudgetTemplate | None:
    """
    Pick the primary trial-level template — oldest (first created) wins so that
    the original populated template is always preferred over later duplicates.
    """
    r = await db.execute(
        select(BudgetTemplate)
        .where(
            BudgetTemplate.trial_id == trial_id,
            or_(BudgetTemplate.template_level == "TRIAL", BudgetTemplate.template_level.is_(None)),
            BudgetTemplate.site_id.is_(None),
        )
        .order_by(BudgetTemplate.created_at.asc(), BudgetTemplate.id.asc())
        .limit(1)
    )
    return r.scalar_one_or_none()


async def get_or_create_country_template(
    db: AsyncSession,
    *,
    trial_id: UUID,
    country_code: str,
) -> BudgetTemplate:
    """
    Return existing COUNTRY-level template for (trial, country) or create a child of the trial template.
    Does not commit; caller is responsible for committing.
    """
    code = country_code.upper()

    # Existing COUNTRY template
    r = await db.execute(
        select(BudgetTemplate)
        .where(
            BudgetTemplate.trial_id == trial_id,
            BudgetTemplate.template_level == "COUNTRY",
            BudgetTemplate.country_code == code,
        )
        .order_by(BudgetTemplate.created_at.desc(), BudgetTemplate.id.desc())
        .limit(1)
    )
    existing = r.scalar_one_or_none()
    if existing is not None:
        # Validate parent is a TRIAL-level template when present.
        if existing.parent_template_id is not None:
            parent = await db.get(BudgetTemplate, existing.parent_template_id)
            if parent is None or parent.trial_id != trial_id or parent.template_level not in (None, "TRIAL"):
                raise ValueError("Invalid cascade: COUNTRY template parent must be TRIAL level for same trial")
        return existing

    trial_tpl = await _find_trial_template(db, trial_id)
    if trial_tpl is None:
        raise ValueError("No trial-level template found for cascade")

    country_tpl = BudgetTemplate(
        trial_id=trial_id,
        name=f"{trial_tpl.name} — {code}",
        status=trial_tpl.status,
        enrollment_planned=trial_tpl.enrollment_planned,
        target_currency_code=trial_tpl.target_currency_code,
        template_level="COUNTRY",
        country_code=code,
        parent_template_id=trial_tpl.id,
    )
    db.add(country_tpl)
    await db.flush()
    await _ensure_factor_type_registered(db, trial_id, "COUNTRY", sequence=10)
    return country_tpl


async def get_or_create_site_template(
    db: AsyncSession,
    *,
    trial_id: UUID,
    country_code: str,
    site_id: UUID,
) -> BudgetTemplate:
    """
    Return existing SITE-level template for (trial, site, country) or create a fresh
    child of the matching COUNTRY template. Keying by all three ensures that switching
    countries in the UI gives a different cascade chain — milestones, visits, and
    refactor exclusions all route through the currently-selected country, not whatever
    country the site template was originally created under.
    Does not commit; caller is responsible for committing.
    """
    cc = (country_code or "").strip().upper()
    if not cc:
        raise ValueError("country_code is required for site template")

    r = await db.execute(
        select(BudgetTemplate)
        .where(
            BudgetTemplate.trial_id == trial_id,
            BudgetTemplate.template_level == "SITE",
            BudgetTemplate.site_id == site_id,
            BudgetTemplate.country_code == cc,
        )
        .order_by(BudgetTemplate.created_at.desc(), BudgetTemplate.id.desc())
        .limit(1)
    )
    existing = r.scalar_one_or_none()
    if existing is not None:
        return existing

    # Ensure we have a COUNTRY template first.
    country_tpl = await get_or_create_country_template(db, trial_id=trial_id, country_code=country_code)

    site_tpl = BudgetTemplate(
        trial_id=trial_id,
        name=f"{country_tpl.name} — site",
        status=country_tpl.status,
        enrollment_planned=country_tpl.enrollment_planned,
        target_currency_code=country_tpl.target_currency_code,
        template_level="SITE",
        country_code=country_tpl.country_code,
        site_id=site_id,
        parent_template_id=country_tpl.id,
    )
    db.add(site_tpl)
    await db.flush()
    await _ensure_factor_type_registered(db, trial_id, "SITE", sequence=20)
    return site_tpl


async def get_effective_template(
    db: AsyncSession,
    *,
    trial_id: UUID,
    country_code: Optional[str] = None,
    site_id: Optional[UUID] = None,
) -> BudgetTemplate:
    """
    High-level helper for cascade selection:
    - SITE: get_or_create_site_template(trial, country, site)
    - COUNTRY: get_or_create_country_template(trial, country)
    - TRIAL: best-effort trial template.
    """
    if site_id is not None:
        # Prefer site-level template; require country to disambiguate per-country SITE templates.
        if not country_code:
            raise ValueError("country_code is required to resolve a SITE-level template")
        cc = country_code.strip().upper()
        r = await db.execute(
            select(BudgetTemplate)
            .where(
                BudgetTemplate.trial_id == trial_id,
                BudgetTemplate.template_level == "SITE",
                BudgetTemplate.site_id == site_id,
                BudgetTemplate.country_code == cc,
            )
            .order_by(BudgetTemplate.created_at.desc(), BudgetTemplate.id.desc())
            .limit(1)
        )
        site_tpl = r.scalar_one_or_none()
        if site_tpl is not None:
            return site_tpl
        return await get_or_create_site_template(db, trial_id=trial_id, country_code=cc, site_id=site_id)

    if country_code:
        return await get_or_create_country_template(db, trial_id=trial_id, country_code=country_code)

    trial_tpl = await _find_trial_template(db, trial_id)
    if trial_tpl is None:
        raise ValueError("No trial-level template found")
    return trial_tpl


def _factor_scope_label_from_rank(rank: int) -> str:
    return {
        8: "Element + site",
        7: "Element + country",
        6: "Category + site",
        5: "Category + country",
        4: "Element (global)",
        3: "Global + site",
        2: "Global + country",
        1: "Global",
    }.get(rank, "Factor")


async def sum_milestone_ancestor_chain(db: AsyncSession, template_id: UUID) -> Decimal:
    """Sum milestone amounts for this template and every ancestor (trial → country → site)."""
    total = Decimal(0)
    tid: Optional[UUID] = template_id
    seen: set[UUID] = set()
    while tid is not None and tid not in seen:
        seen.add(tid)
        total += await repo.sum_milestone_amounts(db, tid)
        t = await db.get(BudgetTemplate, tid)
        tid = t.parent_template_id if t else None
    return total



async def resolve_visit_matrix(
    db: AsyncSession,
    template_id: UUID,
    memo: Optional[RequestMemo] = None,
) -> list[dict[str, Any]]:
    """
    Merge parent template visit matrix with local rows (copy-on-write).
    Keys: (cost_element_id, visit_code). Local row with is_excluded removes mapping.
    """
    ck = cache_key("rvm", template_id)
    work_memo = memo if memo is not None else RequestMemo()
    if work_memo.has(ck):
        return work_memo.get(ck)  # type: ignore[return-value]

    tmpl = await db.get(BudgetTemplate, template_id)
    if not tmpl:
        raise ValueError("Template not found")

    parent_map: dict[tuple[str, str], dict[str, Any]] = {}
    if tmpl.parent_template_id:
        parent_cells = await resolve_visit_matrix(db, tmpl.parent_template_id, memo=work_memo)
        for c in parent_cells:
            k = (c["cost_element_id"], c["visit_code"])
            parent_map[k] = c

    # Cascade: walk parent chain until we find a template that owns visits/lines.
    # SITE → COUNTRY → TRIAL: typically only TRIAL has them, so one-level cascade is not enough.
    visits = await _visits_for_template(db, template_id)
    if not visits:
        cursor = tmpl
        seen: set = set()
        while cursor.parent_template_id and cursor.id not in seen:
            seen.add(cursor.id)
            cursor = await db.get(BudgetTemplate, cursor.parent_template_id)
            if cursor is None:
                break
            visits = await _visits_for_template(db, cursor.id)
            if visits:
                break

    # Union of local + parent lines, keyed by cost_element_id.
    # - Local lines override parent for same cost_element_id (so an `is_excluded` flag
    #   at COUNTRY hides the row even though TRIAL has it active).
    # - Parent-only lines still need to be emitted for cascaded display (this was the bug:
    #   adding any local line to COUNTRY made `_line_rows_for_template(country)` non-empty,
    #   which short-circuited the cascade and dropped every TRIAL-only row).
    local_lines = await _line_rows_for_template(db, template_id)
    local_by_ce: dict[str, Any] = {str(li.cost_element_id): li for li in local_lines}

    # Walk parent chain to gather parent lines (each ce_id wins by closest ancestor).
    parent_lines_by_ce: dict[str, Any] = {}
    cursor = tmpl
    seen: set = set()
    while cursor.parent_template_id and cursor.id not in seen:
        seen.add(cursor.id)
        cursor = await db.get(BudgetTemplate, cursor.parent_template_id)
        if cursor is None:
            break
        for li in await _line_rows_for_template(db, cursor.id):
            ce_key = str(li.cost_element_id)
            if ce_key not in parent_lines_by_ce:
                parent_lines_by_ce[ce_key] = li

    # Build unified iteration list: union of ce_ids; pick local line if present, else parent.
    unified: list[tuple[str, Any]] = []  # [(ce_id, line_item)]
    for ce_id, li in local_by_ce.items():
        unified.append((ce_id, li))
    for ce_id, li in parent_lines_by_ce.items():
        if ce_id not in local_by_ce:
            unified.append((ce_id, li))

    enriched = await repo.load_visit_matrix_enriched(db, template_id)
    m_by_pair: dict[tuple[str, str], Any] = {}
    for m, li, vs in enriched:
        if str(li.budget_template_id) != str(template_id):
            continue
        code = (vs.visit_code or str(vs.id)).strip()
        m_by_pair[(str(li.cost_element_id), code)] = m

    out: list[dict[str, Any]] = []
    for ceid, li in unified:
        # If local line item is excluded → skip ALL its cells. Whole row goes silent.
        local_li = local_by_ce.get(ceid)
        if local_li is not None and getattr(local_li, "is_excluded", False):
            continue

        for v in visits:
            code = (v.visit_code or str(v.id)).strip()
            k = (ceid, code)
            local = m_by_pair.get(k)
            parent = parent_map.get(k)

            if local is not None:
                if local.is_excluded:
                    continue
                units = local.units
                inherited = False
            elif parent is not None:
                if parent.get("is_excluded"):
                    continue
                units = Decimal(parent["units"])
                inherited = True
            else:
                continue

            out.append(
                {
                    "cost_element_id": ceid,
                    "visit_code": code,
                    "visit_schedule_id": str(v.id),
                    "budget_line_item_id": str(li.id),
                    "units": str(units),
                    "inherited_from_parent": inherited,
                    "is_excluded": False,
                }
            )
    work_memo.set(ck, out)
    return out


def _inherit_label(parent_tid: Optional[UUID], tmpl: BudgetTemplate) -> Optional[str]:
    """Return a label describing from which cascade level the item was inherited."""
    if not parent_tid:
        return None
    lvl = getattr(tmpl, "template_level", None)
    if lvl == "SITE":
        return "country"
    if lvl == "COUNTRY":
        return "trial"
    # Legacy / TRIAL-level with a parent: label by parent UUID for UI resolution.
    if tmpl.parent_template_id:
        return f"parent:{tmpl.parent_template_id}"
    return "trial"


async def resolve_budget_line_items(
    db: AsyncSession,
    template_id: UUID,
    *,
    country_code: Optional[str] = None,
    site_id: Optional[UUID] = None,
    visit_matrix_precomputed: Optional[list[dict[str, Any]]] = None,
    memo: Optional[RequestMemo] = None,
) -> list[dict[str, Any]]:
    """
    Full copy-on-write: recursive parent resolve, merge local deltas (excluded, overrides, quantity).
    """
    work_memo = memo if memo is not None else RequestMemo()

    tmpl = await db.get(BudgetTemplate, template_id)
    if not tmpl:
        raise ValueError("Template not found")

    # Derive factor context from template level when explicit context is not provided.
    eff_country = country_code
    eff_site = site_id
    lvl = getattr(tmpl, "template_level", None)
    if eff_country is None and lvl in ("COUNTRY", "SITE"):
        eff_country = getattr(tmpl, "country_code", None)
    if eff_site is None and lvl == "SITE" and getattr(tmpl, "site_id", None) is not None:
        eff_site = tmpl.site_id

    parent_rows: dict[str, dict[str, Any]] = {}
    if tmpl.parent_template_id:
        pres = await resolve_budget_line_items(
            db,
            tmpl.parent_template_id,
            country_code=eff_country,
            site_id=eff_site,
            memo=work_memo,
        )
        parent_rows = {r["cost_element_id"]: r for r in pres}

    local_lines = await _line_rows_for_template(db, template_id)
    local_by_ce = {str(li.cost_element_id): li for li in local_lines}

    vm = visit_matrix_precomputed if visit_matrix_precomputed is not None else await resolve_visit_matrix(db, template_id, memo=work_memo)
    qty_by_ce: dict[str, Decimal] = {}
    for cell in vm:
        ce = cell["cost_element_id"]
        qty_by_ce[ce] = qty_by_ce.get(ce, Decimal(0)) + Decimal(str(cell["units"]))

    merged: dict[str, dict[str, Any]] = {}

    for ce_id, li in local_by_ce.items():
        par = parent_rows.get(ce_id)
        # B3: use is_excluded (single flag). Excluded local rows are emitted with
        # is_excluded=True so the UI can render them strikethrough / red, instead
        # of silently dropping them.
        if li.is_excluded:
            pq = Decimal(str(par["quantity"])) if par and par.get("quantity") is not None else None
            merged[ce_id] = {
                "line_item_id": str(li.id),
                "cost_element_id": ce_id,
                "code": li.cost_element.code if li.cost_element else None,
                "name": li.cost_element.name if li.cost_element else None,
                "is_excluded": True,
                "is_policy_included": False,
                "override_unit_cost": None,
                "override_currency_code": None,
                "override_quantity": None,
                "quantity": str(pq) if pq is not None else "0",
                "inherited_from": _inherit_label(tmpl.parent_template_id, tmpl) or "parent",
                "needs_review": False,
                "parent_quantity": str(pq) if pq is not None else None,
            }
            continue


        pq = Decimal(str(par["quantity"])) if par and par.get("quantity") is not None else None

        if li.override_quantity is not None:
            # Explicit override always wins.
            pqty: Decimal = li.override_quantity
        else:
            # B2: PER_PATIENT elements have effective_quantity = 1 per patient (guide §4).
            # PER_VISIT elements use visit-matrix count. All others (FIXED, MILESTONE) use
            # stored/parent quantity.
            cost_type = (li.cost_element.cost_type if li.cost_element else None) or ""
            if cost_type == "PER_PATIENT":
                pqty = Decimal(1)
            else:
                # Prefer the resolved visit-matrix count (merges parent + local cells).
                vm_count = qty_by_ce.get(ce_id)
                if vm_count is not None and vm_count > Decimal(0):
                    pqty = vm_count
                elif pq is not None:
                    pqty = pq
                else:
                    pqty = Decimal(0)

        overridden = (
            li.override_unit_cost is not None
            or li.override_quantity is not None
            or (par is not None and not li.inherited_from_parent)
        )
        inherited_from = None if overridden or par is None else _inherit_label(tmpl.parent_template_id, tmpl)

        merged[ce_id] = {
            "line_item_id": str(li.id),
            "cost_element_id": ce_id,
            "code": li.cost_element.code if li.cost_element else None,
            "name": li.cost_element.name if li.cost_element else None,
            "is_excluded": li.is_excluded,
            "override_unit_cost": str(li.override_unit_cost) if li.override_unit_cost is not None else None,
            "override_currency_code": li.override_currency_code,
            "override_quantity": str(li.override_quantity) if li.override_quantity is not None else None,
            "quantity": str(pqty),
            "inherited_from": inherited_from,
            "needs_review": bool(getattr(li, "needs_review", False)),
            "parent_quantity": str(pq) if pq is not None else None,
        }

    for ce_id, par in parent_rows.items():
        if ce_id in merged:
            continue
        if ce_id in local_by_ce and local_by_ce[ce_id].is_excluded:
            continue
        if local_by_ce.get(ce_id) is not None:
            continue
        pq = Decimal(str(par["quantity"])) if par.get("quantity") else Decimal(0)
        merged[ce_id] = {
            # Carry parent's line_item_id for cascaded (inherited) rows so the visit matrix
            # can key cells by it. This is read-only at country/site — edits go through the
            # override path which creates a local line item.
            "line_item_id": par.get("line_item_id"),
            "cost_element_id": ce_id,
            "code": par.get("code"),
            "name": par.get("name"),
            "is_excluded": False,
            "override_unit_cost": None,
            "override_currency_code": None,
            "override_quantity": None,
            "quantity": str(pq),
            "inherited_from": _inherit_label(tmpl.parent_template_id, tmpl) or "parent",
            "needs_review": bool(par.get("needs_review", False)),
            "parent_quantity": str(pq),
        }

    ce_uuid_list = [UUID(k) for k in merged.keys()]
    versioned = await cost_service.bulk_get_versioned_costs(db, ce_uuid_list, tmpl.trial_id, template=tmpl)
    element_map = await repo.bulk_cost_elements(db, ce_uuid_list)
    cat_by_ce = {
        str(eid): (
            (element_map[eid].category.name if element_map[eid].category else None)
            if eid in element_map else None
        )
        for eid in ce_uuid_list
    }

    out: list[dict[str, Any]] = []
    for ce_id, row in merged.items():
        element_uuid = UUID(ce_id)
        vc = versioned.get(element_uuid)
        if not vc:
            unit_computed = None
        else:
            amt, cur = vc
            if row.get("override_unit_cost"):
                amt = Decimal(row["override_unit_cost"])
                cur = row.get("override_currency_code") or tmpl.target_currency_code
            fr = await factor_service.compute_final_unit_cost(
                db,
                element_id=element_uuid,
                trial_id=tmpl.trial_id,
                country_code=eff_country,
                site_id=eff_site,
                target_currency=tmpl.target_currency_code,
                memo=work_memo,
                base_amount=amt,
                base_currency=cur,
                element_category=cat_by_ce.get(ce_id),
            )
            unit_computed = str(fr.converted_amount)

        ovr = row.get("override_unit_cost")
        unit_cost = ovr if ovr else unit_computed

        # Sort + section: take from local line item when present, else inherit from the
        # parent's resolved row (so cascade preserves the SOA insertion order at COUNTRY/SITE
        # views — otherwise inherited rows would all have sort_order=0 and shuffle alphabetically).
        local_li = local_by_ce.get(ce_id)
        par = parent_rows.get(ce_id)
        if local_li is not None:
            sort_order = int(local_li.sort_order or 0)
            soa_section = local_li.soa_section
            section = soa_section or cat_by_ce.get(ce_id)
        else:
            sort_order = int((par or {}).get("sort_order") or 0)
            section = (par.get("category") if par else None) or cat_by_ce.get(ce_id)

        is_policy_included = bool(getattr(local_li, "is_policy_included", False)) if local_li else False

        out.append(
            {
                **row,
                "category": section,
                "sort_order": sort_order,
                "is_policy_included": is_policy_included,
                "unit_cost_computed": unit_computed,
                "unit_cost": unit_cost or unit_computed,
            }
        )

    # Sort by sort_order so section groups stay together in SOA-insertion order;
    # fall back to code/element_id for stability when sort_order ties.
    return sorted(out, key=lambda x: (x.get("sort_order") or 0, x.get("code") or "", x.get("cost_element_id") or ""))


async def propagate_trial_amendment_to_children(
    db: AsyncSession,
    trial_template_id: UUID,
    changed_element_ids: list[UUID],
) -> int:
    """
    When trial-level line items change, mark descendant templates' lines that override the same element for review.
    Does not overwrite values.
    """
    if not changed_element_ids:
        return 0

    ce_set = set(changed_element_ids)
    queue: list[UUID] = [trial_template_id]
    descendants: list[BudgetTemplate] = []
    seen: set[UUID] = set()
    while queue:
        pid = queue.pop(0)
        r = await db.execute(select(BudgetTemplate).where(BudgetTemplate.parent_template_id == pid))
        for ch in r.scalars().all():
            if ch.id in seen:
                continue
            seen.add(ch.id)
            descendants.append(ch)
            queue.append(ch.id)

    marked = 0
    for child in descendants:
        lines = await _line_rows_for_template(db, child.id)
        for li in lines:
            if li.cost_element_id not in ce_set:
                continue
            if li.override_unit_cost is None and li.override_quantity is None:
                continue
            li.needs_review = True
            marked += 1
    await db.flush()
    return marked


async def compute_budget_totals(
    db: AsyncSession,
    template_id: UUID,
    *,
    trial_id: UUID,
    country_code: Optional[str],
    site_id: Optional[UUID],
    memo: Optional[RequestMemo] = None,
    use_totals_cache: bool = True,
) -> dict[str, Any]:
    tmpl = await repo.get_template(db, template_id, load_children=False)
    if not tmpl:
        raise ValueError("Template not found")

    # Derive geo context from template level when not explicitly provided.
    eff_country = country_code
    eff_site = site_id
    lvl = getattr(tmpl, "template_level", None)
    if eff_country is None and lvl in ("COUNTRY", "SITE"):
        eff_country = getattr(tmpl, "country_code", None)
    if eff_site is None and lvl == "SITE" and getattr(tmpl, "site_id", None) is not None:
        eff_site = tmpl.site_id

    ck = budget_totals_cache.totals_key(template_id, eff_country, eff_site)
    if use_totals_cache:
        hit = budget_totals_cache.get_totals(ck)
        if hit is not None:
            return hit

    work_memo = memo if memo is not None else RequestMemo()
    vm = await resolve_visit_matrix(db, template_id, memo=work_memo)
    resolved = await resolve_budget_line_items(
        db,
        template_id,
        country_code=eff_country,
        site_id=eff_site,
        visit_matrix_precomputed=vm,
        memo=work_memo,
    )

    target_currency = tmpl.target_currency_code or "USD"
    enrollment = Decimal(tmpl.enrollment_planned or 0)

    per_patient = Decimal(0)
    line_details: list[dict[str, Any]] = []

    for row in resolved:
        if row.get("is_excluded"):
            continue
        qty_raw = row.get("quantity")
        if qty_raw is None:
            continue
        qty = Decimal(str(qty_raw))
        uc_raw = row.get("unit_cost_computed") or row.get("unit_cost")
        if uc_raw is None:
            continue
        unit_dec = Decimal(str(uc_raw))
        line_total = unit_dec * qty
        per_patient += line_total
        lid = row.get("line_item_id")
        line_details.append(
            {
                "line_item_id": str(lid) if lid else None,
                "cost_element_id": str(row.get("cost_element_id") or ""),
                "units": str(qty),
                "unit_converted": str(unit_dec),
                "line_total": str(line_total),
            }
        )

    milestone_total = await sum_milestone_ancestor_chain(db, template_id)

    # ── Personnel total ───────────────────────────────────────────────────────
    p_q = await db.execute(
        select(BudgetPersonnelRole).where(BudgetPersonnelRole.budget_template_id == template_id)
    )
    personnel_rows = p_q.scalars().all()
    personnel_total = Decimal(0)
    personnel_details: list[dict[str, Any]] = []
    for pr in personnel_rows:
        hr  = Decimal(str(pr.hourly_rate or 0))
        su  = Decimal(str(pr.startup_hrs or 0))
        sc  = Decimal(str(pr.screening_hrs or 0))
        osm = Decimal(str(pr.on_study_hrs_per_month or 0))
        mo  = Decimal(str(pr.months or 0))
        co  = Decimal(str(pr.closeout_hrs or 0))
        oh  = Decimal(str(pr.overhead_pct or 0))
        total_hrs  = su + sc + (osm * mo) + co
        total_cost = total_hrs * hr
        oh_amount  = total_cost * (oh / 100)
        role_total = total_cost + oh_amount
        personnel_total += role_total
        personnel_details.append({
            "role_name":    pr.role_name,
            "total_hours":  str(total_hrs.quantize(Decimal("0.01"))),
            "total_cost":   str(total_cost.quantize(Decimal("0.01"))),
            "oh_amount":    str(oh_amount.quantize(Decimal("0.01"))),
            "role_total":   str(role_total.quantize(Decimal("0.01"))),
        })

    total_budget = per_patient * enrollment + milestone_total + personnel_total

    def _q2(x: Decimal) -> str:
        return str(x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    factor_breakdown: Optional[dict[str, Any]] = None
    if line_details:
        best = max(line_details, key=lambda x: Decimal(x["line_total"]))
        if Decimal(best["line_total"]) > 0:
            ce_id = UUID(best["cost_element_id"])
            row_best = next((r for r in resolved if str(r.get("cost_element_id")) == best["cost_element_id"]), None)
            versioned_b = await cost_service.bulk_get_versioned_costs(db, [ce_id], trial_id, template=tmpl)
            element_map_b = await repo.bulk_cost_elements(db, [ce_id])
            vc = versioned_b.get(ce_id)
            if vc:
                amt, cur = vc
                if row_best and row_best.get("override_unit_cost"):
                    amt = Decimal(str(row_best["override_unit_cost"]))
                    cur = row_best.get("override_currency_code") or target_currency
                el = element_map_b.get(ce_id)
                ec = (el.category.name if el.category else None) if el else None
                code_label = str(row_best.get("code") or "") if row_best else ""
                fr = await factor_service.compute_final_unit_cost(
                    db,
                    element_id=ce_id,
                    trial_id=trial_id,
                    country_code=eff_country,
                    site_id=eff_site,
                    target_currency=target_currency,
                    memo=work_memo,
                    base_amount=amt,
                    base_currency=cur,
                    element_category=ec,
                )
                steps_out: list[dict[str, Any]] = []
                for st in fr.applied_steps:
                    mode = st.get("mode")
                    if mode == "MULTIPLICATIVE":
                        rk = st.get("rank")
                        try:
                            label = _factor_scope_label_from_rank(int(rk)) if rk is not None else "Factor"
                        except (TypeError, ValueError):
                            label = "Factor"
                        steps_out.append(
                            {
                                "scope": label,
                                "mode": "MULTIPLICATIVE",
                                "value": st.get("value"),
                                "display": f"×{st.get('value')}",
                            }
                        )
                    elif mode == "ADDITIVE":
                        rk = st.get("rank")
                        try:
                            label = _factor_scope_label_from_rank(int(rk)) if rk is not None else "Factor"
                        except (TypeError, ValueError):
                            label = "Factor"
                        steps_out.append(
                            {
                                "scope": label,
                                "mode": "ADDITIVE",
                                "value": st.get("value"),
                                "display": f"+{st.get('value')}",
                            }
                        )
                factor_breakdown = {
                    "example_line_code": code_label,
                    "base_amount": str(fr.base_amount),
                    "base_currency": fr.base_currency,
                    "final_amount": str(fr.converted_amount),
                    "target_currency": fr.target_currency,
                    "factors": steps_out,
                }

    result = {
        "template_id": str(template_id),
        "trial_id": str(trial_id),
        "target_currency": target_currency,
        "enrollment_planned": tmpl.enrollment_planned,
        "cost_version_label": tmpl.cost_version_label,
        "locked_pricing": cost_service.is_budget_locked(tmpl),
        "per_patient_total": _q2(per_patient),
        "milestone_total": _q2(milestone_total),
        "milestone_includes_ancestor_chain": True,
        "personnel_total": _q2(personnel_total),
        "personnel_details": personnel_details,
        "total_budget": _q2(total_budget),
        "lines": line_details,
        "factor_breakdown": factor_breakdown,
    }
    if use_totals_cache:
        budget_totals_cache.set_totals(ck, result)
    return result


# ─── Dynamic visit-pattern parsing (no hardcoded protocol values) ────────────

def _parse_interval_weeks(text: str) -> Optional[int]:
    """
    Parse a recurrence interval, expressed in WEEKS, from free text.

    Handles days / weeks / months / years so follow-up cadences like
    "Every 3 months" or "Every 6 months" scale correctly (previously only weeks
    were understood, so month-based visits fell back to count = 1).

      qNd / qNw / qNm / qNy      (e.g. q28d, q4w, q3m)
      every N days|weeks|months|years
      weekly / monthly / quarterly

    A month is treated as 4 weeks and a year as 52 weeks (same 4-week cadence used
    for treatment cycles), so "every 3 months" → 12 weeks, "every 6 months" → 24.
    Returns None when nothing parseable.
    """
    if not text:
        return None

    def _to_weeks(n: int, unit: str) -> Optional[int]:
        if n <= 0:
            return None
        u = unit[0]
        if u == "d":
            return max(1, round(n / 7))
        if u == "w":
            return n
        if u == "m":
            return n * 4
        if u == "y":
            return n * 52
        return None

    # q-notation: q4w, q3m, q28d, q.2.w
    m = re.search(r"\bq\.?\s*(\d+)\s*\.?\s*([dwmy])\b", text)
    if m:
        return _to_weeks(int(m.group(1)), m.group(2))

    # "every N day/week/month/year(s)"
    m = re.search(r"every\s+(\d+)\s*(day|week|month|year)s?", text)
    if m:
        return _to_weeks(int(m.group(1)), m.group(2))

    # bare cadence words
    if re.search(r"\bweekly\b", text):
        return 1
    if re.search(r"\bmonthly\b", text):
        return 4
    if re.search(r"\bquarterly\b", text):
        return 12
    return None


def _parse_end_week(text: str) -> Optional[int]:
    """thru/until/through Wk N, before Wk N, ≤ N, < N. None if not parseable."""
    if not text:
        return None
    m = re.search(r"(?:thru|through|until|before|<=|≤|<)\s*(?:wk|week)\.?\s*(\d+)", text)
    if m:
        try:
            n = int(m.group(1))
            return n if n >= 0 else None
        except (TypeError, ValueError):
            return None
    return None


def _parse_start_week(text: str) -> Optional[int]:
    """from/after/starting Wk N, > Wk N, ≥ N. None if not parseable."""
    if not text:
        return None
    m = re.search(r"(?:from|after|starting|>=|≥|>)\s*(?:wk|week)\.?\s*(\d+)", text)
    if m:
        try:
            n = int(m.group(1))
            return n if n >= 0 else None
        except (TypeError, ValueError):
            return None
    return None


_FIXED_KEYWORDS = (
    "screening", "baseline", "end of treatment", " eot", "eot ", "end visit", "end of study",
    "safety follow-up", "safety followup", "follow-up (single)", "single follow",
)

_UNSCHEDULED_KEYWORDS = ("unscheduled",)

_FOLLOWUP_KEYWORDS = ("follow-up", "follow up", "followup", "survival", "long-term", "long term", "post-treatment")

# Cycle-based recurrence: "Subsequent Cycles", "Day 1 of each cycle", "per cycle",
# "every cycle", "q1c". These repeat once per treatment cycle, so their count scales
# with treatment duration. The cycle length is derived per-protocol from the SOA's
# own visit days (see _infer_cycle_weeks, e.g. C1D1=Day 1, C2D1=Day 29 -> 4 weeks);
# _DEFAULT_CYCLE_WEEKS is only the fallback when the SOA has no datable cycle starts.
_CYCLE_RECURRENCE_RE = re.compile(r"\b(each|every|per|subsequent)\s+cycles?\b|\bcycles?\s+thereafter\b|\bq1c\b")
_DEFAULT_CYCLE_WEEKS = 4


def _classify_visit_frequency(name: str, day: str = "") -> dict[str, Any]:
    """
    Dynamic classifier: derives visit_type + interval/start/end metadata from the visit
    name and (optionally) day field. No protocol-specific hardcoding. Never raises.

    Returns one of:
      { 'visit_type': 'fixed' }
      { 'visit_type': 'unscheduled' }
      { 'visit_type': 'frequency', 'interval_weeks'?, 'start_week'?, 'end_week'?, 'basis': 'treatment'|'followup' }
      { 'visit_type': 'unknown' }
    """
    try:
        text = ((name or "") + " " + (day or "")).lower()

        # Unscheduled wins early — explicit user-added or imported "Unscheduled N".
        if any(k in text for k in _UNSCHEDULED_KEYWORDS) or re.search(r"\buns\d*\b", text):
            return {"visit_type": "unscheduled"}

        # Frequency markers → parse interval / start / end.
        interval = _parse_interval_weeks(text)
        has_freq_marker = (
            interval is not None
            or bool(re.search(r"\bq\.?\d+\.?w\b|\bweekly\b|every\s+\d+", text))
        )

        if has_freq_marker:
            basis = "followup" if any(k in text for k in _FOLLOWUP_KEYWORDS) else "treatment"
            return {
                "visit_type": "frequency",
                "interval_weeks": interval,
                "start_week": _parse_start_week(text),
                "end_week": _parse_end_week(text),
                "basis": basis,
            }

        # Cycle-based recurrence ("Subsequent Cycles", "Day 1 of each cycle") → repeats
        # once per treatment cycle. No explicit interval in the SOA, so assume a 4-week
        # (28-day) cycle. Count over the treatment window = treatment_weeks / 4.
        if _CYCLE_RECURRENCE_RE.search(text):
            basis = "followup" if any(k in text for k in _FOLLOWUP_KEYWORDS) else "treatment"
            return {
                "visit_type": "frequency",
                "interval_weeks": _DEFAULT_CYCLE_WEEKS,
                "start_week": None,
                "end_week": None,
                "basis": basis,
                "cycle_based": True,
            }

        # Fixed by keyword (Screening / Baseline / End / single follow-up).
        if any(k in text for k in _FIXED_KEYWORDS):
            return {"visit_type": "fixed"}

        # Anything else is unknown — caller falls back to count = 1.
        return {"visit_type": "unknown"}
    except Exception:
        # Never crash on weird visit names — degrade to safe default.
        return {"visit_type": "unknown"}


def _compute_visit_count(
    classification: dict[str, Any],
    treatment_weeks: Optional[int],
    followup_weeks: Optional[int],
    unscheduled_count: int,
) -> Decimal:
    """
    Generic, safe count formula. Returns a non-negative Decimal quantized to 2 dp.

      fixed       → 1
      unscheduled → unscheduled_count (>= 0)
      frequency   → max(0, (effective_end - effective_start) / interval_weeks)
                    where:
                      duration       = treatment_weeks if basis == 'treatment'
                                       else followup_weeks
                      effective_start = start_week if not None else 0
                      effective_end   = min(duration, end_week) if end_week else duration
                    If interval_weeks is None → fallback to 1 (safe default).
      unknown     → 1 (safe default — caller may override with any prior cell value)
    """
    try:
        vt = (classification or {}).get("visit_type", "unknown")

        if vt == "fixed":
            return Decimal("1")

        if vt == "unscheduled":
            n = max(0, int(unscheduled_count or 0))
            return Decimal(str(n))

        if vt == "frequency":
            interval = classification.get("interval_weeks")
            if not interval or interval <= 0:
                return Decimal("1")  # safe default — name had a freq marker but no parseable N

            basis = classification.get("basis", "treatment")
            treat_w = max(0, int(treatment_weeks or 0))
            fu_w = max(0, int(followup_weeks or 0))
            duration = fu_w if basis == "followup" else treat_w

            start = classification.get("start_week")
            end = classification.get("end_week")

            effective_start = int(start) if start is not None else 0
            effective_end = min(duration, int(end)) if end is not None else duration

            if duration <= 0 or effective_end <= effective_start:
                return Decimal("0")

            count = (effective_end - effective_start) / interval
            count = max(0.0, count)
            # A partial recurrence still means the visit happens — round UP to the
            # next whole visit (e.g. 1.67 -> 2, 0.83 -> 1) so no visit is under-counted.
            return Decimal(str(count)).quantize(Decimal("1"), rounding=ROUND_CEILING)

        # unknown → never crash, never zero out a cell
        return Decimal("1")
    except Exception:
        return Decimal("1")


def _extract_day_number(text: str) -> Optional[int]:
    """
    Best-effort: parse a representative *day from baseline* number out of the SOA's
    free-text `day` field. Returns None when no parseable token is present.

    Recognises: "Day 8", "Week 4", "4 weeks", "Month 3", "3 months", "5 years",
    "C2D1" (cycle 2 day 1 → assume 28-day cycles), "Cycles 2-8 (Day 1)" → take
    last cycle.
    """
    if not text:
        return None
    t = text.lower()
    # "Day -28 to -1" or "Day N" — take the largest absolute number
    days_seen: list[int] = []
    for m in re.finditer(r"day\s+(-?\d+)", t):
        days_seen.append(int(m.group(1)))
    if days_seen:
        return max(days_seen, key=abs)
    # "Week N" / "N weeks" / "N week" → days
    m = re.search(r"week\s++(\d++)", t) or re.search(r"(\d++)\s*+weeks?\b", t)
    if m:
        return int(m.group(1)) * 7
    # Cycle / day: "C2D8"
    m = re.search(r"c(\d+)d(\d+)", t)
    if m:
        return (int(m.group(1)) - 1) * 28 + int(m.group(2))
    # "Cycles 2-8 (Day 1)" — last cycle
    m = re.search(r"cycles?\s+\d+\s*-\s*(\d+)", t)
    if m:
        return (int(m.group(1)) - 1) * 28
    # "Cycle N"
    m = re.search(r"cycle\s+(\d+)", t)
    if m:
        return (int(m.group(1)) - 1) * 28
    # "Month N" / "N months"
    m = re.search(r"month\s++(\d++)", t) or re.search(r"(\d++)\s*+months?\b", t)
    if m:
        return int(m.group(1)) * 30
    # "N years"
    m = re.search(r"(\d++)\s*+years?\b", t)
    if m:
        return int(m.group(1)) * 365
    return None


def _infer_cycle_weeks(visits: list[dict[str, Any]]) -> Optional[float]:
    """
    Derive the treatment cycle length in WEEKS from the SOA's own visit days,
    rather than assuming it. Looks at visits that mark *Day 1 of a cycle*
    (C1D1, C2D1, "Cycle 2 Day 1", …) together with their absolute study day, then:

        cycle_days = (later cycle's Day-1 study-day - earlier cycle's Day-1 study-day)
                     / (difference in cycle number)

    e.g. C1D1 = Day 1 and C2D1 = Day 29 -> (29 - 1) / (2 - 1) = 28 days = 4 weeks.

    Returns None when fewer than two cycle-start visits carry an explicit day, so
    the caller can fall back to a default cycle length.
    """
    points: list[tuple[int, int]] = []  # (cycle_number, absolute_day)
    for v in visits:
        label = f"{v.get('visit_name', '')} {v.get('visit_code', '')}".lower()
        cd = re.search(r"c(?:ycle)?\s*(\d+)\s*[/\-]?\s*d(?:ay)?\s*(\d+)", label)
        if not cd:
            continue
        cycle_num, day_in_cycle = int(cd.group(1)), int(cd.group(2))
        if day_in_cycle != 1:
            continue  # only a cycle's Day 1 marks a cycle boundary
        dm = re.search(r"day\s+(-?\d+)", (v.get("target_day") or "").lower())
        if not dm:
            continue  # need an explicit absolute day, not an assumed one
        points.append((cycle_num, int(dm.group(1))))

    if len(points) < 2:
        return None
    points.sort()
    (c_lo, d_lo), (c_hi, d_hi) = points[0], points[-1]
    if c_hi == c_lo:
        return None
    cycle_days = (d_hi - d_lo) / (c_hi - c_lo)
    if cycle_days <= 0:
        return None
    return round(cycle_days / 7.0, 2)


_SCREENING_KEYWORDS = ("screening", "screen", "pre-screen", "baseline")


def _classify_visit(name: str) -> str:
    text = (name or "").lower()
    if any(k in text for k in _SCREENING_KEYWORDS):
        return "screening"
    if any(k in text for k in _FOLLOWUP_KEYWORDS):
        return "followup"
    return "treatment"


def _soa_durations_weeks(visits: list[dict[str, Any]]) -> tuple[Optional[float], Optional[float]]:
    """
    From the normalized SOA visits list, infer the actual span of treatment and
    follow-up windows in WEEKS by parsing each visit's `target_day` field.
    Returns (treatment_weeks, followup_weeks); either may be None if SOA didn't
    contain enough day info for that category.
    """
    treatment_days: list[int] = []
    followup_days: list[int] = []
    for v in visits:
        cat = _classify_visit(v.get("visit_name", ""))
        if cat == "screening":
            continue
        day = _extract_day_number(v.get("target_day") or "")
        if day is None:
            continue
        if cat == "treatment":
            treatment_days.append(day)
        elif cat == "followup":
            followup_days.append(day)

    def _span(days: list[int]) -> Optional[float]:
        if not days:
            return None
        span = max(days) - min(days)
        # Single-visit category — fall back to absolute day from baseline.
        if span <= 0:
            span = max(days)
        return span / 7.0 if span > 0 else None

    return _span(treatment_days), _span(followup_days)


async def _get_or_create_category(db: AsyncSession, name: Optional[str]) -> Optional[UUID]:
    """Look up an ElementCategory by name (case-insensitive). Create one if missing."""
    if not name:
        return None
    n = name.strip()
    if not n:
        return None
    existing = (
        await db.execute(select(ElementCategory).where(func.lower(ElementCategory.name) == n.lower()))
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id
    new_cat = ElementCategory(name=n, sort_order=999)
    db.add(new_cat)
    await db.flush()
    return new_cat.id


async def _get_or_create_element_for_activity(
    db: AsyncSession,
    activity_name: str,
    section_title: Optional[str],
) -> Optional[CostElement]:
    """
    SOA activity → CostElement. Reuses any existing cost_element with the same name
    (case-insensitive); otherwise creates a fresh one with code `SOA-<8-hex>`. The
    section title becomes the element's category. Cost defaults to 0 — user fills in
    the Cost Master Elements tab later.
    """
    name = (activity_name or "").strip()
    if not name:
        return None

    # cost_element.name is NOT unique, so a case-insensitive match can legitimately
    # return several rows (e.g. a seeded element plus an earlier SOA-auto-created one
    # with the same name). Prefer an ACTIVE row (inactive ones are hidden from the
    # Elements tab), then order by code so canonical seeded codes (ARC-001, VISIT-002,
    # …) win over generated SOA-<hex> ones. scalar_one_or_none() here would raise
    # MultipleResultsFound and 500 the generate.
    existing = (
        await db.execute(
            select(CostElement)
            .where(func.lower(CostElement.name) == name.lower())
            .order_by(CostElement.is_active.desc(), CostElement.code)
        )
    ).scalars().first()
    if existing is not None:
        return existing

    cat_id = await _get_or_create_category(db, section_title)
    code = f"SOA-{uuid.uuid4().hex[:8].upper()}"
    el = CostElement(
        code=code,
        name=name,
        description=section_title or "",
        unit_of_measure="Per Visit",
        category_id=cat_id,
        element_type="ATOMIC",
        cost_type="PER_VISIT",
        is_active=True,
    )
    db.add(el)
    await db.flush()

    # Auto-price the new element so it never shows as an empty/$0 cost in a budget.
    # Prefer copying an already-priced element with the same concept (dedup rule),
    # otherwise fall back to a market-standard price keyed off the activity name.
    price = await _price_for_new_element(db, name)
    db.add(ElementCostVersion(
        element_id=el.id,
        version_label="FMV-2026",
        base_unit_cost=price,
        reference_currency="USD",
        effective_from=date.today(),
        source="auto-activity-price",
        is_bundle_override=False,
    ))
    await db.flush()
    return el


# Market-standard prices (USD) for auto-created SoA activity elements, keyed by the
# concept found in the activity name. Grounded in the seeded FMV catalog so an
# auto-priced element matches its hand-priced siblings. First match wins.
_ACTIVITY_PRICE_RULES: list[tuple[list[str], Decimal]] = [
    (["physical exam"], Decimal("65")),
    (["vital sign"], Decimal("35")),
    (["ecog"], Decimal("25")),
    (["ecg", "12-lead", "electrocardiogram"], Decimal("125")),
    (["adverse+concomitant"], Decimal("75")),
    (["sae"], Decimal("320")),
    (["adverse event"], Decimal("65")),
    (["concomitant"], Decimal("30")),
    (["fresh+biops", "core biops"], Decimal("1200")),
    (["archival", "tissue collection", "tissue retrieval"], Decimal("180")),
    (["biops"], Decimal("1200")),
    (["tumor+mri", "tumor+ct/", "tumor+imag", "tumor+evaluation", "tumor+assessment", "tumor+scan"], Decimal("1850")),
    (["hematology+chemistry", "heme, chem"], Decimal("85")),
    (["coagulation"], Decimal("40")),
    (["hematology"], Decimal("40")),
    (["chemistry"], Decimal("45")),
    (["urinalysis"], Decimal("20")),
    (["thyroid"], Decimal("55")),
    (["pregnancy"], Decimal("25")),
    (["ca19", "cea"], Decimal("65")),
    (["immunogenicity", "(ada)", "anti-drug antib"], Decimal("280")),
    (["retrospective", "translational", "biomarker"], Decimal("50")),
    (["pharmacokinet"], Decimal("85")),
    (["ophthalmolog", "eye exam"], Decimal("150")),
    (["tsh", "thyroid"], Decimal("55")),
    (["survival", "follow-up contact"], Decimal("280")),
    (["unscheduled", "toxicity"], Decimal("480")),
    (["inclusion", "exclusion", "eligibility criteria"], Decimal("120")),
    (["medical+history"], Decimal("150")),
    (["demographic"], Decimal("50")),  # after medical+history so "…& Demographics" -> 150
    (["informed consent"], Decimal("180")),
    (["dpd"], Decimal("150")),
    (["pre-medication", "premedication"], Decimal("35")),
    (["dose modification"], Decimal("45")),
    (["genetic", "pharmacogenom"], Decimal("850")),
    (["administration", "tislelizumab", "infusion", "study drug"], Decimal("185")),
]
_ACTIVITY_PRICE_DEFAULT = Decimal("100")  # generic per-visit assessment — never leave $0


def _market_price_for_activity(name: str) -> Decimal:
    """Best-effort market price for an activity name (see _ACTIVITY_PRICE_RULES)."""
    n = (name or "").lower()
    # word-boundary check for standalone "pk" (PK sampling) before the rules run
    if re.search(r"\bpk\b", n):
        return Decimal("85")
    for keywords, price in _ACTIVITY_PRICE_RULES:
        for kw in keywords:
            if "+" in kw:  # all sub-terms must be present
                if all(part in n for part in kw.split("+")):
                    return price
            elif kw in n:
                return price
    return _ACTIVITY_PRICE_DEFAULT


async def _price_for_new_element(db: AsyncSession, name: str) -> Decimal:
    """
    Price a freshly-created activity element. Rule 2 first: if another priced element
    shares this (case-insensitive) name, reuse its cost. Rule 1 otherwise: a market
    price by concept. Never returns 0.
    """
    sibling = (
        await db.execute(
            select(ElementCostVersion.base_unit_cost)
            .join(CostElement, CostElement.id == ElementCostVersion.element_id)
            .where(func.lower(CostElement.name) == (name or "").lower())
            .where(ElementCostVersion.base_unit_cost > 0)
            .order_by(ElementCostVersion.effective_from.desc().nullslast())
            .limit(1)
        )
    ).scalar_one_or_none()
    if sibling is not None and sibling > 0:
        return sibling
    return _market_price_for_activity(name)


async def generate_visit_matrix_from_soa(
    db: AsyncSession,
    *,
    template_id: UUID,
    study_id: str,
    treatment_duration: Optional[int] = None,
    followup_duration: Optional[int] = None,
    unscheduled_visits: int = 0,
) -> dict[str, Any]:
    """
    Build a visit matrix for `template_id` from the MongoDB-stored SOA of `study_id`.

    Each visit is classified as:
      - fixed       → count = 1, cell quantity unchanged
      - frequency   → count from formula (q8w / q12w / survival follow-up), cells × count
      - unscheduled → count = unscheduled_count

    Cell quantity = SOA per-occurrence units × computed visit count.
    """
    tmpl = await repo.get_template(db, template_id)
    if tmpl is None:
        raise ValueError("Template not found")

    # 1. Fetch SOA from Mongo
    soa_doc = await mongo_service.fetch_soa(study_id)
    if soa_doc is None:
        raise ValueError(f"No SOA found in Mongo for study_id={study_id!r}")

    # 2. Normalize the SOA — gives us visits[] and activities[] (each activity carries
    #    name, category=section title, visit_indices). No catalog matching anywhere.
    normalized = ai_budget_service.normalize_soa(soa_doc)

    # Cycle length for this protocol: derive it from the SOA's own visit days
    # (e.g. C1D1=Day 1, C2D1=Day 29 -> 28 days = 4 weeks). Fall back to the default
    # only when the SOA doesn't carry two datable cycle-start visits.
    cycle_weeks = _infer_cycle_weeks(normalized.get("visits") or []) or _DEFAULT_CYCLE_WEEKS

    # 4. Apply the plan
    trial_id = tmpl.trial_id
    inserted_visits = 0
    inserted_lines = 0
    inserted_cells = 0
    skipped = 0

    # Pre-create visits in SOA index order so column order is preserved.
    # Existing visits with the same name on this trial are reused.
    last_order_db = (
        await db.execute(
            select(VisitSchedule.visit_order)
            .where(VisitSchedule.trial_id == trial_id)
            .order_by(VisitSchedule.visit_order.desc())
            .limit(1)
        )
    ).scalar_one_or_none() or 0
    next_order = int(last_order_db)
    name_to_visit: dict[str, VisitSchedule] = {}
    name_to_class: dict[str, dict[str, Any]] = {}
    for v in normalized["visits"]:
        vname = v["visit_name"]
        if vname in name_to_visit:
            continue
        cls = _classify_visit_frequency(vname, v.get("target_day") or "")
        # Cycle-based visits ("Subsequent Cycles") use the protocol's actual cycle
        # length inferred above, instead of the generic default.
        if cls.get("cycle_based"):
            cls["interval_weeks"] = cycle_weeks
        name_to_class[vname] = cls
        # (trial_id, visit_name) is not unique — the same visit name can exist under
        # several templates of one trial — so match may return multiple rows. Take the
        # earliest by visit_order deterministically instead of raising MultipleResultsFound.
        existing = (
            await db.execute(
                select(VisitSchedule)
                .where(
                    VisitSchedule.trial_id == trial_id,
                    VisitSchedule.visit_name == vname,
                )
                .order_by(
                    VisitSchedule.is_active.desc(),
                    VisitSchedule.visit_order,
                    VisitSchedule.id,
                )
            )
        ).scalars().first()
        if existing is not None:
            # Update classification metadata even on existing rows so re-runs reclassify cleanly.
            existing.visit_type = cls.get("visit_type")
            existing.interval_weeks = cls.get("interval_weeks")
            existing.start_week = cls.get("start_week")
            existing.end_week = cls.get("end_week")
            name_to_visit[vname] = existing
            continue
        next_order += 10
        vs = VisitSchedule(
            trial_id=trial_id,
            budget_template_id=template_id,
            visit_name=vname,
            visit_code=(v.get("visit_code") or v.get("target_day") or None),
            visit_order=next_order,
            is_active=True,
            visit_type=cls.get("visit_type"),
            interval_weeks=cls.get("interval_weeks"),
            start_week=cls.get("start_week"),
            end_week=cls.get("end_week"),
        )
        db.add(vs)
        await db.flush()
        name_to_visit[vname] = vs
        inserted_visits += 1

    # ── Per-visit count multiplier (replaces the old scaling/ratio logic) ──────
    # cell_qty = SOA_units × computed_count, where count is determined by the visit's
    # classification (fixed = 1, frequency = formula, unscheduled = user count).
    visit_count_by_name: dict[str, Decimal] = {
        vname: _compute_visit_count(
            cls,
            treatment_weeks=treatment_duration,
            followup_weeks=followup_duration,
            unscheduled_count=int(unscheduled_visits or 0),
        )
        for vname, cls in name_to_class.items()
    }

    def _scale(qty: Decimal, vname: str) -> Decimal:
        return qty * visit_count_by_name.get(vname, Decimal("1"))

    # ── DB-driven matrix population (no catalog matching, no LLM) ─────────────
    # Walk normalized SOA activities. Each unique activity name becomes one row in
    # the matrix (auto-creating a CostElement when we don't already have one with
    # the same name). Cells are inserted only at visits the SOA explicitly lists for
    # the activity. The same _scale() count multiplier applies on top.

    last_sort_db = (
        await db.execute(
            select(BudgetLineItem.sort_order)
            .where(BudgetLineItem.budget_template_id == template_id)
            .order_by(BudgetLineItem.sort_order.desc())
            .limit(1)
        )
    ).scalar_one_or_none() or 0
    next_sort = int(last_sort_db)

    # Cache (activity-name → line_item) so the same activity reuses the same row.
    activity_to_line_item: dict[str, BudgetLineItem] = {}

    for act in normalized.get("activities", []):
        act_name = (act.get("name") or "").strip()
        if not act_name:
            skipped += 1
            continue

        # 1. Get-or-create a CostElement for this activity.
        el = await _get_or_create_element_for_activity(
            db, act_name, act.get("category")
        )
        if el is None:
            skipped += 1
            continue

        # 2. Get-or-create the BudgetLineItem on this template.
        section_title = (act.get("category") or None)
        li = activity_to_line_item.get(act_name.lower())
        if li is None:
            li = (
                await db.execute(
                    select(BudgetLineItem).where(
                        BudgetLineItem.budget_template_id == template_id,
                        BudgetLineItem.cost_element_id == el.id,
                    )
                )
            ).scalar_one_or_none()
            if li is None:
                next_sort += 10
                li = BudgetLineItem(
                    budget_template_id=template_id,
                    cost_element_id=el.id,
                    is_excluded=False,
                    sort_order=next_sort,
                    soa_section=section_title,
                )
                db.add(li)
                await db.flush()
                inserted_lines += 1
            else:
                # Re-import: refresh the section tag in case the SOA grouped this differently.
                if section_title:
                    li.soa_section = section_title
            activity_to_line_item[act_name.lower()] = li

        # 3. For every visit the SOA references for this activity, write the cell.
        visit_names_for_act = act.get("visit_names") or []
        if not visit_names_for_act:
            # Activity with no visit_indices in SOA — fallback: occurs at every visit.
            visit_names_for_act = list(name_to_visit.keys())

        for vname in visit_names_for_act:
            vs = name_to_visit.get(vname)
            if vs is None:
                skipped += 1
                continue

            # Apply the visit-count multiplier (frequency / unscheduled rules).
            quantity = _scale(Decimal("1"), vname).quantize(Decimal("0.0001"))

            existing_cell = (
                await db.execute(
                    select(BudgetVisitMatrix).where(
                        BudgetVisitMatrix.budget_line_item_id == li.id,
                        BudgetVisitMatrix.visit_schedule_id == vs.id,
                    )
                )
            ).scalar_one_or_none()
            if existing_cell is not None:
                existing_cell.units = quantity
            else:
                db.add(
                    BudgetVisitMatrix(
                        budget_line_item_id=li.id,
                        visit_schedule_id=vs.id,
                        units=quantity,
                        is_excluded=False,
                    )
                )
                await db.flush()
                inserted_cells += 1

    # 5. Append Unscheduled N visits (no default cells — user can fill in units)
    appended_unscheduled = 0
    if unscheduled_visits and unscheduled_visits > 0:
        last_order = (
            await db.execute(
                select(VisitSchedule.visit_order)
                .where(VisitSchedule.trial_id == trial_id)
                .order_by(VisitSchedule.visit_order.desc())
                .limit(1)
            )
        ).scalar_one_or_none() or 0
        for i in range(1, int(unscheduled_visits) + 1):
            name = f"Unscheduled {i}"
            existing = (
                await db.execute(
                    select(VisitSchedule.id).where(
                        VisitSchedule.trial_id == trial_id,
                        VisitSchedule.visit_name == name,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue
            last_order += 10
            db.add(
                VisitSchedule(
                    trial_id=trial_id,
                    budget_template_id=template_id,
                    visit_name=name,
                    visit_code=f"UNS{i}",
                    visit_order=last_order,
                    is_active=True,
                    visit_type="unscheduled",
                )
            )
            appended_unscheduled += 1
        if appended_unscheduled:
            await db.flush()

    # Default unit value for unscheduled visits = 1 across every line item that exists on
    # this template. Pre-existing cells are preserved (so re-running won't overwrite user edits).
    if unscheduled_visits and unscheduled_visits > 0:
        all_uns_visits = (
            await db.execute(
                select(VisitSchedule).where(
                    VisitSchedule.trial_id == trial_id,
                    VisitSchedule.visit_type == "unscheduled",
                )
            )
        ).scalars().all()
        if all_uns_visits:
            template_lines = (
                await db.execute(
                    select(BudgetLineItem).where(BudgetLineItem.budget_template_id == template_id)
                )
            ).scalars().all()
            for li in template_lines:
                for uvs in all_uns_visits:
                    has_cell = (
                        await db.execute(
                            select(BudgetVisitMatrix.id).where(
                                BudgetVisitMatrix.budget_line_item_id == li.id,
                                BudgetVisitMatrix.visit_schedule_id == uvs.id,
                            )
                        )
                    ).scalar_one_or_none()
                    if has_cell is not None:
                        continue
                    db.add(
                        BudgetVisitMatrix(
                            budget_line_item_id=li.id,
                            visit_schedule_id=uvs.id,
                            units=Decimal("1"),
                            is_excluded=False,
                        )
                    )
                    inserted_cells += 1
            await db.flush()

    budget_totals_cache.clear_all()

    # Snapshot the visit-count math actually applied so the audit log + UI can show it.
    visit_counts_snapshot = [
        {
            "visit_name": vname,
            "visit_type": cls.get("visit_type"),
            "interval_weeks": cls.get("interval_weeks"),
            "start_week": cls.get("start_week"),
            "end_week": cls.get("end_week"),
            "count": str(visit_count_by_name.get(vname, Decimal("1"))),
        }
        for vname, cls in name_to_class.items()
    ]

    return {
        "template_id": str(template_id),
        "study_id": study_id,
        "treatment_duration": treatment_duration,
        "followup_duration": followup_duration,
        "visit_counts": visit_counts_snapshot,
        "visits_inserted": inserted_visits,
        "line_items_inserted": inserted_lines,
        "matrix_cells_inserted": inserted_cells,
        "unscheduled_appended": appended_unscheduled,
        "unmapped_activities": [],  # always [] now — every SOA activity becomes a row
        "skipped": skipped,
    }
