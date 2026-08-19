"""
Idempotent seed for site budgeting master data:

- element_category (top-level categories from cost_master_data.CATEGORIES)
- cost_element + element_cost_version (FMV) from cost_master_data.ELEMENTS
- conversion_factor_type + country adjustment factors

Run from Backend-CRM (app on PYTHONPATH):

    python -m app.modules.site_budgeting.seed_data
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date
from decimal import Decimal

if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

from sqlalchemy import select

from app.config import settings
from app.db import AsyncSessionLocal
import app.models  # noqa: F401 — ensures 'studies' and 'sites' tables are registered with SQLAlchemy metadata
from app.modules.site_budgeting.cost_master_data import (
    CATEGORIES,
    ELEMENTS,
    VERSION_LABEL,
    build_description,
    derive_cost_type,
)
from app.modules.site_budgeting.db_models import (
    ConversionFactor,
    ConversionFactorType,
    CostElement,
    ElementCategory,
    ElementCostVersion,
)

_NS_SEED = uuid.UUID("018f1b4e-81f2-7d3a-a1b2-c3d4e5f60789")
_NS_FACTOR_TYPE = uuid.UUID("018f1b4e-81f2-7d3a-a1b2-c3d4e5f60791")
_NS_CATEGORY = uuid.UUID("018f1b4e-81f2-7d3a-a1b2-c3d4e5f60793")
_NS_FACTOR = uuid.UUID("018f1b4e-81f2-7d3a-a1b2-c3d4e5f60795")


def _element_id(code: str) -> uuid.UUID:
    return uuid.uuid5(_NS_SEED, f"cost_element:{code}")


def _version_id(cost_element_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(_NS_SEED, f"element_cost_version:{cost_element_id}:{VERSION_LABEL}")


def _category_id(name: str) -> uuid.UUID:
    return uuid.uuid5(_NS_CATEGORY, f"element_category:{name}")


def _factor_type_id(code: str) -> uuid.UUID:
    return uuid.uuid5(_NS_FACTOR_TYPE, f"conversion_factor_type:{code}")


def _country_factor_id(country_code: str) -> uuid.UUID:
    return uuid.uuid5(_NS_FACTOR, f"conversion_factor:COUNTRY:{country_code}")


# (iso3_code, display_name, multiplier)
_COUNTRY_FACTORS: list[tuple[str, str, Decimal]] = [
    ("USA", "United States", Decimal("1.00")),
    ("GBR", "United Kingdom", Decimal("0.92")),
    ("DEU", "Germany", Decimal("0.95")),
    ("JPN", "Japan", Decimal("1.35")),
    ("IND", "India", Decimal("0.45")),
    ("BRA", "Brazil", Decimal("0.55")),
    ("AUS", "Australia", Decimal("1.05")),
    ("POL", "Poland", Decimal("0.60")),
]


# (code, name, mode, description)
_FACTOR_TYPE_SEEDS: list[tuple[str, str, str, str | None]] = [
    ("MULT", "Multiplicative default", "MULTIPLICATIVE", "Default multiplicative factor slot"),
    ("ADD", "Additive default", "ADDITIVE", "Default additive factor slot"),
    ("PASS", "Pass-through default", "PASS_THROUGH", "Pass-through / no transform"),
    ("COUNTRY", "Country Adjustment", "MULTIPLICATIVE", "Geographic cost multiplier by country"),
    ("SITE", "Site Adjustment", "MULTIPLICATIVE", "Site-specific cost multiplier"),
    ("TRIAL_COMPLEXITY", "Trial Complexity", "MULTIPLICATIVE", "Protocol complexity multiplier"),
    ("COMPETITIVENESS", "Market Competitiveness", "MULTIPLICATIVE", "Competitive site landscape multiplier"),
]


async def run() -> None:
    print("Site budgeting seed — element_category + cost_element + element_cost_version + conversion_factor_type")
    db_info = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Database: {db_info}\n")

    today = date.today()
    inserted_cat = 0
    skipped_cat = 0
    inserted_el = 0
    inserted_ver = 0
    skipped_el = 0
    inserted_ft = 0
    skipped_ft = 0

    async with AsyncSessionLocal() as session:
        # Categories first — elements FK to category_id
        cat_id_by_name: dict[str, uuid.UUID] = {}
        for sort_order, cname in enumerate(CATEGORIES, start=10):
            cid = _category_id(cname)
            cat_id_by_name[cname] = cid
            existing_cat = (
                await session.execute(select(ElementCategory.id).where(ElementCategory.name == cname))
            ).scalar_one_or_none()
            if existing_cat is not None:
                # Adopt existing id so element FK resolves to it.
                cat_id_by_name[cname] = existing_cat
                skipped_cat += 1
                print(f"[skip] element_category name={cname!r} already exists")
                continue
            session.add(ElementCategory(id=cid, name=cname, sort_order=sort_order))
            inserted_cat += 1
            print(f"[insert] element_category {cname} (sort={sort_order})")

        await session.flush()

        print()
        for code, name, category, subcategory, payment_type, user_cost_type, unit, base_amount, pass_thru in ELEMENTS:
            existing = (
                await session.execute(select(CostElement.id).where(CostElement.code == code))
            ).scalar_one_or_none()
            if existing is not None:
                skipped_el += 1
                print(f"[skip] cost_element code={code!r} already exists")
                continue

            eid = _element_id(code)
            vid = _version_id(eid)
            session.add(
                CostElement(
                    id=eid,
                    code=code,
                    name=name,
                    description=build_description(subcategory, unit, user_cost_type, pass_thru),
                    unit_of_measure=payment_type,
                    category_id=cat_id_by_name.get(category),
                    element_type="ATOMIC",
                    cost_type=derive_cost_type(user_cost_type, payment_type, pass_thru),
                )
            )
            session.add(
                ElementCostVersion(
                    id=vid,
                    element_id=eid,
                    version_label=VERSION_LABEL,
                    base_unit_cost=base_amount,
                    reference_currency="USD",
                    effective_from=today,
                    effective_to=None,
                )
            )
            inserted_el += 1
            inserted_ver += 1
            print(f"[insert] {code} → {name} (USD {base_amount}, {VERSION_LABEL})")

        print()
        for code, name, mode, desc in _FACTOR_TYPE_SEEDS:
            existing_ft = (
                await session.execute(select(ConversionFactorType.id).where(ConversionFactorType.code == code))
            ).scalar_one_or_none()
            if existing_ft is not None:
                skipped_ft += 1
                print(f"[skip] conversion_factor_type code={code!r} already exists")
                continue
            session.add(
                ConversionFactorType(
                    id=_factor_type_id(code),
                    code=code,
                    name=name,
                    mode=mode,
                    description=desc,
                )
            )
            inserted_ft += 1
            print(f"[insert] factor_type {code} → {name} ({mode})")

        # Seed country adjustment factors (requires COUNTRY factor type to exist first)
        country_ft_id = _factor_type_id("COUNTRY")
        inserted_cf = 0
        skipped_cf = 0
        print()
        for iso3, display_name, multiplier in _COUNTRY_FACTORS:
            cf_id = _country_factor_id(iso3)
            existing_cf = (
                await session.execute(select(ConversionFactor.id).where(ConversionFactor.id == cf_id))
            ).scalar_one_or_none()
            if existing_cf is not None:
                skipped_cf += 1
                print(f"[skip] country_factor country_code={iso3!r} already exists")
                continue
            session.add(
                ConversionFactor(
                    id=cf_id,
                    factor_type_id=country_ft_id,
                    country_code=iso3,
                    value=multiplier,
                    label=display_name,
                    scope_level="GLOBAL",
                )
            )
            inserted_cf += 1
            print(f"[insert] country_factor {iso3} → {display_name} (×{multiplier})")

        await session.commit()

    print(
        f"\nDone. categories inserted={inserted_cat}, categories skipped={skipped_cat}; "
        f"elements inserted={inserted_el}, versions={inserted_ver}, elements skipped={skipped_el}; "
        f"factor_types inserted={inserted_ft}, factor_types skipped={skipped_ft}; "
        f"country_factors inserted={inserted_cf}, country_factors skipped={skipped_cf}."
    )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
