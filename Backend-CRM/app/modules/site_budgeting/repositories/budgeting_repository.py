from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional, Sequence
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.site_budgeting.db_models import (
    BudgetLineItem,
    BudgetMilestone,
    BudgetTemplate,
    BudgetVisitMatrix,
    ConversionFactor,
    ConversionFactorType,
    CostElement,
    CurrencyExchangeRate,
    ElementCostVersion,
    TrialFactorConfiguration,
    VisitSchedule,
)


async def get_cost_element(db: AsyncSession, element_id: UUID) -> CostElement | None:
    r = await db.execute(select(CostElement).where(CostElement.id == element_id))
    return r.scalar_one_or_none()


async def list_cost_elements(db: AsyncSession) -> Sequence[CostElement]:
    r = await db.execute(
        select(CostElement)
        .options(selectinload(CostElement.category))
        .order_by(CostElement.code)
    )
    return r.scalars().all()


async def get_cost_version_by_label(
    db: AsyncSession, element_id: UUID, version_label: str
) -> ElementCostVersion | None:
    r = await db.execute(
        select(ElementCostVersion).where(
            ElementCostVersion.element_id == element_id,
            ElementCostVersion.version_label == version_label,
        )
    )
    return r.scalar_one_or_none()


async def get_latest_cost_version(db: AsyncSession, element_id: UUID) -> ElementCostVersion | None:
    """Pick the most recently created version for the element (deterministic tie-breaker)."""
    r = await db.execute(
        select(ElementCostVersion)
        .where(ElementCostVersion.element_id == element_id)
        .order_by(ElementCostVersion.created_at.desc(), ElementCostVersion.id.desc())
        .limit(1)
    )
    return r.scalar_one_or_none()


async def bulk_latest_cost_versions(
    db: AsyncSession, element_ids: list[UUID]
) -> dict[UUID, ElementCostVersion]:
    """One query + in-memory pick of latest row per cost_element_id."""
    if not element_ids:
        return {}
    r = await db.execute(
        select(ElementCostVersion).where(ElementCostVersion.element_id.in_(element_ids))
    )
    rows: list[ElementCostVersion] = list(r.scalars().all())
    best: dict[UUID, ElementCostVersion] = {}
    for row in rows:
        eid = row.element_id
        cur = best.get(eid)
        if cur is None:
            best[eid] = row
            continue
        ca, cb = cur.created_at, row.created_at
        if cb is not None and (ca is None or cb > ca or (cb == ca and row.id > cur.id)):
            best[eid] = row
        elif ca == cb and row.id > cur.id:
            best[eid] = row
    return best


async def bulk_cost_versions_by_label(
    db: AsyncSession, element_ids: list[UUID], version_label: str
) -> dict[UUID, ElementCostVersion]:
    if not element_ids:
        return {}
    r = await db.execute(
        select(ElementCostVersion).where(
            ElementCostVersion.element_id.in_(element_ids),
            ElementCostVersion.version_label == version_label,
        )
    )
    rows = list(r.scalars().all())
    return {row.element_id: row for row in rows}


async def bulk_cost_elements(db: AsyncSession, element_ids: list[UUID]) -> dict[UUID, CostElement]:
    if not element_ids:
        return {}
    r = await db.execute(
        select(CostElement)
        .options(selectinload(CostElement.category))
        .where(CostElement.id.in_(element_ids))
    )
    return {row.id: row for row in r.scalars().all()}


async def load_visit_matrix_enriched(
    db: AsyncSession, template_id: UUID
) -> list[tuple[BudgetVisitMatrix, BudgetLineItem, VisitSchedule]]:
    """All matrix cells for a template with line item and visit in one round-trip (no N+1)."""
    r = await db.execute(
        select(BudgetVisitMatrix, BudgetLineItem, VisitSchedule)
        .select_from(BudgetVisitMatrix)
        .join(BudgetLineItem, BudgetVisitMatrix.budget_line_item_id == BudgetLineItem.id)
        .join(VisitSchedule, BudgetVisitMatrix.visit_schedule_id == VisitSchedule.id)
        .where(BudgetLineItem.budget_template_id == template_id)
    )
    return list(r.all())


async def list_conversion_factors_rows(
    db: AsyncSession, trial_id: Optional[UUID] = None
) -> list[ConversionFactor]:
    q = select(ConversionFactor)
    if trial_id is not None:
        q = q.where(or_(ConversionFactor.trial_id == trial_id, ConversionFactor.trial_id.is_(None)))
    r = await db.execute(q)
    return list(r.scalars().all())


async def bulk_conversion_factor_types(
    db: AsyncSession, type_ids: list[UUID]
) -> dict[UUID, ConversionFactorType]:
    if not type_ids:
        return {}
    r = await db.execute(select(ConversionFactorType).where(ConversionFactorType.id.in_(type_ids)))
    return {t.id: t for t in r.scalars().all()}


async def list_templates_for_trial(
    db: AsyncSession,
    trial_id: UUID,
    *,
    level: Optional[str] = None,
    country_code: Optional[str] = None,
    site_id: Optional[UUID] = None,
) -> Sequence[BudgetTemplate]:
    q = select(BudgetTemplate).where(BudgetTemplate.trial_id == trial_id)
    if level:
        q = q.where(BudgetTemplate.template_level == level)
    if country_code:
        q = q.where(BudgetTemplate.country_code == country_code.upper())
    if site_id:
        q = q.where(BudgetTemplate.site_id == site_id)
    q = q.order_by(BudgetTemplate.created_at.desc())
    r = await db.execute(q)
    return r.scalars().all()


async def get_template(db: AsyncSession, template_id: UUID, load_children: bool = False) -> BudgetTemplate | None:
    q = select(BudgetTemplate).where(BudgetTemplate.id == template_id)
    if load_children:
        q = q.options(
            selectinload(BudgetTemplate.line_items).selectinload(BudgetLineItem.cost_element),
            selectinload(BudgetTemplate.visit_schedules),
            selectinload(BudgetTemplate.milestones),
        )
    r = await db.execute(q)
    return r.scalar_one_or_none()


async def list_conversion_factors(
    db: AsyncSession, trial_id: Optional[UUID] = None
) -> Sequence[tuple[ConversionFactor, ConversionFactorType]]:
    q = (
        select(ConversionFactor, ConversionFactorType)
        .join(ConversionFactorType, ConversionFactor.factor_type_id == ConversionFactorType.id)
        .order_by(ConversionFactor.trial_id.nulls_last(), ConversionFactor.sequence_order)
    )
    if trial_id is not None:
        q = q.where(or_(ConversionFactor.trial_id == trial_id, ConversionFactor.trial_id.is_(None)))
    r = await db.execute(q)
    return r.all()


async def list_active_factors_for_trial(
    db: AsyncSession, trial_id: UUID
) -> list[tuple[ConversionFactor, ConversionFactorType, int]]:
    """
    Factors linked via trial_factor_configuration, ordered by sequence_override or factor.sequence_order.
    Returns (factor, type, sequence).
    """
    r = await db.execute(
        select(ConversionFactor, ConversionFactorType, TrialFactorConfiguration)
        .join(TrialFactorConfiguration, TrialFactorConfiguration.conversion_factor_id == ConversionFactor.id)
        .join(ConversionFactorType, ConversionFactor.factor_type_id == ConversionFactorType.id)
        .where(
            TrialFactorConfiguration.trial_id == trial_id,
            TrialFactorConfiguration.enabled.is_(True),
        )
    )
    rows = r.all()
    out: list[tuple[ConversionFactor, ConversionFactorType, int]] = []
    for fac, ftype, cfg in rows:
        seq = cfg.sequence_override if cfg.sequence_override is not None else fac.sequence_order
        out.append((fac, ftype, seq))
    out.sort(key=lambda x: (x[2], x[0].id))
    return out


async def get_exchange_rate(
    db: AsyncSession, from_currency: str, to_currency: str, on_date: Optional[date] = None
) -> Optional[Decimal]:
    if from_currency == to_currency:
        return Decimal("1")
    d = on_date or date.today()
    r = await db.execute(
        select(CurrencyExchangeRate)
        .where(
            CurrencyExchangeRate.from_currency == from_currency,
            CurrencyExchangeRate.to_currency == to_currency,
            CurrencyExchangeRate.effective_date <= d,
        )
        .order_by(CurrencyExchangeRate.effective_date.desc())
        .limit(1)
    )
    row = r.scalar_one_or_none()
    if row:
        return row.rate
    # try inverse
    r2 = await db.execute(
        select(CurrencyExchangeRate)
        .where(
            CurrencyExchangeRate.from_currency == to_currency,
            CurrencyExchangeRate.to_currency == from_currency,
            CurrencyExchangeRate.effective_date <= d,
        )
        .order_by(CurrencyExchangeRate.effective_date.desc())
        .limit(1)
    )
    inv = r2.scalar_one_or_none()
    if inv:
        return Decimal("1") / inv.rate
    return None


async def load_visit_matrix_for_template(
    db: AsyncSession, template_id: UUID
) -> list[BudgetVisitMatrix]:
    r = await db.execute(
        select(BudgetVisitMatrix)
        .join(BudgetLineItem, BudgetVisitMatrix.budget_line_item_id == BudgetLineItem.id)
        .where(BudgetLineItem.budget_template_id == template_id)
    )
    return list(r.scalars().all())


async def sum_milestone_amounts(db: AsyncSession, template_id: UUID) -> Decimal:
    # unit_cost × quantity = milestone line total (guide §3.6); renamed from amount.
    r = await db.execute(
        select(func.coalesce(func.sum(BudgetMilestone.unit_cost * BudgetMilestone.quantity), 0))
        .where(BudgetMilestone.budget_template_id == template_id)
    )
    v = r.scalar_one()
    return Decimal(str(v or 0))
