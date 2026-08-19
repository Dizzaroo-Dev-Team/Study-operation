"""compute_final_unit_cost: multiplicative vs additive (SQLite)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.site_budgeting.db_models import (
    ConversionFactor,
    ConversionFactorType,
    CostElement,
    ElementCostVersion,
    FactorMode,
    TrialFactorConfiguration,
)
from app.modules.site_budgeting.services.factor_service import compute_final_unit_cost
from app.modules.site_budgeting.utils.request_cache import RequestMemo


@pytest.mark.asyncio
async def test_multiplicative_stack(db_session: AsyncSession, seed_study_site):
    trial_id, _ = seed_study_site
    el = CostElement(code="E-MUL", name="El")
    db_session.add(el)
    await db_session.flush()
    db_session.add(
        ElementCostVersion(
            element_id=el.id,
            version_label="v1",
            base_unit_cost=Decimal("100"),
            reference_currency="USD",
        )
    )
    ft = ConversionFactorType(code="COUNTRY_X", name="c", mode=FactorMode.MULTIPLICATIVE.value)
    db_session.add(ft)
    await db_session.flush()
    fac = ConversionFactor(
        factor_type_id=ft.id,
        trial_id=trial_id,
        sequence_order=0,
        value=Decimal("1.5"),
    )
    db_session.add(fac)
    await db_session.flush()
    db_session.add(
        TrialFactorConfiguration(trial_id=trial_id, factor_type_id=ft.id, is_active=True, application_sequence=0)
    )
    await db_session.commit()

    memo = RequestMemo()
    res = await compute_final_unit_cost(
        db_session,
        element_id=el.id,
        trial_id=trial_id,
        country_code=None,
        site_id=None,
        target_currency="USD",
        memo=memo,
        base_amount=Decimal("100"),
        base_currency="USD",
    )
    assert res.converted_amount == Decimal("150")


@pytest.mark.asyncio
async def test_additive_adds_in_running_currency(db_session: AsyncSession, seed_study_site):
    trial_id, _ = seed_study_site
    el = CostElement(code="E-ADD", name="El2")
    db_session.add(el)
    await db_session.flush()
    db_session.add(
        ElementCostVersion(
            element_id=el.id,
            version_label="v1",
            base_unit_cost=Decimal("80"),
            reference_currency="USD",
        )
    )
    ft = ConversionFactorType(code="FEE", name="fee", mode=FactorMode.ADDITIVE.value)
    db_session.add(ft)
    await db_session.flush()
    fac = ConversionFactor(
        factor_type_id=ft.id,
        trial_id=trial_id,
        sequence_order=0,
        value=Decimal("20"),
        currency_code="USD",
    )
    db_session.add(fac)
    await db_session.flush()
    db_session.add(
        TrialFactorConfiguration(trial_id=trial_id, factor_type_id=ft.id, is_active=True, application_sequence=0)
    )
    await db_session.commit()

    res = await compute_final_unit_cost(
        db_session,
        element_id=el.id,
        trial_id=trial_id,
        country_code=None,
        site_id=None,
        target_currency="USD",
        memo=RequestMemo(),
        base_amount=Decimal("80"),
        base_currency="USD",
    )
    assert res.converted_amount == Decimal("100")


@pytest.mark.asyncio
async def test_compute_final_unit_cost_memo_returns_same_instance(db_session: AsyncSession, seed_study_site):
    trial_id, _ = seed_study_site
    el = CostElement(code="E-MEMO", name="El3")
    db_session.add(el)
    await db_session.flush()
    db_session.add(
        ElementCostVersion(
            element_id=el.id,
            version_label="v1",
            base_unit_cost=Decimal("10"),
            reference_currency="USD",
        )
    )
    ft = ConversionFactorType(code="MUL2", name="m", mode=FactorMode.MULTIPLICATIVE.value)
    db_session.add(ft)
    await db_session.flush()
    fac = ConversionFactor(factor_type_id=ft.id, trial_id=trial_id, sequence_order=0, value=Decimal("2"))
    db_session.add(fac)
    await db_session.flush()
    db_session.add(
        TrialFactorConfiguration(trial_id=trial_id, factor_type_id=ft.id, is_active=True, application_sequence=0)
    )
    await db_session.commit()

    memo = RequestMemo()
    r1 = await compute_final_unit_cost(
        db_session,
        element_id=el.id,
        trial_id=trial_id,
        country_code=None,
        site_id=None,
        target_currency="USD",
        memo=memo,
        base_amount=Decimal("10"),
        base_currency="USD",
    )
    r2 = await compute_final_unit_cost(
        db_session,
        element_id=el.id,
        trial_id=trial_id,
        country_code=None,
        site_id=None,
        target_currency="USD",
        memo=memo,
        base_amount=Decimal("10"),
        base_currency="USD",
    )
    assert r1 is r2
    assert r1.converted_amount == Decimal("20")
