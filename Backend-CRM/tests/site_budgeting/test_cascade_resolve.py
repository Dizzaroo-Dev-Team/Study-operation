"""Budget line cascade: inherit, exclude, override."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.site_budgeting.db_models import BudgetLineItem, BudgetTemplate, CostElement, ElementCostVersion
from app.modules.site_budgeting.services import budget_service


@pytest.mark.asyncio
async def test_inherit_from_parent(db_session: AsyncSession, seed_study_site):
    trial_id, _ = seed_study_site
    ce = CostElement(code="CASCADE-A", name="Test A")
    db_session.add(ce)
    await db_session.flush()
    db_session.add(
        ElementCostVersion(
            element_id=ce.id,
            version_label="v1",
            base_unit_cost=Decimal("50"),
            reference_currency="USD",
        )
    )
    parent = BudgetTemplate(trial_id=trial_id, name="Trial tpl", target_currency_code="USD", status="draft")
    db_session.add(parent)
    await db_session.flush()
    db_session.add(
        BudgetLineItem(
            budget_template_id=parent.id,
            cost_element_id=ce.id,
            is_excluded=False,
            inherited_from_parent=False,
        )
    )
    child = BudgetTemplate(
        trial_id=trial_id,
        name="Site tpl",
        target_currency_code="USD",
        parent_template_id=parent.id,
        status="draft",
    )
    db_session.add(child)
    await db_session.commit()

    rows = await budget_service.resolve_budget_line_items(db_session, child.id)
    assert len(rows) == 1
    assert rows[0]["cost_element_id"] == str(ce.id)
    assert rows[0]["inherited_from"] is not None


@pytest.mark.asyncio
async def test_child_excluded_skips_parent_line(db_session: AsyncSession, seed_study_site):
    trial_id, _ = seed_study_site
    ce = CostElement(code="CASCADE-B", name="Test B")
    db_session.add(ce)
    await db_session.flush()
    db_session.add(
        ElementCostVersion(
            element_id=ce.id,
            version_label="v1",
            base_unit_cost=Decimal("40"),
            reference_currency="USD",
        )
    )
    parent = BudgetTemplate(trial_id=trial_id, name="Trial tpl 2", target_currency_code="USD", status="draft")
    db_session.add(parent)
    await db_session.flush()
    db_session.add(
        BudgetLineItem(
            budget_template_id=parent.id,
            cost_element_id=ce.id,
            is_excluded=False,
        )
    )
    child = BudgetTemplate(
        trial_id=trial_id,
        name="Site tpl 2",
        target_currency_code="USD",
        parent_template_id=parent.id,
        status="draft",
    )
    db_session.add(child)
    await db_session.flush()
    db_session.add(
        BudgetLineItem(
            budget_template_id=child.id,
            cost_element_id=ce.id,
            is_excluded=True,
        )
    )
    await db_session.commit()

    rows = await budget_service.resolve_budget_line_items(db_session, child.id)
    # New contract (B3 in budget_service.resolve_budget_line_items):
    # excluded rows are emitted with is_excluded=True so the UI can render
    # them strikethrough, rather than silently dropped. The parent's row
    # must NOT appear independently.
    assert len(rows) == 1
    assert rows[0]["cost_element_id"] == str(ce.id)
    assert rows[0]["is_excluded"] is True


@pytest.mark.asyncio
async def test_override_unit_cost_on_child(db_session: AsyncSession, seed_study_site):
    trial_id, _ = seed_study_site
    ce = CostElement(code="CASCADE-C", name="Test C")
    db_session.add(ce)
    await db_session.flush()
    db_session.add(
        ElementCostVersion(
            element_id=ce.id,
            version_label="v1",
            base_unit_cost=Decimal("100"),
            reference_currency="USD",
        )
    )
    parent = BudgetTemplate(trial_id=trial_id, name="Trial tpl 3", target_currency_code="USD", status="draft")
    db_session.add(parent)
    await db_session.flush()
    db_session.add(
        BudgetLineItem(
            budget_template_id=parent.id,
            cost_element_id=ce.id,
            is_excluded=False,
        )
    )
    child = BudgetTemplate(
        trial_id=trial_id,
        name="Site tpl 3",
        target_currency_code="USD",
        parent_template_id=parent.id,
        status="draft",
    )
    db_session.add(child)
    await db_session.flush()
    db_session.add(
        BudgetLineItem(
            budget_template_id=child.id,
            cost_element_id=ce.id,
            is_excluded=False,
            override_unit_cost=Decimal("77"),
            inherited_from_parent=False,
        )
    )
    await db_session.commit()

    rows = await budget_service.resolve_budget_line_items(db_session, child.id)
    assert len(rows) == 1
    assert rows[0]["override_unit_cost"] in ("77", "77.0000")
    assert rows[0]["unit_cost"] in ("77", "77.0000")
