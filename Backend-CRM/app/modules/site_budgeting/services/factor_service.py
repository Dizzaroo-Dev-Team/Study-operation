"""Conversion factor engine: resolve_factor priority + per-type application; currency after factors."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.site_budgeting.db_models import ConversionFactor, ConversionFactorType, CostElement, FactorMode, TrialFactorConfiguration
# NOTE: FactorMode.PASS_THROUGH was removed from the enum; handled via cost_type_pass_through param.
from app.modules.site_budgeting.repositories import budgeting_repository as repo
from app.modules.site_budgeting.utils.request_cache import RequestMemo, cache_key


@dataclass
class FactorComputationResult:
    base_amount: Decimal
    base_currency: str
    after_factors_amount: Decimal
    after_factors_currency: str
    converted_amount: Decimal
    target_currency: str
    applied_steps: list[dict]


@dataclass
class FactorTrialContext:
    """Per-request preload: factor types in order + all candidate rows for the trial (and globals)."""

    type_order: list[UUID]
    types_by_id: dict[UUID, ConversionFactorType]
    candidates: list[ConversionFactor]


def _mode(s: str) -> str:
    return (s or "").upper()


def _norm_cc(code: Optional[str]) -> Optional[str]:
    return code.upper().strip() if code else None


def resolve_factor_match_rank(
    fac: ConversionFactor,
    *,
    element_id: UUID,
    element_category: Optional[str],
    country_code: Optional[str],
    site_id: Optional[UUID],
) -> int:
    """
    Return 0 = no match, 1–8 = specificity (8 = most specific, wins).
    8 Element+Site, 7 Element+Country, 6 Category+Site, 5 Category+Country,
    4 Element-only (no geo), 3 Global+Site, 2 Global+Country, 1 Global default.
    """
    cc = _norm_cc(country_code)
    fc_country = _norm_cc(fac.country_code)

    el = fac.scope_element_id
    scat = (fac.scope_category or "").strip() or None
    ec = (element_category or "").strip() or None

    if el is not None:
        if el != element_id:
            return 0
        if fac.site_id is not None and site_id is not None and fac.site_id == site_id:
            return 8
        if fac.country_code is not None and cc is not None and fc_country == cc and fac.site_id is None:
            return 7
        if fac.site_id is None and fac.country_code is None:
            return 4
        return 0

    if scat is not None:
        if ec is None or scat != ec:
            return 0
        if fac.site_id is not None and site_id is not None and fac.site_id == site_id:
            return 6
        if fac.country_code is not None and cc is not None and fc_country == cc and fac.site_id is None:
            return 5
        return 0

    if fac.site_id is not None:
        if site_id is not None and fac.site_id == site_id:
            if fac.country_code is None or (cc is not None and fc_country == cc):
                return 3
        return 0

    if fac.country_code is not None:
        if cc is not None and fc_country == cc and fac.site_id is None:
            return 2
        return 0

    if fac.country_code is None and fac.site_id is None:
        return 1

    return 0


def pick_best_factor(
    candidates: list[ConversionFactor],
    *,
    factor_type_id: UUID,
    trial_id: UUID,
    element_id: UUID,
    element_category: Optional[str],
    country_code: Optional[str],
    site_id: Optional[UUID],
) -> Optional[ConversionFactor]:
    best: Optional[ConversionFactor] = None
    best_rank = 0
    for fac in candidates:
        if fac.factor_type_id != factor_type_id:
            continue
        if fac.trial_id is not None and fac.trial_id != trial_id:
            continue
        rank = resolve_factor_match_rank(
            fac,
            element_id=element_id,
            element_category=element_category,
            country_code=country_code,
            site_id=site_id,
        )
        if rank == 0:
            continue
        if best is None or rank > best_rank or (rank == best_rank and str(fac.id) < str(best.id)):
            best = fac
            best_rank = rank
    return best


async def _ordered_factor_types_for_trial(db: AsyncSession, trial_id: UUID) -> list[UUID]:
    """
    Return factor type IDs in application_sequence order for this trial.

    Post-refactor: TrialFactorConfiguration directly references factor_type_id
    (guide §3.2). The old join through conversion_factor to extract the type has
    been replaced with a direct query.
    """
    r = await db.execute(
        select(TrialFactorConfiguration.factor_type_id, TrialFactorConfiguration.application_sequence)
        .where(
            TrialFactorConfiguration.trial_id == trial_id,
            TrialFactorConfiguration.is_active.is_(True),
        )
        .order_by(TrialFactorConfiguration.application_sequence, TrialFactorConfiguration.factor_type_id)
    )
    rows = r.all()
    # De-duplicate: if a type appears more than once, keep the lowest sequence
    seen: dict[UUID, int] = {}
    for ftype_id, seq in rows:
        if ftype_id not in seen or seq < seen[ftype_id]:
            seen[ftype_id] = seq
    return [fid for fid, _ in sorted(seen.items(), key=lambda x: (x[1], str(x[0])))]


async def ensure_factor_trial_context(db: AsyncSession, trial_id: UUID, memo: RequestMemo) -> FactorTrialContext:
    k = cache_key("ftctx", trial_id)
    if memo.has(k):
        return memo.get(k)  # type: ignore[return-value]
    type_order = await _ordered_factor_types_for_trial(db, trial_id)
    candidates = await repo.list_conversion_factors_rows(db, trial_id)
    type_ids = list({*type_order, *(c.factor_type_id for c in candidates)})
    types_by_id = await repo.bulk_conversion_factor_types(db, type_ids)
    ctx = FactorTrialContext(type_order=type_order, types_by_id=types_by_id, candidates=candidates)
    memo.set(k, ctx)
    return ctx


async def resolve_factor(
    db: AsyncSession,
    *,
    factor_type_id: UUID,
    trial_id: UUID,
    element_id: UUID,
    country_code: Optional[str],
    site_id: Optional[UUID],
    memo: Optional[RequestMemo] = None,
    element_category: Optional[str] = None,
) -> Optional[ConversionFactor]:
    """
    Pick the single best-matching conversion_factor row for this factor type and context.
    Uses one preload per trial per request (memo) and caches each (trial, geo, element, factor_type) result.
    """
    m = memo if memo is not None else RequestMemo()
    rf_key = cache_key("rf", trial_id, country_code or "", site_id or "", element_id, factor_type_id)
    if m.has(rf_key):
        return m.get(rf_key)  # type: ignore[return-value]

    ctx = await ensure_factor_trial_context(db, trial_id, m)
    cat = element_category
    if cat is None:
        ce = await db.get(CostElement, element_id)
        cat = (ce.category.name if ce.category else None) if ce else None

    fac = pick_best_factor(
        ctx.candidates,
        factor_type_id=factor_type_id,
        trial_id=trial_id,
        element_id=element_id,
        element_category=cat,
        country_code=country_code,
        site_id=site_id,
    )
    m.set(rf_key, fac)
    return fac


async def _exchange_rate_cached(db: AsyncSession, memo: RequestMemo, frm: str, to: str) -> Decimal:
    fk = cache_key("fx", frm, to)
    if memo.has(fk):
        return memo.get(fk)  # type: ignore[return-value]
    rate = await repo.get_exchange_rate(db, frm, to)
    if rate is None:
        raise ValueError(f"Missing FX rate {frm}->{to}")
    memo.set(fk, rate)
    return rate


async def compute_final_unit_cost(
    db: AsyncSession,
    *,
    element_id: UUID,
    trial_id: UUID,
    country_code: Optional[str],
    site_id: Optional[UUID],
    target_currency: str,
    memo: Optional[RequestMemo] = None,
    base_amount: Optional[Decimal] = None,
    base_currency: Optional[str] = None,
    cost_type_pass_through: bool = False,
    element_category: Optional[str] = None,
) -> FactorComputationResult:
    """
    For each active factor *type* (in order), resolve_factor → apply one row (MULTIPLICATIVE / ADDITIVE / PASS_THROUGH).
    Currency conversion applied once at end. Request-scoped memo caches factor preload, FX pairs, and full result.
    """
    ck = cache_key(
        "fc",
        element_id,
        trial_id,
        country_code or "",
        site_id or "",
        target_currency,
        str(base_amount) if base_amount is not None else "",
        base_currency or "",
        str(cost_type_pass_through),
        element_category or "",
    )
    work_memo = memo if memo is not None else RequestMemo()
    if work_memo.has(ck):
        return work_memo.get(ck)  # type: ignore[return-value]

    if cost_type_pass_through:
        if base_amount is not None and base_currency is not None:
            amt, cur = base_amount, base_currency
        else:
            vc = await repo.get_latest_cost_version(db, element_id)
            if not vc:
                raise ValueError("No cost version for element")
            amt, cur = vc.base_unit_cost, vc.reference_currency
        converted = amt
        if cur != target_currency:
            converted = amt * await _exchange_rate_cached(db, work_memo, cur, target_currency)
        result = FactorComputationResult(
            base_amount=Decimal(amt),
            base_currency=cur,
            after_factors_amount=Decimal(amt),
            after_factors_currency=cur,
            converted_amount=converted,
            target_currency=target_currency,
            applied_steps=[{"step": "PASS_THROUGH_ELEMENT", "effect": "factors_skipped"}],
        )
        work_memo.set(ck, result)
        return result

    if base_amount is None or base_currency is None:
        vc = await repo.get_latest_cost_version(db, element_id)
        if not vc:
            raise ValueError("No cost version for element")
        amt = vc.base_unit_cost
        cur = vc.reference_currency
    else:
        amt = base_amount
        cur = base_currency

    steps: list[dict] = []
    running = Decimal(amt)
    running_currency = cur

    ec = element_category
    if ec is None:
        ce_row = await db.get(CostElement, element_id)
        ec = (ce_row.category.name if ce_row.category else None) if ce_row else None

    rk = lambda f: resolve_factor_match_rank(
        f, element_id=element_id, element_category=ec, country_code=country_code, site_id=site_id
    )

    ctx = await ensure_factor_trial_context(db, trial_id, work_memo)
    for ftype_id in ctx.type_order:
        # Scope-gate: a COUNTRY factor type only applies when resolving at/below country level
        # (country_code is set); SITE factor type only applies when a site is set. This prevents
        # a global SITE factor (site_id=NULL) from leaking up into COUNTRY-level calculations.
        ftype_for_gate = ctx.types_by_id.get(ftype_id)
        gate_code = (ftype_for_gate.code or "").upper() if ftype_for_gate else ""
        if gate_code == "SITE" and site_id is None:
            steps.append({"factor_type_id": str(ftype_id), "skipped": True, "reason": "no_site_context"})
            continue
        if gate_code == "COUNTRY" and country_code is None:
            steps.append({"factor_type_id": str(ftype_id), "skipped": True, "reason": "no_country_context"})
            continue

        fac = await resolve_factor(
            db,
            factor_type_id=ftype_id,
            trial_id=trial_id,
            element_id=element_id,
            country_code=country_code,
            site_id=site_id,
            memo=work_memo,
            element_category=ec,
        )
        if fac is None:
            steps.append({"factor_type_id": str(ftype_id), "skipped": True, "reason": "no_matching_factor"})
            continue

        ftype = ctx.types_by_id.get(fac.factor_type_id)
        if not ftype:
            continue

        mode = _mode(ftype.mode)
        if mode == "PASS_THROUGH":
            steps.append({"factor_id": str(fac.id), "factor_type_id": str(ftype_id), "mode": "PASS_THROUGH", "effect": "none"})
            continue
        if mode == _mode(FactorMode.MULTIPLICATIVE.value):
            before = running
            running = running * fac.value
            steps.append(
                {
                    "factor_id": str(fac.id),
                    "factor_type_id": str(ftype_id),
                    "rank": rk(fac),
                    "mode": "MULTIPLICATIVE",
                    "value": str(fac.value),
                    "before": str(before),
                    "after": str(running),
                }
            )
            continue
        if mode == _mode(FactorMode.ADDITIVE.value):
            add_val = fac.value
            add_cur = fac.currency_code or running_currency
            if add_cur != running_currency:
                rate = await _exchange_rate_cached(db, work_memo, add_cur, running_currency)
                add_val = add_val * rate
            before = running
            running = running + add_val
            steps.append(
                {
                    "factor_id": str(fac.id),
                    "factor_type_id": str(ftype_id),
                    "rank": rk(fac),
                    "mode": "ADDITIVE",
                    "value": str(fac.value),
                    "before": str(before),
                    "after": str(running),
                }
            )
            continue

        steps.append({"factor_id": str(fac.id), "factor_type_id": str(ftype_id), "mode": mode, "effect": "unknown_unchanged"})

    converted = running
    if running_currency != target_currency:
        rate = await _exchange_rate_cached(db, work_memo, running_currency, target_currency)
        converted = running * rate
        steps.append(
            {
                "step": "currency_conversion",
                "from": running_currency,
                "to": target_currency,
                "rate": str(rate),
            }
        )

    result = FactorComputationResult(
        base_amount=Decimal(amt),
        base_currency=cur,
        after_factors_amount=running,
        after_factors_currency=running_currency,
        converted_amount=converted,
        target_currency=target_currency,
        applied_steps=steps,
    )
    work_memo.set(ck, result)
    return result
