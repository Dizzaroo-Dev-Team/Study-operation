"""
End-to-end import audit: import a real SOA into a fresh TRIAL template and verify
every activity ends up as a line item + every (activity × visit) ends up as a cell,
both in raw DB rows AND in the resolveTemplate response that the frontend consumes.

Run: docker exec -w /app backend-crm-backend-1 python -m scripts.audit_full_import
"""
import asyncio
import uuid
from collections import Counter

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
import app.models  # noqa: F401  ensure Sites + Studies tables are in the SA metadata registry
from app.modules.site_budgeting.db_models import (
    BudgetLineItem,
    BudgetTemplate,
    BudgetVisitMatrix,
    CostElement,
    VisitSchedule,
)
from app.modules.site_budgeting.services import mongo_service
from app.modules.site_budgeting.services import budget_service
from app.modules.site_budgeting.services.ai_budget_service import normalize_soa


async def audit_one(db: AsyncSession, sid: str, trial_id: uuid.UUID) -> None:
    print("=" * 76)
    print(f"=== {sid} ===")

    # Drop any prior budget rows for this trial first.
    statements = [
        "DELETE FROM budget_visit_matrix WHERE budget_line_item_id IN (SELECT id FROM budget_line_item WHERE budget_template_id IN (SELECT id FROM budget_template WHERE trial_id = :tid))",
        "DELETE FROM budget_line_item WHERE budget_template_id IN (SELECT id FROM budget_template WHERE trial_id = :tid)",
        "DELETE FROM visit_schedule WHERE trial_id = :tid",
        "DELETE FROM budget_template WHERE trial_id = :tid",
    ]
    for s in statements:
        await db.execute(text(s), {"tid": trial_id})
    await db.commit()

    # Create fresh trial template
    tmpl = BudgetTemplate(
        trial_id=trial_id, name=f"audit-{sid}",
        template_level="TRIAL", target_currency_code="USD",
    )
    db.add(tmpl)
    await db.flush()
    tmpl_id = tmpl.id
    await db.commit()

    # Expected from raw SOA
    doc = await mongo_service.fetch_soa(sid)
    n = normalize_soa(doc)
    expected_acts = len(n["activities"])
    expected_visits = len(n["visits"])
    expected_cells = sum(
        max(len(a["visit_indices"]), 1) for a in n["activities"]
    )
    # ^ activities with empty visit_indices fall back to all visits — that's
    #   max(len, 1) here only because empty falls back to ALL visits in importer.
    expected_cells_fallback = sum(
        len(a["visit_indices"]) if a["visit_indices"] else expected_visits
        for a in n["activities"]
    )

    print(f"  Raw normalize    : {expected_acts} activities, {expected_visits} visits")
    print(f"  Expected lines   : {expected_acts}")
    print(f"  Expected cells   : {expected_cells_fallback} (with empty-visits fallback to all)")

    # Run importer
    try:
        result = await budget_service.generate_visit_matrix_from_soa(
            db,
            template_id=tmpl_id,
            study_id=sid,
            treatment_duration=0,
            followup_duration=0,
            unscheduled_visits=0,
        )
        await db.commit()
    except Exception as e:
        print(f"  ** IMPORT CRASHED: {e}")
        await db.rollback()
        return

    print(f"  Importer reported: visits={result['visits_inserted']}, "
          f"lines={result['line_items_inserted']}, "
          f"cells={result['matrix_cells_inserted']}, "
          f"skipped={result.get('skipped', 0)}")

    # Count actual DB state
    db_lines = (await db.execute(
        select(BudgetLineItem).where(BudgetLineItem.budget_template_id == tmpl_id)
    )).scalars().all()
    db_visits = (await db.execute(
        select(VisitSchedule).where(VisitSchedule.budget_template_id == tmpl_id)
    )).scalars().all()
    db_cells_count = (await db.execute(
        text("SELECT COUNT(*) FROM budget_visit_matrix m JOIN budget_line_item li ON li.id = m.budget_line_item_id WHERE li.budget_template_id = :tid"),
        {"tid": tmpl_id},
    )).scalar_one()

    print(f"  DB state         : {len(db_lines)} lines, {len(db_visits)} visits, {db_cells_count} cells")

    # Sanity vs expected
    if len(db_lines) != expected_acts:
        print(f"  ** LINES MISMATCH: expected {expected_acts}, got {len(db_lines)} **")
    if db_cells_count != expected_cells_fallback:
        print(f"  ** CELLS MISMATCH: expected {expected_cells_fallback}, got {db_cells_count} **")

    # Now call resolveTemplate (this is what frontend uses)
    resolved = await budget_service.resolve_budget_line_items(db, tmpl_id)
    print(f"  resolveTemplate  : returned {len(resolved)} rows")
    rows_with_li = sum(1 for r in resolved if r.get("line_item_id"))
    rows_no_li = len(resolved) - rows_with_li
    print(f"    with line_item_id: {rows_with_li}, without: {rows_no_li}")

    if len(resolved) != expected_acts:
        print(f"  ** RESOLVE MISMATCH: expected {expected_acts}, got {len(resolved)} **")

    # Look for activities present in DB but missing from resolveTemplate
    db_ce_names = {(li.cost_element_id, li.id) for li in db_lines}
    resolved_ce = {r["cost_element_id"] for r in resolved if r.get("cost_element_id")}
    missing_in_resolve = []
    for li in db_lines:
        if str(li.cost_element_id) not in resolved_ce:
            ce = await db.get(CostElement, li.cost_element_id)
            missing_in_resolve.append((li.id, ce.name if ce else "?"))
    if missing_in_resolve:
        print(f"  ** {len(missing_in_resolve)} line items missing from resolveTemplate output **")
        for li_id, name in missing_in_resolve[:5]:
            print(f"    - {name}")

    # Check what frontend's filter `Boolean(l.line_item_id)` would drop
    after_frontend_filter = sum(1 for r in resolved if r.get("line_item_id"))
    if after_frontend_filter != len(resolved):
        print(f"  ** Frontend filter would drop {len(resolved) - after_frontend_filter} rows (line_item_id=None) **")

    # Per-section breakdown of returned rows
    sec_counter = Counter((r.get("category") or "(no category)") for r in resolved)
    print(f"  Sections in resolveTemplate output: {len(sec_counter)}")
    for sec, n_rows in sec_counter.most_common():
        print(f"    {sec[:40]:40}  {n_rows}")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        # Pick first trial
        r = await db.execute(text("SELECT id FROM studies LIMIT 1"))
        row = r.first()
        if not row:
            print("No studies in DB"); return
        trial_id = row[0]
        print(f"(using trial_id={trial_id})\n")

        for sid in ["D0816C00010", "BO27938"]:
            try:
                await audit_one(db, sid, trial_id)
            except Exception as e:
                print(f"  CRASH: {e}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
