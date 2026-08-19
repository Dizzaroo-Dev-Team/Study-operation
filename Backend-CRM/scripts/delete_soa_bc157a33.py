"""One-shot: delete the orphan SOA-BC157A33 cost_element. Safe-checks FK refs first."""
from __future__ import annotations
import asyncio
from sqlalchemy import text
from app.db import AsyncSessionLocal

TARGET_CODE = "SOA-BC157A33"


async def main() -> None:
    async with AsyncSessionLocal() as s:
        eid = (await s.execute(text("SELECT id FROM cost_element WHERE code=:c"), {"c": TARGET_CODE})).scalar_one_or_none()
        print(f"element_id = {eid}")
        if not eid:
            print("Already gone or never existed. Nothing to do.")
            return

        n_lines = (await s.execute(text("SELECT COUNT(*) FROM budget_line_item WHERE cost_element_id = :id"), {"id": eid})).scalar_one()
        n_ms = (await s.execute(text("SELECT COUNT(*) FROM budget_milestone WHERE element_id = :id"), {"id": eid})).scalar_one()
        n_v = (await s.execute(text("SELECT COUNT(*) FROM element_cost_version WHERE element_id = :id"), {"id": eid})).scalar_one()
        n_b = (await s.execute(
            text("SELECT COUNT(*) FROM element_bundle_composition WHERE bundle_element_id = :id OR child_element_id = :id"),
            {"id": eid},
        )).scalar_one()
        n_f = (await s.execute(text("SELECT COUNT(*) FROM conversion_factor WHERE scope_element_id = :id"), {"id": eid})).scalar_one()
        print(f"refs: budget_line_item={n_lines} budget_milestone={n_ms} cost_versions={n_v} bundle_comps={n_b} conv_factors={n_f}")

        if n_lines > 0:
            print(f"ABORT: {n_lines} budget_line_item rows reference this element (FK RESTRICT). Clear those first.")
            return

        # cost_version + bundle_comp are CASCADE on cost_element delete.
        # budget_milestone.element_id is SET NULL.
        # conversion_factor.scope_element_id is SET NULL.
        await s.execute(text("DELETE FROM cost_element WHERE id = :id"), {"id": eid})
        await s.commit()
        print(f"Deleted cost_element {TARGET_CODE} ({eid}). Cascaded {n_v} cost_version + {n_b} bundle_comp rows; nulled {n_ms} milestone + {n_f} factor refs.")


if __name__ == "__main__":
    asyncio.run(main())
