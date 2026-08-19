"""
Rebuild the cost-element catalog from MongoDB SOA data.

What it does (in order, in one transaction):
  1. Wipes per-trial budget data so the cost_element FK constraint (RESTRICT) can be released:
     budget_visit_matrix, budget_line_item, visit_schedule, budget_milestone, budget_note,
     budget_personnel_role, budget_template, trial_factor_configuration,
     budget_policy_document, site_budgeting_audit_log.
  2. Deletes existing cost_element rows whose cost_type is NOT 'MILESTONE' / 'PASS_THROUGH'
     (the milestone-related rows are kept so milestone generation still works).
  3. Walks every SOA document in MongoDB. Collects unique activities — case-insensitive
     by name. Each unique activity becomes a cost_element with:
        code  = "SOA-<8hex>"
        name  = activity.name
        description = section.title (e.g. "ELIGIBILITY")
        category   = ElementCategory(section.title)
        cost_type   = "PER_VISIT"
        is_active   = True
  4. Seeds a default ElementCostVersion at base_unit_cost = 0 USD for each new element.
     User edits costs later in the Cost Master Elements tab.

Run:
  docker exec -w /app backend-crm-backend-1 python -m scripts.rebuild_cost_catalog_from_mongo
"""
import asyncio
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select, text

from app.db import AsyncSessionLocal
import app.models  # noqa: F401  ensure SA metadata registry is fully populated
from app.modules.site_budgeting.db_models import (
    CostElement,
    ElementCategory,
    ElementCostVersion,
)
from app.modules.site_budgeting.services import mongo_service


VERSION_LABEL = "SOA-IMPORT-2026"

KEPT_COST_TYPES = ("MILESTONE", "PASS_THROUGH")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        # 1. Wipe per-trial budget data (RESTRICT FK on cost_element_id forces this).
        wipe_statements = [
            "DELETE FROM budget_visit_matrix",
            "DELETE FROM budget_line_item",
            "DELETE FROM visit_schedule",
            "DELETE FROM budget_milestone",
            "DELETE FROM budget_note",
            "DELETE FROM budget_personnel_role",
            "DELETE FROM widget_schedule_visit",
            "DELETE FROM site_budgeting_audit_log",
            "DELETE FROM trial_factor_configuration",
            "DELETE FROM budget_policy_document",
            "DELETE FROM budget_template",
        ]
        for stmt in wipe_statements:
            await db.execute(text(stmt))
        await db.commit()
        print("[1/4] wiped per-trial budget data")

        # 2. Delete non-milestone cost elements (and their versions / bundle rows).
        # Order matters: versions + bundle children first, then the element row itself.
        await db.execute(text(f"""
            DELETE FROM element_bundle_composition
            WHERE bundle_element_id IN (
                SELECT id FROM cost_element
                WHERE cost_type NOT IN ({','.join(repr(c) for c in KEPT_COST_TYPES)})
            )
            OR child_element_id IN (
                SELECT id FROM cost_element
                WHERE cost_type NOT IN ({','.join(repr(c) for c in KEPT_COST_TYPES)})
            )
        """))
        await db.execute(text(f"""
            DELETE FROM element_cost_version
            WHERE element_id IN (
                SELECT id FROM cost_element
                WHERE cost_type NOT IN ({','.join(repr(c) for c in KEPT_COST_TYPES)})
            )
        """))
        deleted = (await db.execute(text(f"""
            DELETE FROM cost_element
            WHERE cost_type NOT IN ({','.join(repr(c) for c in KEPT_COST_TYPES)})
            RETURNING id
        """))).all()
        await db.commit()
        print(f"[2/4] deleted {len(deleted)} non-milestone cost elements")

        # 3. Pull unique activities from every SOA in Mongo.
        soa_ids = await mongo_service.list_soa_ids(limit=1000)
        print(f"      MongoDB: {len(soa_ids)} SOA documents to scan")

        unique_acts: dict[str, tuple[str, str]] = {}  # name_lower → (name, section_title)
        per_doc_count = 0
        for sid in soa_ids:
            doc = await mongo_service.fetch_soa(sid)
            if not doc:
                continue
            per_doc_count += 1
            for sec in (doc.get("sections") or []):
                title = ((sec.get("title") or "").strip() or "OTHER").upper()
                for act in (sec.get("activities") or []):
                    name = (act.get("name") or "").strip()
                    if not name:
                        continue
                    key = name.lower()
                    if key not in unique_acts:
                        unique_acts[key] = (name, title)
        print(f"[3/4] scanned {per_doc_count} SOA docs, found {len(unique_acts)} unique activities")

        # 4. Get-or-create ElementCategory rows + insert cost_elements.
        cat_ids: dict[str, uuid.UUID] = {}
        for _, title in unique_acts.values():
            if title in cat_ids:
                continue
            existing = (await db.execute(
                select(ElementCategory).where(func.lower(ElementCategory.name) == title.lower())
            )).scalar_one_or_none()
            if existing is not None:
                cat_ids[title] = existing.id
            else:
                cat = ElementCategory(name=title, sort_order=999)
                db.add(cat)
                await db.flush()
                cat_ids[title] = cat.id

        today = date.today()
        inserted = 0
        for name, title in unique_acts.values():
            code = f"SOA-{uuid.uuid4().hex[:8].upper()}"
            el = CostElement(
                code=code,
                name=name,
                description=title,
                unit_of_measure="Per Visit",
                category_id=cat_ids[title],
                element_type="ATOMIC",
                cost_type="PER_VISIT",
                is_active=True,
            )
            db.add(el)
            await db.flush()
            db.add(ElementCostVersion(
                element_id=el.id,
                version_label=VERSION_LABEL,
                base_unit_cost=Decimal("0"),
                reference_currency="USD",
                effective_from=today,
            ))
            inserted += 1

        await db.commit()
        print(f"[4/4] inserted {inserted} new cost elements + cost versions across {len(cat_ids)} categories")

        # Final report — sanity check kept rows
        kept_q = await db.execute(text(f"""
            SELECT cost_type, COUNT(*) FROM cost_element
            WHERE cost_type IN ({','.join(repr(c) for c in KEPT_COST_TYPES)})
            GROUP BY cost_type
        """))
        print("\nKept (milestone-related) rows still in catalog:")
        for ct, n in kept_q.all():
            print(f"  {ct:14}  {n}")
        total_q = await db.execute(text("SELECT COUNT(*) FROM cost_element"))
        print(f"Total cost_element rows now: {total_q.scalar_one()}")


if __name__ == "__main__":
    asyncio.run(main())
