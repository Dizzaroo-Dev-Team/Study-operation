"""
Fill metadata + base cost on auto-imported SOA-* cost_element rows.

The SOA importer (services/budget_service.py) creates cost_elements with
`code = "SOA-<8hex>"`, base_unit_cost = 0, and no category. This script
populates the human-supplied values (NEW CODE, name, category/subcategory,
payment type, unit, pass-thru, base cost) for a known list of SOA codes.

`code` is left as SOA-* because the NEW CODEs collide both with each other
(e.g. PK-001 appears 3x, ONC-008 appears 2x) and with codes already in the
master catalog. The NEW CODE is preserved inside the description metadata so
the frontend can still surface it.

Idempotent: re-running upserts the same values.

Run:
  docker exec -w /app backend-crm-backend-1 python -m scripts.fill_soa_cost_elements
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
import app.models  # noqa: F401  ensure SA metadata registry is populated
from app.modules.site_budgeting.cost_master_data import VERSION_LABEL, derive_cost_type
from app.modules.site_budgeting.db_models import (
    CostElement,
    ElementCategory,
    ElementCostVersion,
)


# (soa_code, new_code, name, category, subcategory, payment_type, cost_variability, unit, pass_thru, base_cost_usd)
ROWS: list[tuple[str, str, str, str, str, str, str, str, str, Decimal]] = [
    ("SOA-08F9B59C", "ONC-008", "Archival Tumor Tissue Collection",        "ONCOLOGY-SPECIFIC", "Pathology",       "PER PATIENT", "VARIABLE", "Per Block",      "Y", Decimal("180.00")),
    ("SOA-0C4CDBB2", "LAB-001", "Laboratory Tests (Chemistry)",            "ASSESSMENTS",       "Local Lab",       "PER VISIT",   "VARIABLE", "Per Panel",      "N", Decimal("45.00")),
    ("SOA-0E2C9685", "BIO-006", "Blood for Retrospective Biomarkers",      "BIOMARKERS",        "Phlebotomy",      "PER SAMPLE",  "VARIABLE", "Per Sample",     "N", Decimal("50.00")),
    ("SOA-14B59EDA", "IMG-001", "Tumor Imaging (CT/MRI)",                  "IMAGING",           "Radiology",       "PER VISIT",   "VARIABLE", "Per Scan",       "Y", Decimal("1850.00")),
    ("SOA-15C70F59", "CLIN-001", "ECOG Performance Status",                "ASSESSMENTS",       "Clinical Assess.","PER VISIT",   "VARIABLE", "Per Eval",       "N", Decimal("25.00")),
    ("SOA-2817AA7E", "PK-001",  "PK Samples (Part 2 - Sparse)",            "PK/ADA",            "PK Blood Draw",   "PER SAMPLE",  "VARIABLE", "Per Time-Point", "N", Decimal("85.00")),
    ("SOA-2E162CE1", "CLIN-002", "Vital Signs",                            "ASSESSMENTS",       "Clinical Assess.","PER VISIT",   "VARIABLE", "Per Eval",       "N", Decimal("35.00")),
    ("SOA-32952189", "CARD-001", "ECG (Part 2 - Standard)",                "ASSESSMENTS",       "Cardiology",      "PER VISIT",   "VARIABLE", "Per Scan",       "N", Decimal("125.00")),
    ("SOA-49954B7A", "CLIN-003", "Concomitant Medications",                "ASSESSMENTS",       "Review",          "PER VISIT",   "VARIABLE", "Per Review",     "N", Decimal("30.00")),
    ("SOA-4AE2CD25", "CARD-002", "ECG (Part 1 - Intensive)",               "ASSESSMENTS",       "Cardiology",      "PER VISIT",   "VARIABLE", "Per Scan",       "N", Decimal("125.00")),
    ("SOA-5197CBC8", "ELIG-001", "Medical History",                        "ELIGIBILITY",       "Clinical Assess.","ONCE",        "VARIABLE", "Per Patient",    "N", Decimal("150.00")),
    ("SOA-5CD53236", "SAF-003", "Adverse Events",                          "SAFETY",            "Safety",          "PER VISIT",   "VARIABLE", "Per Review",     "N", Decimal("65.00")),
    ("SOA-607C0ADD", "LAB-002", "Urinalysis",                              "ASSESSMENTS",       "Local Lab",       "PER VISIT",   "VARIABLE", "Per Test",       "N", Decimal("20.00")),
    ("SOA-63F2EA60", "BIO-007", "Genetics/Pharmacogenomics (tissue)",      "BIOMARKERS",        "Genetics",        "PER SAMPLE",  "VARIABLE", "Per Sample",     "Y", Decimal("850.00")),
    ("SOA-6A2436E2", "LAB-003", "Blood for CA19.9/CEA",                    "BIOMARKERS",        "Central Lab",     "PER SAMPLE",  "VARIABLE", "Per Sample",     "N", Decimal("65.00")),
    ("SOA-6F567246", "ELIG-002", "Inclusion/Exclusion Criteria",           "ELIGIBILITY",       "Clinical Assess.","ONCE",        "VARIABLE", "Per Patient",    "N", Decimal("120.00")),
    ("SOA-819B4587", "CLIN-004", "Physical Examination",                   "ASSESSMENTS",       "Clinical Assess.","PER VISIT",   "VARIABLE", "Per Exam",       "N", Decimal("65.00")),
    ("SOA-8916CD8B", "PK-001",  "PK Samples (Part 1 - Intensive)",         "PK/ADA",            "PK Blood Draw",   "PER SAMPLE",  "VARIABLE", "Per Time-Point", "N", Decimal("85.00")),
    ("SOA-89E37487", "LAB-004", "DPD Deficiency Testing",                  "ELIGIBILITY",       "Local Lab",       "ONCE",        "VARIABLE", "Per Test",       "N", Decimal("150.00")),
    ("SOA-8D6BA40F", "LAB-005", "Lab Tests (Heme, Chem, Coag)",            "ASSESSMENTS",       "Local Lab",       "PER VISIT",   "VARIABLE", "Per Panel",      "N", Decimal("85.00")),
    ("SOA-950B42C1", "BIO-008", "Optional Biomarker Sampling",             "BIOMARKERS",        "Optional",        "PER SAMPLE",  "VARIABLE", "Per Sample",     "N", Decimal("50.00")),
    ("SOA-967C153E", "ELIG-003", "Informed Consent",                       "ELIGIBILITY",       "Admin",           "ONCE",        "VARIABLE", "Per Patient",    "N", Decimal("180.00")),
    ("SOA-9C596934", "DRUG-001", "Dose Modifications Review",              "STUDY DRUG",        "Clinical Assess.","PER EVENT",   "VARIABLE", "Per Review",     "N", Decimal("45.00")),
    ("SOA-A2F965D9", "LAB-006", "Pregnancy Test (Serum or Urine)",         "ASSESSMENTS",       "Local Lab",       "PER VISIT",   "VARIABLE", "Per Test",       "N", Decimal("25.00")),
    ("SOA-B2418684", "ONC-008", "Archival/Biopsy Tumor Tissue Collection", "BIOMARKERS",        "Pathology",       "PER PATIENT", "VARIABLE", "Per Block",      "Y", Decimal("180.00")),
    ("SOA-B453136D", "PK-001",  "PK Blood Samples",                        "PK/ADA",            "PK Blood Draw",   "PER SAMPLE",  "VARIABLE", "Per Time-Point", "N", Decimal("85.00")),
    ("SOA-BA47B15D", "ONC-001", "Study Drug Administration",               "STUDY DRUG",        "Infusion",        "PER HOUR",    "VARIABLE", "Per Hour",       "N", Decimal("185.00")),
    ("SOA-BE94BC2D", "LAB-007", "Laboratory Tests (Hematology)",           "ASSESSMENTS",       "Local Lab",       "PER VISIT",   "VARIABLE", "Per Panel",      "N", Decimal("40.00")),
    ("SOA-BEC9CFAE", "CARD-001", "12-lead ECG",                            "ASSESSMENTS",       "Cardiology",      "PER VISIT",   "VARIABLE", "Per Scan",       "N", Decimal("125.00")),
    ("SOA-D43D3D46", "IMG-001", "Tumor Imaging (CT/MRI)",                  "ASSESSMENTS",       "Radiology",       "PER VISIT",   "VARIABLE", "Per Scan",       "Y", Decimal("1850.00")),
    ("SOA-EE17F9C7", "SAF-001", "Adverse Events/SAEs",                     "ASSESSMENTS",       "Safety",          "PER EVENT",   "VARIABLE", "Per SAE",        "N", Decimal("320.00")),
    ("SOA-F29815C4", "DRUG-003", "Pre-medications (if applicable)",        "STUDY DRUG",        "Pharmacy",        "PER VISIT",   "VARIABLE", "Per Admin",      "N", Decimal("35.00")),
]


def build_description(new_code: str, subcategory: str, unit: str, cost_variability: str, pass_thru: str) -> str:
    return (
        f"New Code: {new_code} | Subcategory: {subcategory} | Unit: {unit} | "
        f"Cost Type: {cost_variability} | Pass-Thru: {pass_thru}"
    )


async def _get_or_create_category(session: AsyncSession, name: str, sort_cache: dict[str, int]) -> uuid.UUID:
    r = await session.execute(select(ElementCategory).where(ElementCategory.name == name))
    cat = r.scalar_one_or_none()
    if cat:
        return cat.id
    next_sort = max(sort_cache.values(), default=0) + 10
    sort_cache[name] = next_sort
    cat = ElementCategory(id=uuid.uuid4(), name=name, sort_order=next_sort)
    session.add(cat)
    await session.flush()
    return cat.id


async def run() -> None:
    today = date.today()
    print(f"Filling {len(ROWS)} SOA-* cost elements with master values...")

    async with AsyncSessionLocal() as session:  # type: AsyncSession
        existing_cats = (await session.execute(select(ElementCategory))).scalars().all()
        sort_cache: dict[str, int] = {c.name: c.sort_order for c in existing_cats}

        updated = 0
        missing: list[str] = []
        for soa_code, new_code, name, category, subcategory, payment_type, cost_variability, unit, pass_thru, base_cost in ROWS:
            er = await session.execute(select(CostElement).where(CostElement.code == soa_code))
            el = er.scalar_one_or_none()
            if not el:
                missing.append(soa_code)
                continue

            cat_id = await _get_or_create_category(session, category, sort_cache)

            el.name = name
            el.category_id = cat_id
            el.unit_of_measure = payment_type
            el.description = build_description(new_code, subcategory, unit, cost_variability, pass_thru)
            el.cost_type = derive_cost_type(cost_variability, payment_type, pass_thru)
            el.is_active = True

            # Upsert latest version for VERSION_LABEL
            vr = await session.execute(
                select(ElementCostVersion).where(
                    ElementCostVersion.element_id == el.id,
                    ElementCostVersion.version_label == VERSION_LABEL,
                )
            )
            ver = vr.scalar_one_or_none()
            if ver:
                ver.base_unit_cost = base_cost
                ver.reference_currency = "USD"
                ver.source = "soa_fill_2026"
            else:
                session.add(
                    ElementCostVersion(
                        id=uuid.uuid4(),
                        element_id=el.id,
                        version_label=VERSION_LABEL,
                        base_unit_cost=base_cost,
                        reference_currency="USD",
                        effective_from=today,
                        source="soa_fill_2026",
                    )
                )
            updated += 1

        await session.commit()
        print(f"Updated {updated}/{len(ROWS)} elements.")
        if missing:
            print(f"Missing SOA codes (no matching cost_element row, skipped): {missing}")


if __name__ == "__main__":
    asyncio.run(run())
