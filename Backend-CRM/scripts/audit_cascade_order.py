"""Compare row order between TRIAL and COUNTRY resolveTemplate output."""
import asyncio
from sqlalchemy import text
from app.db import AsyncSessionLocal
import app.models  # noqa: F401
from app.modules.site_budgeting.db_models import BudgetTemplate
from app.modules.site_budgeting.services import budget_service


async def main() -> None:
    async with AsyncSessionLocal() as db:
        trial_id = (await db.execute(text("SELECT id FROM studies LIMIT 1"))).scalar_one()
        # Reset
        for w in [
            "DELETE FROM budget_visit_matrix WHERE budget_line_item_id IN (SELECT id FROM budget_line_item WHERE budget_template_id IN (SELECT id FROM budget_template WHERE trial_id = :t))",
            "DELETE FROM budget_line_item WHERE budget_template_id IN (SELECT id FROM budget_template WHERE trial_id = :t)",
            "DELETE FROM visit_schedule WHERE trial_id = :t",
            "DELETE FROM trial_factor_configuration WHERE trial_id = :t",
            "DELETE FROM budget_template WHERE trial_id = :t",
        ]:
            await db.execute(text(w), {"t": trial_id})
        await db.commit()

        trial_tpl = BudgetTemplate(trial_id=trial_id, name="x", template_level="TRIAL", target_currency_code="USD")
        db.add(trial_tpl); await db.flush(); await db.commit()
        await budget_service.generate_visit_matrix_from_soa(
            db, template_id=trial_tpl.id, study_id="D0816C00010",
            treatment_duration=24, followup_duration=24, unscheduled_visits=2,
        )
        await db.commit()

        country_tpl = await budget_service.get_or_create_country_template(db, trial_id=trial_id, country_code="BRA")
        await db.commit()

        trial_rows = await budget_service.resolve_budget_line_items(db, trial_tpl.id)
        country_rows = await budget_service.resolve_budget_line_items(db, country_tpl.id)

        print(f"TRIAL    rows: {len(trial_rows)}")
        print(f"COUNTRY  rows: {len(country_rows)}")
        print()
        print(f"{'#':>3}  {'TRIAL':40}  {'COUNTRY':40}  match")
        for i in range(max(len(trial_rows), len(country_rows))):
            tn = trial_rows[i]['name'] if i < len(trial_rows) else '—'
            cn = country_rows[i]['name'] if i < len(country_rows) else '—'
            mark = '✓' if tn == cn else '✗'
            print(f"{i:>3}  {(tn or '')[:40]:40}  {(cn or '')[:40]:40}  {mark}")


if __name__ == "__main__":
    asyncio.run(main())
