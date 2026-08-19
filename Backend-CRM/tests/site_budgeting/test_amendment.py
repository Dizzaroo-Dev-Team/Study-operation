"""Protocol amendment: flag overridden child lines without overwriting values."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.site_budgeting.db_models import BudgetLineItem, BudgetTemplate, CostElement, ElementCostVersion
from app.modules.site_budgeting.services import budget_service


@pytest.mark.asyncio
async def test_propagate_marks_needs_review_on_overridden_child(db_session: AsyncSession, seed_study_site):
    trial_id, _ = seed_study_site
    ce = CostElement(code="AMEND-1", name="Elem")
    db_session.add(ce)
    await db_session.flush()
    db_session.add(
        ElementCostVersion(
            element_id=ce.id,
            version_label="v1",
            base_unit_cost=Decimal("200"),
            reference_currency="USD",
        )
    )
    trial_tpl = BudgetTemplate(trial_id=trial_id, name="Trial master", target_currency_code="USD", status="draft")
    db_session.add(trial_tpl)
    await db_session.flush()
    db_session.add(
        BudgetLineItem(
            budget_template_id=trial_tpl.id,
            cost_element_id=ce.id,
            is_excluded=False,
        )
    )
    child = BudgetTemplate(
        trial_id=trial_id,
        name="Country",
        target_currency_code="USD",
        parent_template_id=trial_tpl.id,
        status="draft",
    )
    db_session.add(child)
    await db_session.flush()
    child_li = BudgetLineItem(
        budget_template_id=child.id,
        cost_element_id=ce.id,
        is_excluded=False,
        override_unit_cost=Decimal("250"),
        needs_review=False,
    )
    db_session.add(child_li)
    await db_session.commit()

    n = await budget_service.propagate_trial_amendment_to_children(db_session, trial_tpl.id, [ce.id])
    assert n == 1
    await db_session.refresh(child_li)
    assert child_li.needs_review is True
    assert child_li.override_unit_cost == Decimal("250")


@pytest.mark.asyncio
async def test_propagate_skips_lines_without_override(db_session: AsyncSession, seed_study_site):
    trial_id, _ = seed_study_site
    ce = CostElement(code="AMEND-2", name="Elem2")
    db_session.add(ce)
    await db_session.flush()
    db_session.add(
        ElementCostVersion(
            element_id=ce.id,
            version_label="v1",
            base_unit_cost=Decimal("10"),
            reference_currency="USD",
        )
    )
    trial_tpl = BudgetTemplate(trial_id=trial_id, name="Trial master 2", target_currency_code="USD", status="draft")
    db_session.add(trial_tpl)
    await db_session.flush()
    db_session.add(BudgetLineItem(budget_template_id=trial_tpl.id, cost_element_id=ce.id, is_excluded=False))
    child = BudgetTemplate(
        trial_id=trial_id,
        name="Country 2",
        target_currency_code="USD",
        parent_template_id=trial_tpl.id,
        status="draft",
    )
    db_session.add(child)
    await db_session.flush()
    child_li = BudgetLineItem(budget_template_id=child.id, cost_element_id=ce.id, is_excluded=False, needs_review=False)
    db_session.add(child_li)
    await db_session.commit()

    n = await budget_service.propagate_trial_amendment_to_children(db_session, trial_tpl.id, [ce.id])
    assert n == 0
    await db_session.refresh(child_li)
    assert child_li.needs_review is False
