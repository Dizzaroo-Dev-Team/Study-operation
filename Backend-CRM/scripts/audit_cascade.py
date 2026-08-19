"""
End-to-end audit of the Study → Country cascade for visit matrix.

Reset DB → import SOA into TRIAL template → get-or-create COUNTRY template →
read /visit-matrix/resolved for COUNTRY → verify it surfaces TRIAL's visits/cells.

  docker exec -w /app backend-crm-backend-1 python -m scripts.audit_cascade
"""
import asyncio
import uuid
from collections import Counter

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
import app.models  # noqa: F401
from app.modules.site_budgeting.db_models import (
    BudgetLineItem,
    BudgetTemplate,
    BudgetVisitMatrix,
    VisitSchedule,
)
from app.modules.site_budgeting.services import budget_service


async def main() -> None:
    async with AsyncSessionLocal() as db:  # type: AsyncSession
        # Pick a trial
        trial_id = (await db.execute(text("SELECT id FROM studies LIMIT 1"))).scalar_one()
        print(f"trial_id = {trial_id}")

        # Reset
        wipes = [
            "DELETE FROM budget_visit_matrix WHERE budget_line_item_id IN (SELECT id FROM budget_line_item WHERE budget_template_id IN (SELECT id FROM budget_template WHERE trial_id = :tid))",
            "DELETE FROM budget_line_item WHERE budget_template_id IN (SELECT id FROM budget_template WHERE trial_id = :tid)",
            "DELETE FROM visit_schedule WHERE trial_id = :tid",
            "DELETE FROM trial_factor_configuration WHERE trial_id = :tid",
            "DELETE FROM budget_template WHERE trial_id = :tid",
        ]
        for w in wipes:
            await db.execute(text(w), {"tid": trial_id})
        await db.commit()
        print("wiped budget data for this trial")

        # Create TRIAL template
        trial_tpl = BudgetTemplate(
            trial_id=trial_id, name="audit-cascade",
            template_level="TRIAL", target_currency_code="USD",
        )
        db.add(trial_tpl)
        await db.flush()
        trial_tpl_id = trial_tpl.id
        await db.commit()
        print(f"TRIAL template id = {trial_tpl_id}")

        # Import SOA at TRIAL level
        sid = "D0816C00010"
        result = await budget_service.generate_visit_matrix_from_soa(
            db, template_id=trial_tpl_id, study_id=sid,
            treatment_duration=24, followup_duration=24, unscheduled_visits=2,
        )
        await db.commit()
        print(f"\nIMPORT result: visits={result['visits_inserted']}, lines={result['line_items_inserted']}, cells={result['matrix_cells_inserted']}")

        # Verify TRIAL counts in DB
        n_visits = (await db.execute(text("SELECT COUNT(*) FROM visit_schedule WHERE budget_template_id = :tid"), {"tid": trial_tpl_id})).scalar_one()
        n_lines = (await db.execute(text("SELECT COUNT(*) FROM budget_line_item WHERE budget_template_id = :tid"), {"tid": trial_tpl_id})).scalar_one()
        n_cells = (await db.execute(text("SELECT COUNT(*) FROM budget_visit_matrix m JOIN budget_line_item li ON li.id = m.budget_line_item_id WHERE li.budget_template_id = :tid"), {"tid": trial_tpl_id})).scalar_one()
        print(f"TRIAL DB: visits={n_visits}, lines={n_lines}, cells={n_cells}")

        # Create COUNTRY template via cascade-aware helper
        country_tpl = await budget_service.get_or_create_country_template(
            db, trial_id=trial_id, country_code="BRA",
        )
        await db.commit()
        country_tpl_id = country_tpl.id
        print(f"\nCOUNTRY template id = {country_tpl_id}, parent = {country_tpl.parent_template_id}")

        # Country template should have NO direct visits / lines
        c_visits = (await db.execute(text("SELECT COUNT(*) FROM visit_schedule WHERE budget_template_id = :tid"), {"tid": country_tpl_id})).scalar_one()
        c_lines = (await db.execute(text("SELECT COUNT(*) FROM budget_line_item WHERE budget_template_id = :tid"), {"tid": country_tpl_id})).scalar_one()
        c_cells = (await db.execute(text("SELECT COUNT(*) FROM budget_visit_matrix m JOIN budget_line_item li ON li.id = m.budget_line_item_id WHERE li.budget_template_id = :tid"), {"tid": country_tpl_id})).scalar_one()
        print(f"COUNTRY DB direct: visits={c_visits}, lines={c_lines}, cells={c_cells}  (expect 0/0/0 — cascades from parent)")

        # === The key cascade calls — what frontend hits ===
        print("\n=== /visit-matrix/resolved on COUNTRY ===")
        # We re-implement what the route does: query visits direct, cascade if 0.
        # Then call resolve_visit_matrix for cells.
        vs_direct = (await db.execute(
            select(VisitSchedule).where(VisitSchedule.budget_template_id == country_tpl_id)
            .order_by(VisitSchedule.visit_order, VisitSchedule.id)
        )).scalars().all()

        if not vs_direct:
            cursor = country_tpl
            seen = set()
            while cursor.parent_template_id and cursor.id not in seen:
                seen.add(cursor.id)
                cursor = await db.get(BudgetTemplate, cursor.parent_template_id)
                if cursor is None:
                    break
                vs_direct = (await db.execute(
                    select(VisitSchedule).where(VisitSchedule.budget_template_id == cursor.id)
                    .order_by(VisitSchedule.visit_order, VisitSchedule.id)
                )).scalars().all()
                if vs_direct:
                    print(f"   visits cascade hit on parent {cursor.id} (level={cursor.template_level})")
                    break

        print(f"   visits returned: {len(vs_direct)}")

        cells = await budget_service.resolve_visit_matrix(db, country_tpl_id)
        print(f"   cells returned : {len(cells)}")
        if cells:
            sample = cells[:3]
            for c in sample:
                print(f"   sample cell    : visit={c.get('visit_code')} li={c['budget_line_item_id'][:8]}.. units={c['units']} inherited={c.get('inherited_from_parent')}")

        # And resolveTemplate
        resolved = await budget_service.resolve_budget_line_items(db, country_tpl_id)
        rows_with_li = sum(1 for r in resolved if r.get("line_item_id"))
        print("\n=== resolveTemplate on COUNTRY ===")
        print(f"   {len(resolved)} rows total, {rows_with_li} with line_item_id (frontend filters by line_item_id)")

        # Cross-check: cell.budget_line_item_id should be in the resolved rows' line_item_ids
        resolved_li_ids = {r.get("line_item_id") for r in resolved if r.get("line_item_id")}
        cells_li_ids = {c["budget_line_item_id"] for c in cells}
        orphan_cells = cells_li_ids - resolved_li_ids
        if orphan_cells:
            print(f"   ** {len(orphan_cells)} cells reference line_items NOT in resolveTemplate output — cells will appear in 'wrong' rows or be invisible **")
            for li in list(orphan_cells)[:3]:
                print(f"     orphan: {li}")

        # Section breakdown to see if grouping works at country
        sec_counter = Counter(r.get("category") or "(none)" for r in resolved)
        print(f"   Sections: {dict(sec_counter)}")


if __name__ == "__main__":
    asyncio.run(main())
