"""
Seed script: clinical-trial site-budgeting master data
Inserts cost elements, FMV 2026 Q1 cost versions, and conversion factor types.
Safe to re-run — skips rows whose code already exists.
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

# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------

ELEMENTS = [
    # (code, name, category, element_type, cost_type, unit, therapeutic_area, base_amount)
    ("LAB-HEM-001", "Complete Blood Count (CBC)", "Laboratory / Hematology", "ATOMIC", "PER_VISIT", "panel", None, "35.00"),
    ("LAB-HEM-002", "Comprehensive Metabolic Panel", "Laboratory / Hematology", "ATOMIC", "PER_VISIT", "panel", None, "45.00"),
    ("LAB-HEM-003", "Coagulation Studies (PT/PTT/INR)", "Laboratory / Hematology", "ATOMIC", "PER_VISIT", "panel", None, "55.00"),
    ("LAB-HEM-004", "Erythrocyte Sedimentation Rate", "Laboratory / Hematology", "ATOMIC", "PER_VISIT", "test", None, "25.00"),
    ("LAB-CHEM-001", "Liver Function Tests (LFTs)", "Laboratory / Chemistry", "ATOMIC", "PER_VISIT", "panel", None, "60.00"),
    ("LAB-CHEM-002", "Renal Function Panel", "Laboratory / Chemistry", "ATOMIC", "PER_VISIT", "panel", None, "55.00"),
    ("LAB-CHEM-003", "Lipid Panel", "Laboratory / Chemistry", "ATOMIC", "PER_VISIT", "panel", None, "40.00"),
    ("LAB-CHEM-004", "Thyroid Function Tests", "Laboratory / Chemistry", "ATOMIC", "PER_VISIT", "panel", None, "75.00"),
    ("LAB-BIO-001", "Biomarker Panel – Oncology", "Laboratory / Biomarkers", "ATOMIC", "PER_VISIT", "panel", "Oncology", "120.00"),
    ("LAB-BIO-002", "Pharmacokinetic Sampling", "Laboratory / Biomarkers", "ATOMIC", "PER_VISIT", "sample", None, "85.00"),
    ("LAB-BIO-003", "Cytokine Panel", "Laboratory / Biomarkers", "ATOMIC", "PER_VISIT", "panel", "Immunology", "150.00"),
    ("LAB-BIO-004", "Flow Cytometry", "Laboratory / Biomarkers", "ATOMIC", "PER_VISIT", "test", "Oncology", "200.00"),
    ("IMG-001", "CT Scan", "Imaging", "ATOMIC", "PER_VISIT", "scan", None, "450.00"),
    ("IMG-002", "MRI", "Imaging", "ATOMIC", "PER_VISIT", "scan", None, "850.00"),
    ("IMG-003", "PET Scan", "Imaging", "ATOMIC", "PER_VISIT", "scan", "Oncology", "2200.00"),
    ("IMG-004", "Echocardiogram", "Imaging", "ATOMIC", "PER_VISIT", "scan", "Cardiology", "350.00"),
    ("IMG-005", "X-Ray", "Imaging", "ATOMIC", "PER_VISIT", "scan", None, "85.00"),
    ("PROC-001", "Electrocardiogram (ECG/EKG)", "Procedures", "ATOMIC", "PER_VISIT", "procedure", None, "75.00"),
    ("PROC-002", "Vital Signs Assessment", "Procedures", "ATOMIC", "PER_VISIT", "assessment", None, "25.00"),
    ("PROC-003", "Physical Examination", "Procedures", "ATOMIC", "PER_VISIT", "assessment", None, "150.00"),
    ("PROC-004", "Biopsy Procedure", "Procedures", "ATOMIC", "PER_VISIT", "procedure", "Oncology", "800.00"),
    ("REG-001", "IRB Submission Fee", "Regulatory / Admin", "ATOMIC", "FIXED", "submission", None, "3500.00"),
    ("REG-002", "Site Initiation Visit", "Regulatory / Admin", "ATOMIC", "FIXED", "visit", None, "5000.00"),
    ("OVR-001", "Site Overhead / Startup", "Overhead / Startup", "ATOMIC", "FIXED", "flat", None, "15000.00"),
    ("LAB-BUNDLE-001", "Standard Lab Panel", "Laboratory", "BUNDLE", "PER_VISIT", "bundle", None, "155.00"),
]

FACTOR_TYPES = [
    # (code, name, mode, description)
    ("COUNTRY",          "Country Adjustment",     "MULTIPLICATIVE", "Geographic cost multiplier by country"),
    ("SITE",             "Site Adjustment",        "MULTIPLICATIVE", "Site-specific cost multiplier"),
    ("TRIAL_COMPLEXITY", "Trial Complexity",       "MULTIPLICATIVE", "Protocol complexity multiplier"),
    ("COMPETITIVENESS",  "Market Competitiveness", "MULTIPLICATIVE", "Competitive site landscape multiplier"),
]

# Default conversion_factor rows under COUNTRY factor type. trial_id is NULL so
# they surface for every trial via the OR-NULL clause in list_conversion_factors.
# (iso3, display_label, multiplier)
COUNTRY_FACTORS = [
    ("USA", "United States",  "1.00"),
    ("GBR", "United Kingdom", "0.92"),
    ("DEU", "Germany",        "0.95"),
    ("JPN", "Japan",          "1.35"),
    ("IND", "India",          "0.45"),
    ("BRA", "Brazil",         "0.55"),
    ("AUS", "Australia",      "1.05"),
    ("POL", "Poland",         "0.60"),
]

# ---------------------------------------------------------------------------

async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)  # type: ignore[call-overload]

    async with async_session() as session:
        async with session.begin():
            # ----------------------------------------------------------------
            # 1. Cost elements + FMV versions
            # ----------------------------------------------------------------
            inserted_elements = 0
            inserted_versions = 0

            for (code, name, category, el_type, cost_type, unit, ta, base_amount) in ELEMENTS:
                # Check/insert element
                row = await session.execute(
                    text("SELECT id FROM cost_element WHERE code = :code"),
                    {"code": code}
                )
                existing_el = row.fetchone()
                if existing_el:
                    eid = str(existing_el[0])
                    # Update metadata fields on existing elements in case they were created before these columns existed
                    await session.execute(
                        text("""
                            UPDATE cost_element
                            SET element_type = :el_type, cost_type = :cost_type, unit = :unit,
                                therapeutic_area = :ta, category = :category
                            WHERE id = :eid AND (element_type IS NULL OR element_type != :el_type)
                        """),
                        {"eid": eid, "el_type": el_type, "cost_type": cost_type, "unit": unit, "ta": ta, "category": category}
                    )
                else:
                    result = await session.execute(
                        text("""
                            INSERT INTO cost_element
                                (code, name, category, element_type, cost_type, unit, therapeutic_area, is_active)
                            VALUES
                                (:code, :name, :category, :el_type, :cost_type, :unit, :ta, TRUE)
                            RETURNING id
                        """),
                        {
                            "code": code, "name": name, "category": category,
                            "el_type": el_type, "cost_type": cost_type,
                            "unit": unit, "ta": ta,
                        }
                    )
                    eid = str(result.fetchone()[0])
                    inserted_elements += 1

                # Check/insert FMV version into element_cost_version (not cost_element_version)
                ver_row = await session.execute(
                    text("""
                        SELECT id FROM element_cost_version
                        WHERE element_id = :eid AND version_label = 'FMV 2026 Q1'
                    """),
                    {"eid": eid}
                )
                if not ver_row.fetchone():
                    await session.execute(
                        text("""
                            INSERT INTO element_cost_version
                                (element_id, version_label, base_unit_cost, reference_currency, effective_from)
                            VALUES
                                (:eid, 'FMV 2026 Q1', :amount, 'USD', '2026-01-01')
                        """),
                        {"eid": eid, "amount": base_amount}
                    )
                    inserted_versions += 1

            print(f"[OK] Cost elements: {inserted_elements} inserted, {len(ELEMENTS) - inserted_elements} already existed")
            print(f"[OK] FMV versions:   {inserted_versions} inserted")

            # ----------------------------------------------------------------
            # 2. Conversion factor types
            # ----------------------------------------------------------------
            inserted_ft = 0
            for (code, name, mode, desc) in FACTOR_TYPES:
                row = await session.execute(
                    text("SELECT id FROM conversion_factor_type WHERE code = :code"),
                    {"code": code}
                )
                if row.fetchone():
                    continue
                await session.execute(
                    text("""
                        INSERT INTO conversion_factor_type (code, name, mode, description)
                        VALUES (:code, :name, :mode, :desc)
                    """),
                    {"code": code, "name": name, "mode": mode, "desc": desc}
                )
                inserted_ft += 1

            skipped_ft = len(FACTOR_TYPES) - inserted_ft
            print(f"[OK] Factor types:   {inserted_ft} inserted, {skipped_ft} already existed")

            # ----------------------------------------------------------------
            # 3. Country conversion factors (one row per ISO3, trial_id NULL)
            # ----------------------------------------------------------------
            country_ft_row = await session.execute(
                text("SELECT id FROM conversion_factor_type WHERE code = 'COUNTRY'")
            )
            country_ft_id = country_ft_row.scalar()
            inserted_cf = 0
            skipped_cf = 0
            if country_ft_id is None:
                print("[WARN] COUNTRY factor_type missing — skipping country factor rows")
            else:
                for (iso3, label, value) in COUNTRY_FACTORS:
                    existing = await session.execute(
                        text("""
                            SELECT 1 FROM conversion_factor
                            WHERE factor_type_id = :ft AND country_code = :iso3
                              AND trial_id IS NULL AND site_id IS NULL
                            LIMIT 1
                        """),
                        {"ft": country_ft_id, "iso3": iso3},
                    )
                    if existing.fetchone():
                        skipped_cf += 1
                        continue
                    await session.execute(
                        text("""
                            INSERT INTO conversion_factor
                                (factor_type_id, country_code, value, label, scope_level)
                            VALUES
                                (:ft, :iso3, :value, :label, 'GLOBAL')
                        """),
                        {"ft": country_ft_id, "iso3": iso3, "value": value, "label": label},
                    )
                    inserted_cf += 1
            print(f"[OK] Country factors: {inserted_cf} inserted, {skipped_cf} already existed")

    await engine.dispose()
    print("[DONE] Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
