"""
Seed element_category hierarchy, link cost_element.category_id, and
populate element_bundle_composition for LAB-BUNDLE-001.
Safe to re-run — uses INSERT ON CONFLICT DO NOTHING.
"""
import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit(
        "DATABASE_URL is not set. Run inside the backend container "
        "(docker compose sets it) or export it first."
    )

# ── Category hierarchy (name, parent_name_or_None, sort_order) ──────────────
TOP_CATEGORIES = [
    ("Laboratory",        None, 0),
    ("Imaging",           None, 1),
    ("Procedures",        None, 2),
    ("Regulatory / Admin",None, 3),
    ("Overhead / Startup",None, 4),
]

SUB_CATEGORIES = [
    # (name, parent_top_level_name, sort_order)
    ("Laboratory / Hematology", "Laboratory", 0),
    ("Laboratory / Chemistry",  "Laboratory", 1),
    ("Laboratory / Biomarkers", "Laboratory", 2),
]

# ── Element → category name mapping ─────────────────────────────────────────
# Maps cost_element.code to the category name that should be set as category_id
ELEMENT_CATEGORY_MAP = {
    # Hematology
    "LAB-HEM-001": "Laboratory / Hematology",
    "LAB-HEM-002": "Laboratory / Hematology",
    "LAB-HEM-003": "Laboratory / Hematology",
    "LAB-HEM-004": "Laboratory / Hematology",
    # Chemistry
    "LAB-CHEM-001": "Laboratory / Chemistry",
    "LAB-CHEM-002": "Laboratory / Chemistry",
    "LAB-CHEM-003": "Laboratory / Chemistry",
    "LAB-CHEM-004": "Laboratory / Chemistry",
    # Biomarkers
    "LAB-BIO-001": "Laboratory / Biomarkers",
    "LAB-BIO-002": "Laboratory / Biomarkers",
    "LAB-BIO-003": "Laboratory / Biomarkers",
    "LAB-BIO-004": "Laboratory / Biomarkers",
    # Bundles → top-level Laboratory
    "LAB-BUNDLE-001": "Laboratory",
    "LAB-CHM-001":    "Laboratory / Chemistry",
    # Imaging
    "IMG-001": "Imaging",
    "IMG-002": "Imaging",
    "IMG-003": "Imaging",
    "IMG-004": "Imaging",
    "IMG-005": "Imaging",
    # Procedures
    "PROC-001": "Procedures",
    "PROC-002": "Procedures",
    "PROC-003": "Procedures",
    "PROC-004": "Procedures",
    # Regulatory
    "REG-001": "Regulatory / Admin",
    "REG-002": "Regulatory / Admin",
    # Overhead
    "OVR-001": "Overhead / Startup",
}

# ── Bundle composition: LAB-BUNDLE-001 = CBC + CMP + LFT ─────────────────────
BUNDLE_COMPOSITIONS = {
    "LAB-BUNDLE-001": [
        ("LAB-HEM-001", 1.0, 0),   # CBC
        ("LAB-HEM-002", 1.0, 1),   # Comprehensive Metabolic Panel
        ("LAB-CHEM-001", 1.0, 2),  # Liver Function Tests
    ],
}


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)  # type: ignore[call-overload]

    async with async_session() as session:
        async with session.begin():

            # ── 1. Insert top-level categories ──────────────────────────────
            cat_id_by_name: dict[str, str] = {}

            for (name, parent, order) in TOP_CATEGORIES:
                row = await session.execute(
                    text("SELECT id FROM element_category WHERE name = :name AND parent_id IS NULL"),
                    {"name": name}
                )
                existing = row.fetchone()
                if existing:
                    cat_id_by_name[name] = str(existing[0])
                else:
                    res = await session.execute(
                        text("INSERT INTO element_category (name, sort_order) VALUES (:name, :order) RETURNING id"),
                        {"name": name, "order": order}
                    )
                    cat_id_by_name[name] = str(res.fetchone()[0])

            print(f"[OK] Top-level categories: {len(cat_id_by_name)}")

            # ── 2. Insert subcategories ──────────────────────────────────────
            for (name, parent_name, order) in SUB_CATEGORIES:
                parent_id = cat_id_by_name.get(parent_name)
                row = await session.execute(
                    text("SELECT id FROM element_category WHERE name = :name"),
                    {"name": name}
                )
                existing = row.fetchone()
                if existing:
                    cat_id_by_name[name] = str(existing[0])
                else:
                    res = await session.execute(
                        text("""
                            INSERT INTO element_category (name, parent_id, sort_order)
                            VALUES (:name, :parent_id, :order) RETURNING id
                        """),
                        {"name": name, "parent_id": parent_id, "order": order}
                    )
                    cat_id_by_name[name] = str(res.fetchone()[0])

            print(f"[OK] Subcategories seeded. Total categories: {len(cat_id_by_name)}")

            # ── 3. Link cost_element.category_id ────────────────────────────
            updated_links = 0
            for code, cat_name in ELEMENT_CATEGORY_MAP.items():
                cat_id = cat_id_by_name.get(cat_name)
                if not cat_id:
                    print(f"  [WARN] Category not found: {cat_name} (for {code})")
                    continue
                res = await session.execute(
                    text("""
                        UPDATE cost_element SET category_id = :cat_id
                        WHERE code = :code AND (category_id IS NULL OR category_id != :cat_id)
                        RETURNING id
                    """),
                    {"cat_id": cat_id, "code": code}
                )
                if res.fetchone():
                    updated_links += 1

            print(f"[OK] cost_element.category_id linked: {updated_links} rows updated")

            # ── 4. Verify all elements are linked ────────────────────────────
            unlinked = await session.execute(
                text("SELECT code FROM cost_element WHERE category_id IS NULL AND is_active = TRUE")
            )
            unlinked_codes = [r[0] for r in unlinked.fetchall()]
            if unlinked_codes:
                print(f"  [WARN] {len(unlinked_codes)} active elements still have no category_id: {unlinked_codes}")

            # ── 5. Bundle composition ─────────────────────────────────────────
            inserted_compositions = 0
            for bundle_code, children in BUNDLE_COMPOSITIONS.items():
                bundle_row = await session.execute(
                    text("SELECT id FROM cost_element WHERE code = :code"),
                    {"code": bundle_code}
                )
                bundle = bundle_row.fetchone()
                if not bundle:
                    print(f"  [WARN] Bundle not found: {bundle_code}")
                    continue
                bundle_id = str(bundle[0])

                for (child_code, qty, order) in children:
                    child_row = await session.execute(
                        text("SELECT id FROM cost_element WHERE code = :code"),
                        {"code": child_code}
                    )
                    child = child_row.fetchone()
                    if not child:
                        print(f"  [WARN] Child element not found: {child_code}")
                        continue
                    child_id = str(child[0])

                    exists = await session.execute(
                        text("""
                            SELECT 1 FROM element_bundle_composition
                            WHERE bundle_element_id = :bid AND child_element_id = :cid
                        """),
                        {"bid": bundle_id, "cid": child_id}
                    )
                    if not exists.fetchone():
                        await session.execute(
                            text("""
                                INSERT INTO element_bundle_composition
                                    (bundle_element_id, child_element_id, quantity_in_bundle, sort_order)
                                VALUES (:bid, :cid, :qty, :order)
                            """),
                            {"bid": bundle_id, "cid": child_id, "qty": qty, "order": order}
                        )
                        inserted_compositions += 1

            print(f"[OK] Bundle compositions inserted: {inserted_compositions}")

    await engine.dispose()
    print("[DONE] Categories, links, and bundles seeded.")


if __name__ == "__main__":
    asyncio.run(main())
