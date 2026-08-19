"""
Clear all budgeting TRANSACTIONAL data for fresh testing.

Preserves master/library data:
  - cost_element, element_cost_version, element_category, element_bundle_composition
  - conversion_factor_type, milestone_library_item

Deletes transactional data (ORDER matters for FK constraints):
  - site_budgeting_audit_log
  - budget_visit_matrix
  - budget_milestone
  - budget_note
  - budget_line_item
  - visit_schedule
  - budget_template
  - conversion_factor
  - trial_factor_configuration

Run from Backend-CRM directory:
    python -m scripts.maintenance.clear_budgeting_data
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

# add project root to path
sys.path.insert(0, ".")

from app.db import AsyncSessionLocal

TABLES_TO_CLEAR = [
    # audit first (no FK deps pointing to it)
    "site_budgeting_audit_log",
    # visit matrix before line items and visits
    "budget_visit_matrix",
    # milestones, notes, line items, personnel before template
    "budget_milestone",
    "budget_note",
    "budget_personnel_role",
    "budget_line_item",
    "visit_schedule",
    # template last (parent of above)
    "budget_template",
    # factors
    "conversion_factor",
    "trial_factor_configuration",
]


async def run() -> None:
    print("=== clear_budgeting_data ===")
    print("Preserves: cost_element, element_cost_version, conversion_factor_type, milestone_library_item")
    print("Deletes:   templates, line items, visits, milestones, notes, factors, audit log\n")

    async with AsyncSessionLocal() as session:
        for table in TABLES_TO_CLEAR:
            result = await session.execute(text(f"DELETE FROM {table}"))
            print(f"[DELETE] {table}: {result.rowcount} rows removed")
        await session.commit()

    print("\nDone. Master data intact. Ready for fresh test.")


if __name__ == "__main__":
    asyncio.run(run())
