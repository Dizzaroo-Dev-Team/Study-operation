"""Audit SOA → matrix mapping. Counts everything, surfaces drops."""
import asyncio
from collections import Counter

from app.modules.site_budgeting.services import mongo_service
from app.modules.site_budgeting.services.ai_budget_service import normalize_soa


async def audit(sid: str) -> None:
    doc = await mongo_service.fetch_soa(sid)
    if not doc:
        print(f"{sid}: NOT FOUND IN MONGO")
        return

    print("=" * 72)
    print(f"=== {sid} ===")

    raw_sections = doc.get("sections") or []
    raw_total = 0
    raw_zero_visits = 0
    raw_zero_activities_sections = 0
    raw_dup_names_per_section = 0
    raw_blank_names = 0

    for sec in raw_sections:
        title = sec.get("title") or "(no title)"
        acts = sec.get("activities") or []
        if not acts:
            raw_zero_activities_sections += 1
            continue
        seen_names = set()
        for a in acts:
            raw_total += 1
            name = (a.get("name") or "").strip()
            if not name:
                raw_blank_names += 1
                print(f"  BLANK NAME activity in section '{title}'")
                continue
            if name in seen_names:
                raw_dup_names_per_section += 1
                print(f"  DUPLICATE name '{name}' inside section '{title}'")
            seen_names.add(name)
            v = a.get("visits") or []
            if not v:
                raw_zero_visits += 1

    print(
        f"  RAW: {len(raw_sections)} sections, {raw_total} activities total, "
        f"{raw_zero_visits} zero-visit activities, {raw_blank_names} blank names, "
        f"{raw_zero_activities_sections} sections with no activities, "
        f"{raw_dup_names_per_section} duplicate names within sections"
    )

    n = normalize_soa(doc)
    visits_n = n["visits"]
    acts_n = n["activities"]
    print(f"  NORM: {len(visits_n)} visits, {len(acts_n)} activities")

    if raw_total != len(acts_n):
        diff = raw_total - len(acts_n)
        print(f"  ** LOST {diff} activities during normalize **")

    # Check visit_indices integrity
    visit_count = len(visits_n)
    out_of_range = []
    for a in acts_n:
        for idx in a["visit_indices"]:
            if idx < 0 or idx >= visit_count:
                out_of_range.append((a["name"], idx))
    if out_of_range:
        print(f"  ** {len(out_of_range)} out-of-range visit indices **")
        for name, idx in out_of_range[:3]:
            print(f"    - {name[:50]}: idx={idx} (max={visit_count - 1})")

    # Activities with no visit_indices → fallback to "all visits"
    empty_visit_acts = [a for a in acts_n if not a["visit_indices"]]
    if empty_visit_acts:
        print(f"  ALL-VISIT fallback ({len(empty_visit_acts)} activities, no indices in SOA):")
        for a in empty_visit_acts[:5]:
            print(f"    - [{(a['category'] or '')[:25]}] {a['name'][:55]}")

    # Section breakdown
    sec_counter = Counter((a.get("category") or "(no category)") for a in acts_n)
    print(f"  Sections in normalized output: {len(sec_counter)}")
    for sec, n_acts in sec_counter.most_common():
        print(f"    {sec[:34]:34}  {n_acts} activities")

    # Visit-name duplication after disambiguation
    vnames = [v["visit_name"] for v in visits_n]
    if len(vnames) != len(set(vnames)):
        print(f"  ** VISIT NAME COLLISION after normalize: {len(vnames)} visits, {len(set(vnames))} unique **")
        dupes = [n for n, c in Counter(vnames).items() if c > 1]
        for d in dupes:
            print(f"    duplicate: {d}")


async def main() -> None:
    for sid in ["D0816C00010", "BO27938", "Not Provided", "ABLE-32"]:
        await audit(sid)
        print()


if __name__ == "__main__":
    asyncio.run(main())
