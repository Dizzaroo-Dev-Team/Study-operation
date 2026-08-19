"""
Pure counting audit — mirrors generate_visit_matrix_from_soa logic to verify
no activities or cells get dropped, without writing anything to DB.
"""
import asyncio

from app.modules.site_budgeting.services import mongo_service
from app.modules.site_budgeting.services.ai_budget_service import normalize_soa


async def audit(sid: str) -> None:
    print("=" * 72)
    print(f"=== {sid} ===")

    doc = await mongo_service.fetch_soa(sid)
    if not doc:
        print("  SOA NOT FOUND")
        return

    raw_sections = doc.get("sections") or []
    raw_acts = []
    for sec in raw_sections:
        title = sec.get("title")
        for a in sec.get("activities") or []:
            raw_acts.append((title, a))

    print(f"  Raw counts: {len(raw_sections)} sections, {len(raw_acts)} activities")

    n = normalize_soa(doc)
    visits = n["visits"]
    activities = n["activities"]
    visits_n = len(visits)

    if len(raw_acts) != len(activities):
        print(f"  ** LOST {len(raw_acts) - len(activities)} activities during normalize **")
    else:
        print(f"  Normalized: {len(activities)} activities (matches raw) | {visits_n} visits")

    # Mirror generate_visit_matrix_from_soa cell-loop logic.
    expected_lines = 0
    expected_cells = 0
    activities_with_indices = 0
    activities_fallback_all = 0
    cells_per_activity_min = None
    cells_per_activity_max = 0

    name_to_visit_keys = {v["visit_name"]: True for v in visits}

    for a in activities:
        name = (a.get("name") or "").strip()
        if not name:
            continue
        expected_lines += 1
        # Build list of visit_names this activity hits, mirroring importer logic
        visit_names_for_act = a.get("visit_names") or []
        if not visit_names_for_act:
            # Importer falls back to "all visits" when visit_indices is empty
            visit_names_for_act = list(name_to_visit_keys.keys())
            activities_fallback_all += 1
        else:
            activities_with_indices += 1
        # Filter to visits that exist in the normalized output
        valid = [vn for vn in visit_names_for_act if vn in name_to_visit_keys]
        expected_cells += len(valid)
        if cells_per_activity_min is None or len(valid) < cells_per_activity_min:
            cells_per_activity_min = len(valid)
        if len(valid) > cells_per_activity_max:
            cells_per_activity_max = len(valid)

    print(
        f"  EXPECTED: {expected_lines} line items, {expected_cells} cells "
        f"(min/max cells per activity: {cells_per_activity_min}/{cells_per_activity_max})"
    )
    print(
        f"  Activities with explicit visits: {activities_with_indices}, "
        f"fallback-all: {activities_fallback_all}"
    )

    # Spot-check: any activity with empty visit_indices AND visits_n=0? That'd be 0 cells.
    if activities_fallback_all and visits_n == 0:
        print("  ** No visits in SOA — fallback activities will have 0 cells **")

    # Per-section count — confirm all sections survived
    from collections import Counter
    cat_counts = Counter(a.get("category") for a in activities)
    print("  Section breakdown:")
    for cat, n_acts in cat_counts.most_common():
        print(f"    {(cat or '(no cat)')[:36]:36}  {n_acts}")


async def main() -> None:
    for sid in ["D0816C00010", "BO27938", "Not Provided", "ABLE-32"]:
        await audit(sid)
        print()


if __name__ == "__main__":
    asyncio.run(main())
