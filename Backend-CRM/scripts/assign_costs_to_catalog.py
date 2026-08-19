"""
Assign costs to the auto-imported cost_element rows.

Strategy:
  1. Keyword match against a reference price list (lifted from the previous
     97-element catalog) — first match wins, longer keywords prioritised.
  2. Category fallback (e.g. anything in ASSESSMENTS without a keyword hit
     defaults to $40).
  3. Otherwise leave at $0.

Updates each element's latest ElementCostVersion in-place; doesn't create new
versions. Run after rebuild_cost_catalog_from_mongo.py.

  docker exec -w /app backend-crm-backend-1 python -m scripts.assign_costs_to_catalog
"""
import asyncio
from datetime import date
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
import app.models  # noqa: F401  ensure SA metadata
from app.modules.site_budgeting.db_models import (
    CostElement,
    ElementCategory,
    ElementCostVersion,
)


# Keyword → USD. Order matters — longest specific phrase first when ambiguous.
# Sourced from the prior 97-element FMV catalog.
KEYWORD_PRICES: list[tuple[str, int]] = [
    # Pharmacy / IP
    ("pharmacy setup", 1000),
    ("ip storage", 300),
    ("ip accountability", 40),
    ("ip dispensing", 50),
    ("ip destruction", 200),
    ("drug reconciliation", 50),
    ("blinding", 40),
    ("randomization", 50),
    # Imaging
    ("ct scan", 450),
    ("mri", 600),
    ("tumor assessment", 50),
    ("recist", 50),
    ("central imaging", 150),
    ("image transfer", 25),
    ("echo", 150),
    ("muga", 150),
    ("bone scan", 250),
    ("imaging", 150),
    # Lab / sample
    ("cbc", 35),
    ("complete blood count", 35),
    ("metabolic panel", 55),
    ("chemistry", 55),
    ("hematology", 35),
    ("coagulation", 25),
    ("urinalysis", 15),
    ("urine pregnancy", 25),
    ("blood pregnancy", 25),
    ("pregnancy test", 25),
    ("pk blood", 180),
    ("pharmacokinetic", 180),
    ("pk sample", 180),
    ("biomarker", 250),
    ("genetic", 800),
    ("genomic", 800),
    ("central lab", 75),
    ("specimen shipping", 100),
    ("sample shipping", 100),
    ("cold chain", 100),
    ("blood draw", 15),
    ("venipuncture", 15),
    ("laboratory", 50),
    ("laboratory test", 50),
    ("safety lab", 50),
    # Clinical procedure
    ("12-lead ecg", 100),
    ("12 lead ecg", 100),
    ("ecg", 100),
    ("ecog performance", 10),
    ("ecog", 10),
    ("performance status", 10),
    ("comprehensive physical", 125),
    ("targeted physical", 50),
    ("physical exam", 125),
    ("physical examination", 125),
    ("vital signs", 40),
    ("height and weight", 25),
    ("study drug administration", 100),
    ("infusion", 200),
    # Administrative
    ("informed consent", 100),
    ("inclusion/exclusion", 60),
    ("inclusion exclusion", 60),
    ("medical history", 40),
    ("demographics", 30),
    ("eligibility", 60),
    ("adverse event", 25),
    ("sae monitoring", 150),
    ("sae", 150),
    ("aesi", 25),
    ("concomitant medication", 30),
    ("dose modification", 40),
    ("subject randomization", 50),
    ("archival tumor tissue", 250),
    ("tumor tissue", 250),
    ("optional biomarker", 250),
    # Monitoring
    ("monitoring visit", 1200),
    ("on-site monitoring", 1200),
    ("remote monitoring", 600),
    ("source data verification", 150),
    ("sdv", 150),
    ("monitoring report", 200),
    ("qa audit", 1000),
    ("regulatory inspection", 1000),
    # Data / Tech
    ("edc", 25),
    ("ecrf", 25),
    ("ctms", 2000),
    ("econsent", 200),
    ("epro", 200),
    ("biobank", 1000),
    ("query resolution", 10),
    ("database lock", 2000),
    # Startup / Closeout
    ("site start-up", 3000),
    ("start-up", 3000),
    ("feasibility", 500),
    ("contract negotiation", 1500),
    ("regulatory document", 800),
    ("staff training", 500),
    ("certification", 500),
    ("equipment calibration", 500),
    ("close-out", 500),
    ("closeout", 500),
    ("tmf reconciliation", 1200),
    ("document filing", 800),
    ("document destruction", 800),
    # IRB
    ("irb initial", 2500),
    ("irb annual", 750),
    ("protocol amendment", 500),
    ("expedited review", 500),
    # Pass-through / personnel
    ("screen failure", 350),
    ("unscheduled visit", 200),
    ("telephone visit", 100),
    ("remote visit", 100),
    ("patient travel", 50),
    ("patient stipend", 50),
    ("patient recruitment", 500),
    ("patient retention", 300),
    ("patient reimbursement", 200),
    ("principal investigator", 325),
    ("sub-investigator", 250),
    ("research coordinator", 55),
    ("project manager", 75),
    ("research nurse", 65),
    ("data manager", 60),
    ("clinical pharmacist", 80),
    # Misc
    ("indemnity", 250),
    ("insurance", 250),
    ("courier", 100),
    ("contingency", 250),
    ("conference", 50),
]

# Section/category → default cost when no keyword hits. Section titles match what
# the rebuild script writes into ElementCategory (uppercased SOA section titles).
CATEGORY_DEFAULTS: dict[str, int] = {
    "ELIGIBILITY": 50,
    "ASSESSMENTS": 40,
    "BIOMARKERS": 250,
    "BIOMARKERS & GENETICS": 250,
    "BIOMARKERS & OTHER SAMPLES": 250,
    "PHARMACODYNAMIC & BIOMARKER ASSESSMENTS": 250,
    "STUDY DRUG TREATMENT": 100,
    "PHARMACOKINETICS (PK)": 180,
    "PHARMACOKINETICS (PK) or other biological sample procedures": 180,
    "LABORATORY ASSESSMENTS": 50,
    "OTHER PROCEDURES": 75,
}


def lookup_price(name: str, category: str | None) -> int:
    n = (name or "").lower()
    # Sort by length so longer/more specific keywords win
    for kw, price in sorted(KEYWORD_PRICES, key=lambda x: -len(x[0])):
        if kw in n:
            return price
    if category and category in CATEGORY_DEFAULTS:
        return CATEGORY_DEFAULTS[category]
    return 0


async def main() -> None:
    async with AsyncSessionLocal() as db:  # type: AsyncSession
        # Pull every cost_element with its category name
        rows = (await db.execute(text("""
            SELECT ce.id, ce.name, ec.name AS category
            FROM cost_element ce
            LEFT JOIN element_category ec ON ec.id = ce.category_id
        """))).all()

        updated_keyword = 0
        updated_category = 0
        left_at_zero = 0

        skipped_already_priced = 0

        for el_id, el_name, cat in rows:
            existing = (await db.execute(
                select(ElementCostVersion)
                .where(ElementCostVersion.element_id == el_id)
                .order_by(ElementCostVersion.created_at.desc())
                .limit(1)
            )).scalar_one_or_none()

            # Don't clobber rows that already have a real price (e.g. the kept PASS_THROUGH
            # / MILESTONE rows seeded earlier with IRB fees). Only fill in $0 entries.
            if existing is not None and existing.base_unit_cost and existing.base_unit_cost > 0:
                skipped_already_priced += 1
                continue

            n = (el_name or "").lower()
            keyword_hit = any(kw in n for kw, _ in KEYWORD_PRICES)
            price = lookup_price(el_name or "", cat)
            if price == 0 and not keyword_hit:
                left_at_zero += 1
            elif keyword_hit:
                updated_keyword += 1
            else:
                updated_category += 1

            if existing is not None:
                existing.base_unit_cost = Decimal(price)
                existing.reference_currency = "USD"
            else:
                db.add(ElementCostVersion(
                    element_id=el_id,
                    version_label="SOA-IMPORT-2026",
                    base_unit_cost=Decimal(price),
                    reference_currency="USD",
                    effective_from=date.today(),
                ))

        await db.commit()
        print(f"Total elements scanned     : {len(rows)}")
        print(f"  skipped (already priced) : {skipped_already_priced}")
        print(f"  priced via keyword       : {updated_keyword}")
        print(f"  priced via category fallback: {updated_category}")
        print(f"  left at $0 (no match)    : {left_at_zero}")


if __name__ == "__main__":
    asyncio.run(main())
