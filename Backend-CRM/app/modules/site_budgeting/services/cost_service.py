"""Base and versioned cost lookups with optional FMV lock from budget template."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.site_budgeting.db_models import BudgetTemplate, CostElement, ElementBundleComposition, ElementCostVersion
from app.modules.site_budgeting.repositories import budgeting_repository as repo


def is_budget_locked(template: BudgetTemplate) -> bool:
    s = (template.status or "").lower()
    return s in ("executed", "approved", "locked")


async def get_base_cost(
    db: AsyncSession, element_id: UUID, version_label: str
) -> Optional[tuple[Decimal, str]]:
    row = await repo.get_cost_version_by_label(db, element_id, version_label)
    if not row:
        return None
    return (row.base_unit_cost, row.reference_currency)


async def get_versioned_cost(
    db: AsyncSession,
    element_id: UUID,
    trial_id: UUID,
    *,
    template: Optional[BudgetTemplate] = None,
) -> Optional[tuple[Decimal, str]]:
    """
    When template is locked (executed/approved/locked) and cost_version_label is set,
    always use that FMV vintage — never latest — so finalized budgets do not drift.
    """
    _ = trial_id  # reserved for trial-specific version maps
    if template and template.cost_version_label and is_budget_locked(template):
        row = await repo.get_cost_version_by_label(db, element_id, template.cost_version_label)
        if row:
            return (row.base_unit_cost, row.reference_currency)
    row = await repo.get_latest_cost_version(db, element_id)
    if not row:
        return None
    return (row.base_unit_cost, row.reference_currency)


async def _resolve_bundle_override_cost(
    db: AsyncSession,
    element_id: UUID,
    version_label: Optional[str],
    locked: bool,
) -> Optional[tuple[Decimal, str]]:
    """
    For BUNDLE elements: check for an is_bundle_override=True version first (guide §3.1).
    If found, use that negotiated bundle price instead of summing children.
    Returns None if no bundle override exists.
    """
    if version_label and locked:
        r = await db.execute(
            select(ElementCostVersion)
            .where(
                ElementCostVersion.element_id == element_id,
                ElementCostVersion.version_label == version_label,
                ElementCostVersion.is_bundle_override.is_(True),
            )
            .limit(1)
        )
    else:
        r = await db.execute(
            select(ElementCostVersion)
            .where(
                ElementCostVersion.element_id == element_id,
                ElementCostVersion.is_bundle_override.is_(True),
                ElementCostVersion.effective_to.is_(None),
            )
            .order_by(ElementCostVersion.effective_from.desc().nullslast(), ElementCostVersion.created_at.desc())
            .limit(1)
        )
    row = r.scalar_one_or_none()
    if row:
        return (row.base_unit_cost, row.reference_currency)
    return None


async def _sum_bundle_children_cost(
    db: AsyncSession,
    bundle_id: UUID,
    version_label: Optional[str],
    locked: bool,
) -> Optional[tuple[Decimal, str]]:
    """Sum the base costs of all atomic children for a bundle element."""
    r = await db.execute(
        select(ElementBundleComposition)
        .where(ElementBundleComposition.bundle_element_id == bundle_id)
    )
    compositions = list(r.scalars().all())
    if not compositions:
        return None

    total = Decimal(0)
    currency: Optional[str] = None
    for comp in compositions:
        child_id = comp.child_element_id
        if version_label and locked:
            child_row = await repo.get_cost_version_by_label(db, child_id, version_label)
        else:
            child_row = await repo.get_latest_cost_version(db, child_id)
        if child_row:
            total += child_row.base_unit_cost * Decimal(str(comp.quantity_in_bundle))
            if currency is None:
                currency = child_row.reference_currency
    return (total, currency or "USD") if currency is not None else None


async def get_versioned_cost_for_element(
    db: AsyncSession,
    element_id: UUID,
    element_type: Optional[str],
    *,
    version_label: Optional[str] = None,
    locked: bool = False,
) -> Optional[tuple[Decimal, str]]:
    """
    Get the FMV cost for a single element, respecting bundle override logic (guide §3.1):
    - BUNDLE with is_bundle_override=True version → use that negotiated price
    - BUNDLE without override → sum of children costs
    - ATOMIC → use versioned cost directly
    """
    if element_type == "BUNDLE":
        override = await _resolve_bundle_override_cost(db, element_id, version_label, locked)
        if override:
            return override
        return await _sum_bundle_children_cost(db, element_id, version_label, locked)

    if version_label and locked:
        row = await repo.get_cost_version_by_label(db, element_id, version_label)
    else:
        row = await repo.get_latest_cost_version(db, element_id)
    return (row.base_unit_cost, row.reference_currency) if row else None


async def bulk_get_versioned_costs(
    db: AsyncSession,
    element_ids: list[UUID],
    trial_id: UUID,
    *,
    template: Optional[BudgetTemplate] = None,
) -> dict[UUID, tuple[Decimal, str]]:
    """
    Batch FMV lookup with bundle override logic (guide §3.1).

    For BUNDLE elements: first checks for is_bundle_override=True version.
    If found, uses bundle negotiated price. Otherwise sums children.
    """
    _ = trial_id
    if not element_ids:
        return {}
    uniq: list[UUID] = list(dict.fromkeys(element_ids))
    locked = bool(template and template.cost_version_label and is_budget_locked(template))
    version_label = template.cost_version_label if locked else None

    # Fetch element types for bundle detection
    element_type_map: dict[UUID, str] = {}
    el_r = await db.execute(
        select(CostElement.id, CostElement.element_type).where(CostElement.id.in_(uniq))
    )
    for eid, etype in el_r.all():
        element_type_map[eid] = etype or "ATOMIC"

    bundle_ids = [eid for eid in uniq if element_type_map.get(eid) == "BUNDLE"]
    atomic_ids = [eid for eid in uniq if element_type_map.get(eid) != "BUNDLE"]

    out: dict[UUID, tuple[Decimal, str]] = {}

    # Atomic elements: batch lookup
    if atomic_ids:
        if locked and version_label:
            by_label = await repo.bulk_cost_versions_by_label(db, atomic_ids, version_label)
            missing = [eid for eid in atomic_ids if eid not in by_label]
            latest: dict[UUID, ElementCostVersion] = {}
            if missing:
                latest = await repo.bulk_latest_cost_versions(db, missing)
            for eid in atomic_ids:
                row = by_label.get(eid)
                if row is not None:
                    out[eid] = (row.base_unit_cost, row.reference_currency)
                    continue
                lr = latest.get(eid)
                if lr is not None:
                    out[eid] = (lr.base_unit_cost, lr.reference_currency)
        else:
            latest_all = await repo.bulk_latest_cost_versions(db, atomic_ids)
            for eid, row in latest_all.items():
                out[eid] = (row.base_unit_cost, row.reference_currency)

    # Bundle elements: apply override logic per element (guide §3.1)
    for bid in bundle_ids:
        result = await get_versioned_cost_for_element(
            db, bid, "BUNDLE", version_label=version_label, locked=locked
        )
        if result:
            out[bid] = result

    return out
