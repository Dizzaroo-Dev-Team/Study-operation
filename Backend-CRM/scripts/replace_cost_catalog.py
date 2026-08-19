"""
One-shot script to wipe the cost-element catalog and replace it with the
oncology-focused master list (~62 elements across 16 categories).

Master data lives in app.modules.site_budgeting.cost_master_data — keep that
single source of truth instead of editing this script directly.

Run:
  docker exec backend-crm-backend-1 python -m scripts.replace_cost_catalog

Safe to re-run: it deletes existing elements/categories before re-inserting.
Foreign keys handled:
  - element_cost_version → cost_element     (CASCADE on delete)
  - element_bundle_composition              (CASCADE)
  - conversion_factor.scope_element_id      (SET NULL — fine)
  - budget_milestone.element_id             (SET NULL — fine)
  - budget_line_item.cost_element_id        (must be empty before run; clear DB first)
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.modules.site_budgeting.cost_master_data import (
    CATEGORIES,
    ELEMENTS,
    VERSION_LABEL,
    build_description,
    derive_cost_type,
)
from app.modules.site_budgeting.db_models import (
    CostElement,
    ElementCategory,
    ElementCostVersion,
)


async def run() -> None:
    print(f"Replacing cost-element catalog: {len(ELEMENTS)} elements across {len(CATEGORIES)} categories")
    today = date.today()

    async with AsyncSessionLocal() as session:  # type: AsyncSession
        # Pre-flight: any budget_line_item rows still pointing at cost_element will block deletes.
        n_lines = (await session.execute(text("SELECT COUNT(*) FROM budget_line_item"))).scalar_one()
        if n_lines and n_lines > 0:
            raise SystemExit(
                f"Aborting: {n_lines} rows in budget_line_item still reference cost_element. "
                f"Clear budget tables first (scripts/maintenance/clear_budgeting_data.py)."
            )

        # Wipe in dependency order. element_cost_version cascades from cost_element
        # but we delete it explicitly anyway so progress is visible.
        await session.execute(delete(ElementCostVersion))
        await session.execute(delete(CostElement))
        await session.execute(delete(ElementCategory))
        await session.flush()

        # Insert categories (top-level, no parent)
        cat_id_by_name: dict[str, uuid.UUID] = {}
        for sort_order, cname in enumerate(CATEGORIES, start=10):
            cid = uuid.uuid4()
            session.add(ElementCategory(id=cid, name=cname, sort_order=sort_order))
            cat_id_by_name[cname] = cid

        await session.flush()

        # Insert elements + their initial cost version
        inserted = 0
        for code, name, category, subcategory, payment_type, user_cost_type, unit, base_amount, pass_thru in ELEMENTS:
            if category not in cat_id_by_name:
                raise SystemExit(f"Unknown category {category!r} for {code}")
            eid = uuid.uuid4()
            session.add(
                CostElement(
                    id=eid,
                    code=code,
                    name=name,
                    description=build_description(subcategory, unit, user_cost_type, pass_thru),
                    unit_of_measure=payment_type,
                    category_id=cat_id_by_name[category],
                    element_type="ATOMIC",
                    cost_type=derive_cost_type(user_cost_type, payment_type, pass_thru),
                    is_active=True,
                )
            )
            session.add(
                ElementCostVersion(
                    id=uuid.uuid4(),
                    element_id=eid,
                    version_label=VERSION_LABEL,
                    base_unit_cost=base_amount,
                    reference_currency="USD",
                    effective_from=today,
                    effective_to=None,
                    source="oncology_master_2026",
                )
            )
            inserted += 1

        await session.commit()
        print(f"Inserted {inserted} cost elements + versions across {len(cat_id_by_name)} categories.")


if __name__ == "__main__":
    asyncio.run(run())
