"""
Single source of truth for the oncology cost-element master catalog.

Both `app.modules.site_budgeting.seed_data` (additive idempotent seed) and
`scripts.replace_cost_catalog` (one-shot wipe-and-replace) import from here, so
the catalog never drifts between the two paths.

Tuple shape:
    (code, name, category, subcategory, payment_type, user_cost_type, unit, base_cost_usd, pass_thru)

- `payment_type` is what shows in the frontend "Payment Type" column and is
  stored as `cost_element.unit_of_measure`.
- `subcategory`, `unit`, and `pass_thru` are encoded into `cost_element.description`.
- `cost_element.cost_type` is derived (see `derive_cost_type`) because the enum
  only supports PER_VISIT | PER_PATIENT | FIXED | MILESTONE | PASS_THROUGH.
"""
from __future__ import annotations

from decimal import Decimal

VERSION_LABEL = "FMV-2026"

CATEGORIES: list[str] = [
    "REGULATORY",
    "SITE INITIATION",
    "PER-PATIENT",
    "SCREEN FAILURE",
    "IMAGING",
    "BIOMARKERS",
    "PK/ADA",
    "ONCOLOGY-SPECIFIC",
    "SAFETY",
    "MONITORING",
    "DATA MGMT",
    "CLOSE-OUT",
    "PERSONNEL",
    "OVERHEAD",
    "DRUG ACCOUNTABILITY",
    "ARCHIVAL",
]


ELEMENTS: list[tuple[str, str, str, str, str, str, str, Decimal, str]] = [
    # ── REGULATORY ──
    ("REG-001", "IRB/IEC Initial Submission Fee", "REGULATORY", "IRB/Ethics", "ONCE", "FIXED", "Per Document", Decimal("2500"), "Y"),
    ("REG-002", "IRB Annual Continuing Review", "REGULATORY", "IRB/Ethics", "ANNUAL", "FIXED", "Per Submission", Decimal("1200"), "Y"),
    ("REG-003", "IRB Protocol Amendment Fee", "REGULATORY", "IRB/Ethics", "PER EVENT", "FIXED", "Per Amendment", Decimal("750"), "Y"),
    ("REG-004", "CTA/IND Filing Fee (Country)", "REGULATORY", "Reg Authority", "ONCE", "FIXED", "Lump Sum", Decimal("4800"), "Y"),
    ("REG-005", "Regulatory Document Preparation", "REGULATORY", "Regulatory", "ONCE", "FIXED", "Per Package", Decimal("1800"), "N"),
    # ── SITE INITIATION ──
    ("INIT-001", "Site Qualification Visit (SQV)", "SITE INITIATION", "Site Activation", "ONCE", "FIXED", "Lump Sum", Decimal("2800"), "N"),
    ("INIT-002", "Site Initiation Visit (SIV)", "SITE INITIATION", "Site Activation", "ONCE", "FIXED", "Lump Sum", Decimal("3200"), "N"),
    ("INIT-003", "Site Setup / Admin Fee", "SITE INITIATION", "Admin", "ONCE", "FIXED", "Lump Sum", Decimal("1500"), "N"),
    ("INIT-004", "Pharmacy Setup Fee", "SITE INITIATION", "Pharmacy", "ONCE", "FIXED", "Lump Sum", Decimal("1200"), "N"),
    ("INIT-005", "Staff GCP Training (Initial)", "SITE INITIATION", "Training", "ONCE", "FIXED", "Per Staff", Decimal("350"), "N"),
    # ── PER-PATIENT (Visits) ──
    ("VISIT-001", "Screening Visit (Composite)", "PER-PATIENT", "Visits", "PER PATIENT", "VARIABLE", "Per Visit", Decimal("850"), "N"),
    ("VISIT-002", "Baseline Visit (Composite)", "PER-PATIENT", "Visits", "PER PATIENT", "VARIABLE", "Per Visit", Decimal("680"), "N"),
    ("VISIT-003", "Treatment Visit – Cycle 1", "PER-PATIENT", "Visits", "PER PATIENT", "VARIABLE", "Per Visit", Decimal("1200"), "N"),
    ("VISIT-004", "Treatment Visit – Cycles 2–6", "PER-PATIENT", "Visits", "PER VISIT", "VARIABLE", "Per Visit", Decimal("950"), "N"),
    ("VISIT-005", "Treatment Visit – Cycle 7+", "PER-PATIENT", "Visits", "PER VISIT", "VARIABLE", "Per Visit", Decimal("800"), "N"),
    ("VISIT-006", "End-of-Treatment Visit", "PER-PATIENT", "Visits", "PER PATIENT", "VARIABLE", "Per Visit", Decimal("750"), "N"),
    ("VISIT-007", "30-Day Safety Follow-up", "PER-PATIENT", "Visits", "PER PATIENT", "VARIABLE", "Per Visit", Decimal("450"), "N"),
    ("VISIT-008", "Long-term Follow-up (Annual)", "PER-PATIENT", "Visits", "ANNUAL", "VARIABLE", "Per Year", Decimal("280"), "N"),
    ("VISIT-009", "Unscheduled/Urgent Visit", "PER-PATIENT", "Visits", "PER EVENT", "VARIABLE", "Per Event", Decimal("480"), "N"),
    # ── SCREEN FAILURE ──
    ("SF-001", "Screen Failure Fee", "SCREEN FAILURE", "Screen Failure", "PER PATIENT", "VARIABLE", "Per Patient", Decimal("450"), "N"),
    # ── IMAGING ──
    ("IMG-001", "CT Scan (Oncology Multi-region)", "IMAGING", "Radiology", "PER VISIT", "VARIABLE", "Per Scan", Decimal("1850"), "Y"),
    ("IMG-002", "MRI Whole Body/Target Lesion", "IMAGING", "Radiology", "PER VISIT", "VARIABLE", "Per Scan", Decimal("2200"), "Y"),
    ("IMG-003", "PET-CT (Baseline/On-treatment)", "IMAGING", "Nuclear Med", "PER VISIT", "VARIABLE", "Per Scan", Decimal("3800"), "Y"),
    ("IMG-004", "RECIST 1.1 Assessment (Radiologist)", "IMAGING", "RECIST", "PER VISIT", "VARIABLE", "Per Read", Decimal("285"), "N"),
    ("IMG-005", "Independent Central Imaging Review", "IMAGING", "BICR", "PER VISIT", "VARIABLE", "Per Time-Point", Decimal("420"), "Y"),
    ("IMG-006", "MUGA Scan / Echo (Cardiac Safety)", "IMAGING", "Cardiology", "PER VISIT", "VARIABLE", "Per Scan", Decimal("850"), "Y"),
    # ── BIOMARKERS ──
    ("BIO-001", "ctDNA NGS (Tumor-informed)", "BIOMARKERS", "ctDNA", "PER SAMPLE", "VARIABLE", "Per Sample", Decimal("1850"), "Y"),
    ("BIO-002", "ctDNA NGS (Tumor-agnostic)", "BIOMARKERS", "ctDNA", "PER SAMPLE", "VARIABLE", "Per Sample", Decimal("980"), "Y"),
    ("BIO-003", "PD-L1 IHC Testing", "BIOMARKERS", "IHC", "PER SAMPLE", "VARIABLE", "Per Sample", Decimal("380"), "Y"),
    ("BIO-004", "TMB Assessment (Tumor Mutational Burden)", "BIOMARKERS", "NGS", "PER SAMPLE", "VARIABLE", "Per Sample", Decimal("1200"), "Y"),
    ("BIO-005", "Multiplex Cytokine Panel", "BIOMARKERS", "Cytokines", "PER SAMPLE", "VARIABLE", "Per Sample", Decimal("420"), "Y"),
    # ── PK/ADA ──
    ("PK-001", "PK Sample Collection (per time-point)", "PK/ADA", "PK", "PER SAMPLE", "VARIABLE", "Per Time-Point", Decimal("85"), "N"),
    ("PK-002", "ADA Screening Assay", "PK/ADA", "Immunogenicity", "PER SAMPLE", "VARIABLE", "Per Sample", Decimal("280"), "Y"),
    ("PK-003", "Neutralizing Antibody (NAb) Assay", "PK/ADA", "Immunogenicity", "PER SAMPLE", "VARIABLE", "Per Sample", Decimal("420"), "Y"),
    # ── ONCOLOGY-SPECIFIC ──
    ("ONC-001", "Infusion Chair Time (per hour)", "ONCOLOGY-SPECIFIC", "Infusion", "PER HOUR", "VARIABLE", "Per Hour", Decimal("185"), "N"),
    ("ONC-002", "Extended Infusion Chair (>6h)", "ONCOLOGY-SPECIFIC", "Infusion", "PER HOUR", "VARIABLE", "Per Hour (add-on)", Decimal("95"), "N"),
    ("ONC-003", "Cytotoxic Drug Preparation", "ONCOLOGY-SPECIFIC", "Pharmacy", "PER DOSE", "VARIABLE", "Per Dose", Decimal("185"), "N"),
    ("ONC-004", "Leukapheresis Procedure", "ONCOLOGY-SPECIFIC", "CAR-T", "PER PATIENT", "VARIABLE", "Per Session", Decimal("4200"), "Y"),
    ("ONC-005", "CAR-T Infusion Administration", "ONCOLOGY-SPECIFIC", "CAR-T", "PER PATIENT", "VARIABLE", "Per Infusion", Decimal("2500"), "N"),
    ("ONC-006", "CRS Monitoring (Inpatient, per day)", "ONCOLOGY-SPECIFIC", "CAR-T Safety", "PER DAY", "VARIABLE", "Per Day", Decimal("850"), "N"),
    ("ONC-007", "Fresh Core Biopsy (Tumor)", "ONCOLOGY-SPECIFIC", "Biopsy", "PER PATIENT", "VARIABLE", "Per Procedure", Decimal("1200"), "Y"),
    ("ONC-008", "Archival Tissue Retrieval (FFPE)", "ONCOLOGY-SPECIFIC", "Pathology", "PER PATIENT", "VARIABLE", "Per Block", Decimal("180"), "Y"),
    ("ONC-009", "Central Pathology Review", "ONCOLOGY-SPECIFIC", "Pathology", "PER PATIENT", "VARIABLE", "Per Case", Decimal("650"), "Y"),
    ("ONC-010", "irAE Management (per event)", "ONCOLOGY-SPECIFIC", "Safety", "PER EVENT", "VARIABLE", "Per Event", Decimal("1200"), "N"),
    ("ONC-011", "Radiation Therapy Review", "ONCOLOGY-SPECIFIC", "Radiation Onc", "PER PATIENT", "VARIABLE", "Per Review", Decimal("950"), "N"),
    # ── SAFETY ──
    ("SAF-001", "SAE Reporting (Initial + Follow-up)", "SAFETY", "SAE", "PER EVENT", "VARIABLE", "Per SAE", Decimal("320"), "N"),
    ("SAF-002", "DSMB Meeting (per meeting)", "SAFETY", "DSMB", "PER EVENT", "FIXED", "Per Meeting", Decimal("8500"), "N"),
    # ── MONITORING ──
    ("MON-001", "On-site Monitoring Visit (OSV)", "MONITORING", "SDV", "PER VISIT", "VARIABLE", "Per Visit", Decimal("2200"), "N"),
    ("MON-002", "Remote SDR (per hour)", "MONITORING", "SDR", "PER HOUR", "VARIABLE", "Per Hour", Decimal("185"), "N"),
    # ── DATA MGMT ──
    ("DATA-001", "EDC Data Entry Support (per month)", "DATA MGMT", "EDC", "MONTHLY", "FIXED", "Per Month", Decimal("380"), "N"),
    ("DATA-002", "Query Response (per query)", "DATA MGMT", "Queries", "PER EVENT", "VARIABLE", "Per Query", Decimal("45"), "N"),
    # ── CLOSE-OUT ──
    ("CLO-001", "Site Close-out Visit (COV)", "CLOSE-OUT", "COV", "ONCE", "FIXED", "Lump Sum", Decimal("2500"), "N"),
    # ── PERSONNEL ──
    ("PERS-001", "Principal Investigator (per hour)", "PERSONNEL", "PI", "PER HOUR", "VARIABLE", "Per Hour", Decimal("425"), "N"),
    ("PERS-002", "Sub-Investigator / Oncologist (per hour)", "PERSONNEL", "Sub-I", "PER HOUR", "VARIABLE", "Per Hour", Decimal("325"), "N"),
    ("PERS-003", "Study Coordinator (per hour)", "PERSONNEL", "Coordinator", "PER HOUR", "VARIABLE", "Per Hour", Decimal("95"), "N"),
    ("PERS-004", "Research Nurse (per hour)", "PERSONNEL", "Nurse", "PER HOUR", "VARIABLE", "Per Hour", Decimal("125"), "N"),
    ("PERS-005", "Oncology Pharmacist (per hour)", "PERSONNEL", "Pharmacist", "PER HOUR", "VARIABLE", "Per Hour", Decimal("165"), "N"),
    # ── OVERHEAD ──
    ("OVH-001", "Institutional Overhead (% of directs)", "OVERHEAD", "Overhead", "PERCENTAGE", "FIXED", "% of Total Directs", Decimal("20"), "N"),
    ("OVH-002", "Site Administrative Overhead", "OVERHEAD", "Admin", "MONTHLY", "FIXED", "Per Month", Decimal("650"), "N"),
    # ── DRUG ACCOUNTABILITY ──
    ("OVH-003", "IMP Storage (Temperature-monitored)", "DRUG ACCOUNTABILITY", "Storage", "MONTHLY", "FIXED", "Per Month", Decimal("150"), "N"),
    # ── ARCHIVAL ──
    ("ARC-001", "Archival", "ARCHIVAL", "TMF", "ANNUAL", "FIXED", "Per Box/Year", Decimal("85"), "Y"),
    ("ARC-002", "Biobank Sample Storage (per sample/year)", "ARCHIVAL", "Biobank", "ANNUAL", "FIXED", "Per Sample/Year", Decimal("45"), "Y"),
]


def derive_cost_type(user_cost_type: str, payment_type: str, pass_thru: str) -> str:
    """Map (Pass-Thru, Cost Type, Payment Type) → cost_element.cost_type enum.

    Enum: PER_VISIT | PER_PATIENT | FIXED | MILESTONE | PASS_THROUGH.
    Pass-Thru=Y wins (regulatory/imaging/biomarker reimbursables).
    FIXED preserves user intent. VARIABLE PER PATIENT → PER_PATIENT, else PER_VISIT.
    """
    if pass_thru == "Y":
        return "PASS_THROUGH"
    if user_cost_type == "FIXED":
        return "FIXED"
    if payment_type == "PER PATIENT":
        return "PER_PATIENT"
    return "PER_VISIT"


def build_description(subcategory: str, unit: str, user_cost_type: str, pass_thru: str) -> str:
    """Pack the master spreadsheet's auxiliary columns into the description blob.

    Cost Type is the user's FIXED/VARIABLE label (independent of the enum stored
    in `cost_element.cost_type`, which is derived for backend math).
    """
    return (
        f"Subcategory: {subcategory} | Unit: {unit} | "
        f"Cost Type: {user_cost_type} | Pass-Thru: {pass_thru}"
    )
