from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import IRB, IRBRequiredDocument

router = APIRouter()


async def resolve_requirements_for_irb(db: AsyncSession, irb: IRB) -> List[Dict[str, Any]]:
    """Same requirement rows as GET /irb-requirements for this IRB (used by Site Packages progress, etc.)."""
    # OPTIMIZATION: Normalize strings once instead of 8x per call
    _normalized_code = _normalize_unique_code(getattr(irb, "unique_code", None))
    _normalized_name = _normalize_irb_name(irb.name)

    if _is_heidelberg_medical_faculty_ec_cached(irb, _normalized_name, _normalized_code):
        return _heidelberg_medical_faculty_ec_requirements()

    if _is_peter_mac_hrec_cached(irb, _normalized_name, _normalized_code):
        return _peter_mac_hrec_requirements()

    if _is_ncc_irb_japan_cached(irb, _normalized_name, _normalized_code):
        return _ncc_irb_japan_requirements()

    if _is_chcams_ethics_committee_cached(irb, _normalized_name, _normalized_code):
        return _chcams_ethics_committee_requirements()

    if _is_md_anderson_irb_cached(irb, _normalized_name, _normalized_code):
        return _md_anderson_irb_requirements()

    if _is_tmc_iec_cached(irb, _normalized_name, _normalized_code):
        return _tmc_iec_requirements()

    if _is_hra_oxford_rec_uk_cached(irb, _normalized_name, _normalized_code):
        return _hra_oxford_rec_uk_requirements()

    if _is_smc_irb_cached(irb, _normalized_name, _normalized_code):
        return _smc_irb_requirements()

    docs_res = await db.execute(
        select(IRBRequiredDocument).where(IRBRequiredDocument.irb_id == irb.id).order_by(IRBRequiredDocument.id.asc())
    )
    docs = docs_res.scalars().all()
    if docs:
        return [
            {
                "name": d.document_name,
                "requirement": "Mandatory" if bool(d.is_mandatory) else "Optional",
                "description": "",
            }
            for d in docs
        ]
    return _default_irb_requirements()

# Normalized (lowercase, collapsed spaces) — Heidelberg University Ethics Committee (Germany)
_HEIDELBERG_MEDICAL_FACULTY_EC_NAME = (
    "heidelberg university ethics committee (germany)"
)

_HEIDELBERG_MEDICAL_FACULTY_EC_LEGACY_NAME = (
    "ethics committee of the medical faculty of heidelberg university"
)

# Stable unique_code values (normalized) for special-case IRBs.
_HEIDELBERG_MEDICAL_FACULTY_EC_CODE = "heidelberg_medical_faculty_ec"

# Peter MacCallum Cancer Centre Human Research Ethics Committee (Peter Mac HREC), Australia
_PETER_MAC_HREC_NAME = (
    "peter maccallum cancer centre human research ethics committee (peter mac hrec), australia"
)
_PETER_MAC_HREC_CODE = "peter_mac_hrec"

# CHCAMS — National Cancer Center / CHCAMS Institutional Ethics Committee (China)
_CHCAMS_ETHICS_COMMITTEE_NAME = (
    "national cancer center / chcams institutional ethics committee"
)
_CHCAMS_ETHICS_COMMITTEE_CODE = "chcams_ethics_committee"

_CHCAMS_ETHICS_COMMITTEE_LEGACY_NAME = (
    "ethics committee of national cancer center / cancer hospital, chinese academy of medical "
    "sciences and peking union medical college (chcams ethics committee)"
)

# MD Anderson Cancer Center IRB (US)
_MD_ANDERSON_IRB_NAME = "md anderson irb"
_MD_ANDERSON_IRB_CODE = "md_anderson_irb"

# Tata Memorial Centre — Institutional Ethics Committee (India)
_TMC_IEC_NAME = "tata memorial centre institutional ethics committee (tmc-iec)"
_TMC_IEC_CODE = "tmc_iec"

# National Cancer Center IRB — Japan (must be matched before CHCAMS China patterns)
_NCC_IRB_JAPAN_NAME = "national cancer center institutional review board (ncc irb), japan"
_NCC_IRB_JAPAN_CODE = "ncc_irb_japan"

# UK — The Oxford Cancer & Heamatology Centre
_HRA_OXFORD_REC_UK_NAME = "the oxford cancer & heamatology centre , united kingdom"
_HRA_OXFORD_REC_UK_CODE = "hra_oxford_rec_uk"

# Samsung Medical Center IRB — South Korea
_SMC_IRB_NAME = "samsung medical center institutional review board (smc irb)"
_SMC_IRB_CODE = "smc_irb"


def _normalize_irb_name(name: Optional[str]) -> str:
    if not name:
        return ""
    return " ".join(str(name).strip().lower().split())


def _normalize_unique_code(code: Optional[str]) -> str:
    if not code:
        return ""
    return "_".join(str(code).strip().lower().split())


# ============================================================================
# OPTIMIZATION: Cached IRB matching functions (receive pre-normalized values)
# ============================================================================

def _is_heidelberg_medical_faculty_ec_cached(irb: IRB, norm_name: str, norm_code: str) -> bool:
    """Cached version - receives pre-normalized values."""
    if norm_code and norm_code == _HEIDELBERG_MEDICAL_FACULTY_EC_CODE:
        return True
    if norm_name in {
        _HEIDELBERG_MEDICAL_FACULTY_EC_NAME,
        _HEIDELBERG_MEDICAL_FACULTY_EC_LEGACY_NAME,
    }:
        return True
    return "heidelberg university" in norm_name and "medical faculty" in norm_name and "ethics committee" in norm_name


def _is_peter_mac_hrec_cached(irb: IRB, norm_name: str, norm_code: str) -> bool:
    """Cached version - receives pre-normalized values."""
    if norm_code and norm_code == _PETER_MAC_HREC_CODE:
        return True
    if norm_name == _PETER_MAC_HREC_NAME:
        return True
    return (
        "peter maccallum" in norm_name
        and "peter mac hrec" in norm_name
        and "human research ethics committee" in norm_name
    )


def _is_ncc_irb_japan_cached(irb: IRB, norm_name: str, norm_code: str) -> bool:
    """Cached version - receives pre-normalized values."""
    if norm_code and norm_code == _NCC_IRB_JAPAN_CODE:
        return True
    if norm_name == _NCC_IRB_JAPAN_NAME:
        return True
    if "ncc irb" in norm_name and "japan" in norm_name:
        return True
    return (
        "national cancer center" in norm_name
        and "institutional review board" in norm_name
        and "japan" in norm_name
    )


def _is_chcams_ethics_committee_cached(irb: IRB, norm_name: str, norm_code: str) -> bool:
    """Cached version - receives pre-normalized values."""
    if norm_code and norm_code == _CHCAMS_ETHICS_COMMITTEE_CODE:
        return True
    if norm_name in {
        _CHCAMS_ETHICS_COMMITTEE_NAME,
        _CHCAMS_ETHICS_COMMITTEE_LEGACY_NAME,
    }:
        return True
    return (
        "chcams ethics committee" in norm_name
        or (
            "chcams" in norm_name
            and "national cancer center" in norm_name
            and "ethics committee" in norm_name
        )
    )


def _is_md_anderson_irb_cached(irb: IRB, norm_name: str, norm_code: str) -> bool:
    """Cached version - receives pre-normalized values."""
    if norm_code and norm_code == _MD_ANDERSON_IRB_CODE:
        return True
    if norm_name == _MD_ANDERSON_IRB_NAME:
        return True
    return (
        "md anderson irb" in norm_name
        or (
            "md anderson cancer center" in norm_name
            and "institutional review board" in norm_name
        )
    )


def _is_tmc_iec_cached(irb: IRB, norm_name: str, norm_code: str) -> bool:
    """Cached version - receives pre-normalized values."""
    if norm_code and norm_code == _TMC_IEC_CODE:
        return True
    if norm_name == _TMC_IEC_NAME:
        return True
    return (
        "tmc-iec" in norm_name
        or (
            "tata memorial" in norm_name
            and "institutional ethics committee" in norm_name
        )
    )


def _is_hra_oxford_rec_uk_cached(irb: IRB, norm_name: str, norm_code: str) -> bool:
    """Cached version - receives pre-normalized values."""
    if norm_code and norm_code == _HRA_OXFORD_REC_UK_CODE:
        return True
    if norm_name == _HRA_OXFORD_REC_UK_NAME:
        return True
    return (
        "south central" in norm_name
        and "oxford" in norm_name
        and "research ethics committee" in norm_name
    ) or (
        "oxford" in norm_name
        and "cancer" in norm_name
        and ("heamatology" in norm_name or "hematology" in norm_name)
        and "united kingdom" in norm_name
    ) or (
        "health research authority" in norm_name
        and "oxford rec" in norm_name
        and "uk" in norm_name
    ) or (
        "hra" in norm_name
        and "south central" in norm_name
        and "oxford" in norm_name
        and "rec" in norm_name
    )


def _is_smc_irb_cached(irb: IRB, norm_name: str, norm_code: str) -> bool:
    """Cached version - receives pre-normalized values."""
    if norm_code and norm_code == _SMC_IRB_CODE:
        return True
    if norm_name == _SMC_IRB_NAME:
        return True
    return "smc irb" in norm_name or (
        "samsung medical center" in norm_name and "institutional review board" in norm_name
    )


# ============================================================================
# Original IRB matching functions (kept for backward compatibility)
# ============================================================================
def _is_heidelberg_medical_faculty_ec(irb: IRB) -> bool:
    """Site Package document list: full override for this IRB only (no default/DB mix)."""
    uc = _normalize_unique_code(getattr(irb, "unique_code", None))
    if uc and uc == _HEIDELBERG_MEDICAL_FACULTY_EC_CODE:
        return True
    n = _normalize_irb_name(irb.name)
    if n == _HEIDELBERG_MEDICAL_FACULTY_EC_NAME:
        return True
    # Allow minor punctuation / wording variants
    return "heidelberg university" in n and "medical faculty" in n and "ethics committee" in n


def _is_peter_mac_hrec(irb: IRB) -> bool:
    """Site Package document list: full override for Peter Mac HREC (no default/DB mix)."""
    uc = _normalize_unique_code(getattr(irb, "unique_code", None))
    if uc and uc == _PETER_MAC_HREC_CODE:
        return True
    n = _normalize_irb_name(irb.name)
    if n == _PETER_MAC_HREC_NAME:
        return True
    return (
        "peter maccallum" in n
        and "peter mac hrec" in n
        and "human research ethics committee" in n
    )


def _is_ncc_irb_japan(irb: IRB) -> bool:
    """Site Package document list: National Cancer Center IRB (NCC), Japan — not CHCAMS China."""
    uc = _normalize_unique_code(getattr(irb, "unique_code", None))
    if uc and uc == _NCC_IRB_JAPAN_CODE:
        return True
    n = _normalize_irb_name(irb.name)
    if n == _NCC_IRB_JAPAN_NAME:
        return True
    if "ncc irb" in n and "japan" in n:
        return True
    return (
        "national cancer center" in n
        and "institutional review board" in n
        and "japan" in n
    )


def _is_chcams_ethics_committee(irb: IRB) -> bool:
    """Site Package document list: CHCAMS / National Cancer Center China ethics committee."""
    uc = _normalize_unique_code(getattr(irb, "unique_code", None))
    if uc and uc == _CHCAMS_ETHICS_COMMITTEE_CODE:
        return True
    n = _normalize_irb_name(irb.name)
    if n == _CHCAMS_ETHICS_COMMITTEE_NAME:
        return True
    return (
        "chcams ethics committee" in n
        or (
            "chcams" in n
            and "national cancer center" in n
            and "ethics committee" in n
        )
    )


def _is_md_anderson_irb(irb: IRB) -> bool:
    """Site Package document list: University of Texas MD Anderson Cancer Center IRB."""
    uc = _normalize_unique_code(getattr(irb, "unique_code", None))
    if uc and uc == _MD_ANDERSON_IRB_CODE:
        return True
    n = _normalize_irb_name(irb.name)
    if n == _MD_ANDERSON_IRB_NAME:
        return True
    return (
        "md anderson irb" in n
        or (
            "md anderson cancer center" in n
            and "institutional review board" in n
        )
    )


def _is_tmc_iec(irb: IRB) -> bool:
    """Site Package document list: Tata Memorial Centre Institutional Ethics Committee (TMC-IEC)."""
    uc = _normalize_unique_code(getattr(irb, "unique_code", None))
    if uc and uc == _TMC_IEC_CODE:
        return True
    n = _normalize_irb_name(irb.name)
    if n == _TMC_IEC_NAME:
        return True
    return (
        "tmc-iec" in n
        or (
            "tata memorial" in n
            and "institutional ethics committee" in n
        )
    )


def _is_hra_oxford_rec_uk(irb: IRB) -> bool:
    """Site Package document list: The Oxford Cancer & Heamatology Centre, United Kingdom."""
    uc = _normalize_unique_code(getattr(irb, "unique_code", None))
    if uc and uc == _HRA_OXFORD_REC_UK_CODE:
        return True
    n = _normalize_irb_name(irb.name)
    if n == _HRA_OXFORD_REC_UK_NAME:
        return True
    return (
        "south central" in n
        and "oxford" in n
        and "research ethics committee" in n
    ) or (
        "oxford" in n
        and "cancer" in n
        and ("heamatology" in n or "hematology" in n)
        and "united kingdom" in n
    ) or (
        "health research authority" in n
        and "oxford rec" in n
        and "uk" in n
    ) or (
        "hra" in n
        and "south central" in n
        and "oxford" in n
        and "rec" in n
    )


def _is_smc_irb(irb: IRB) -> bool:
    """Site Package document list: Samsung Medical Center Institutional Review Board (SMC IRB)."""
    uc = _normalize_unique_code(getattr(irb, "unique_code", None))
    if uc and uc == _SMC_IRB_CODE:
        return True
    n = _normalize_irb_name(irb.name)
    if n == _SMC_IRB_NAME:
        return True
    return "smc irb" in n or (
        "samsung medical center" in n and "institutional review board" in n
    )


# ============================================================================
# OPTIMIZATION: Module-level cached requirement lists (tuples, created once)
# ============================================================================

_HEIDELBERG_REQUIREMENTS_CACHE = (
    {"name": "Cover Letter", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "cover_letter", "source": "manual_upload"},
    {"name": "CTIS Application Form (Part I & II)", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "ctis_application_form_part_i_ii", "source": "manual_upload"},
    {"name": "Proof of Payment / Fee Form", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "proof_of_payment_fee_form", "source": "manual_upload"},
    {"name": "Clinical Trial Protocol", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "clinical_trial_protocol_heidelberg", "source": "isf_only"},
    {"name": "Protocol Synopsis", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "protocol_synopsis", "source": "isf_only"},
    {"name": "Investigator's Brochure (IB)", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "investigator_brochure", "source": "isf_only"},
    {"name": "Investigational Medicinal Product Dossier (IMPD)", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "impd", "source": "isf_only"},
    {"name": "Master ICF", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "master_icf", "source": "isf_only"},
    {"name": "Data Protection Concept", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "data_protection_concept", "source": "isf_only"},
    {"name": "Data Protection Impact Assessment (DPIA / DSFA)", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "dpia_dsfa", "source": "isf_only"},
    {"name": "Patient Diaries / e-PRO / Questionnaires (German)", "requirement": "Conditional", "description": "", "upload_allowed": False, "max_files": 1, "type": "patient_diaries_epro_questionnaires_german", "source": "isf_only"},
    {"name": "Patient Recruitment Materials (German)", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "patient_recruitment_materials_german", "source": "isf_only"},
    {"name": "Site Suitability Declaration", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "site_suitability_declaration", "source": "manual_upload"},
    {"name": "Principal Investigator (PI) CV", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "principal_investigator_cv", "source": "isf_only"},
    {"name": "Sub-Investigator CVs", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "sub_investigator_cvs", "source": "isf_only"},
    {"name": "GCP Training Certificates", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "gcp_training_certificates", "source": "isf_only"},
    {"name": "Conflict of Interest / Financial Disclosure", "requirement": "Mandatory", "description": "", "upload_allowed": True, "type": "conflict_of_interest_financial_disclosure", "source": "manual_upload"},
    {"name": "Certificate of Insurance", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "certificate_of_insurance", "source": "isf_only"},
    {"name": "Insurance Conditions", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "insurance_conditions", "source": "isf_only"},
    {"name": "BfS Radiation Approval / Notification", "requirement": "Conditional", "description": "", "upload_allowed": True, "max_files": 1, "type": "bfs_radiation_approval_notification", "source": "manual_upload"},
)

_PETER_MAC_REQUIREMENTS_CACHE = (
    {"name": "Cover Letter", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "cover_letter", "source": "manual_upload"},
    {"name": "Human Research Ethics Application (HREA) Application Form", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "hrea_application_form", "source": "manual_upload"},
    {"name": "Victorian Specific Module (VSM)", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "vsm", "source": "manual_upload"},
    {"name": "Site Specific Assessment (SSA)", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "ssa", "source": "manual_upload"},
    {"name": "Clinical Trial Protocol", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "clinical_trial_protocol", "source": "isf_only"},
    {"name": "Investigator's Brochure (IB)", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "investigator_brochure", "source": "isf_only"},
    {"name": "Investigational Product (IP) Manual", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "ip_manual", "source": "isf_only"},
    {"name": "Master PICF", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "master_picf", "source": "isf_only"},
    {"name": "e-PRO / Questionnaires / Diaries", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "epro_questionnaires_diaries", "source": "isf_only"},
    {"name": "Patient Recruitment Materials", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "patient_recruitment_materials", "source": "isf_only"},
    {"name": "Radiation Safety Report (RSR)", "requirement": "Conditional", "description": "", "upload_allowed": True, "max_files": 1, "type": "radiation_safety_report", "source": "manual_upload"},
    {"name": "Material Transfer Agreement (MTA)", "requirement": "Conditional", "description": "", "upload_allowed": False, "max_files": 1, "type": "material_transfer_agreement", "source": "isf_only"},
    {"name": "TGA Clinical Trial Notification (CTN)", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "tga_clinical_trial_notification", "source": "manual_upload"},
    {"name": "Principal Investigator (PI) CV", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "principal_investigator_cv", "source": "isf_only"},
    {"name": "PI GCP Training Certificate", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "pi_gcp_training_certificate", "source": "isf_only"},
    {"name": "Conflict of Interest (COI) Form", "requirement": "Mandatory", "description": "", "upload_allowed": True, "type": "conflict_of_interest_form", "source": "manual_upload"},
    {"name": "Medicines Australia Indemnity", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "medicines_australia_indemnity", "source": "isf_only"},
    {"name": "Certificate of Insurance", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "certificate_of_insurance", "source": "isf_only"},
)

_CHCAMS_REQUIREMENTS_CACHE = (
        {"name": "Cover Letter / Submission Letter", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "cover_submission_letter", "source": "manual_upload"},
        {"name": "CHCAMS EC Application Form", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "chcams_ec_application_form", "source": "manual_upload"},
        {"name": "NMPA Clinical Trial Approval / CTA", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "nmpa_clinical_trial_approval_cta", "source": "manual_upload"},
        {"name": "Sponsor & CRO Business Licenses / Qualifications", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "sponsor_cro_business_licenses_qualifications", "source": "isf_only"},
        {"name": "Sponsor Authorization Letter", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "sponsor_authorization_letter", "source": "isf_only"},
        {"name": "Clinical Trial Protocol & Synopsis", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "clinical_trial_protocol_synopsis", "source": "isf_only"},
        {"name": "Investigator's Brochure (IB)", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "investigator_brochure", "source": "isf_only"},
        {"name": "Investigational Product (IP) / Pharmacy Manual", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "investigational_product_pharmacy_manual", "source": "isf_only"},
        {"name": "Drug Quality Inspection Report / CoA", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "drug_quality_inspection_report_coa", "source": "isf_only"},
        {"name": "Master Informed Consent Form (ICF)", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "master_informed_consent_form", "source": "isf_only"},
        {"name": "Case Report Form (CRF) Template", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "case_report_form_template", "source": "isf_only"},
        {"name": "Patient Diaries / e-PRO / Questionnaires", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "patient_diaries_epro_questionnaires", "source": "isf_only"},
        {"name": "Patient Recruitment Materials (Advertisements)", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "patient_recruitment_materials_advertisements", "source": "isf_only"},
        {"name": "Principal Investigator (PI) CV & Medical License", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "pi_cv_medical_license", "source": "isf_only"},
        {"name": "Sub-Investigator CVs & Medical Licenses", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "sub_investigator_cvs_medical_licenses", "source": "isf_only"},
        {"name": "GCP Training Certificates", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "gcp_training_certificates", "source": "isf_only"},
        {"name": "Site Feasibility / Capability Statement", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "site_feasibility_capability_statement", "source": "manual_upload"},
        {"name": "Conflict of Interest (COI) Declarations", "requirement": "Mandatory", "description": "", "upload_allowed": True, "type": "conflict_of_interest_declarations", "source": "manual_upload"},
        {"name": "DSMB / IDMC Charter", "requirement": "Conditional", "description": "", "upload_allowed": False, "max_files": 1, "type": "dsmb_idmc_charter", "source": "isf_only"},
        {"name": "Clinical Trial Agreement (CTA) Draft", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "clinical_trial_agreement_draft", "source": "manual_upload"},
        {"name": "Certificate of Insurance & Compensation Agreement", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "certificate_of_insurance_compensation_agreement", "source": "isf_only"},
        {"name": "HGRAC Approval / Submission Proof", "requirement": "Conditional", "description": "", "upload_allowed": True, "max_files": 1, "type": "hgrac_approval_submission_proof", "source": "manual_upload"},
    )

_MD_ANDERSON_REQUIREMENTS_CACHE = (
    {"name": "Cover Letter", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "cover_letter", "source": "manual_upload"},
    {"name": "IRB Form (SmartForm Data)", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "irb_form_smartform_data", "source": "manual_upload"},
    {"name": "Conflict of Interest (COI) Disclosures", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "conflict_of_interest_coi_disclosures", "source": "isf_only"},
    {"name": "PI & Sub-I CVs and Medical Licenses", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "pi_sub_i_cvs_medical_licenses", "source": "isf_only"},
    {"name": "CITI Training Records", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "citi_training_records", "source": "isf_only"},
    {"name": "Site Good Clinical Practice (GCP) Certificates", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "site_gcp_certificates", "source": "isf_only"},
    {"name": "Departmental Review Board (DRB) Approval", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "departmental_review_board_drb_approval", "source": "manual_upload"},
    {"name": "Scientific Review (PRMC) Approval", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "scientific_review_prmc_approval", "source": "manual_upload"},
    {"name": "Main Clinical Protocol", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "main_clinical_protocol", "source": "isf_only"},
    {"name": "Investigator's Brochure (IB)", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "investigator_brochure", "source": "isf_only"},
    {"name": "Master Informed Consent Form (ICF)", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "master_informed_consent_form_icf", "source": "isf_only"},
    {"name": "IND Approval Documentation", "requirement": "Conditional", "description": "", "upload_allowed": True, "max_files": 1, "type": "ind_approval_documentation", "source": "manual_upload"},
    {"name": "FDA Form 1572 / Investigator Agreement", "requirement": "Conditional", "description": "", "upload_allowed": True, "type": "fda_form_1572_investigator_agreement", "source": "manual_upload"},
    {"name": "Investigational Product (IP) / Pharmacy Manual", "requirement": "Conditional", "description": "", "upload_allowed": False, "max_files": 1, "type": "investigational_product_pharmacy_manual", "source": "isf_only"},
    {"name": "Data and Safety Monitoring Plan (DSMP) / Charter", "requirement": "Conditional", "description": "", "upload_allowed": False, "max_files": 1, "type": "data_and_safety_monitoring_plan_charter", "source": "isf_only"},
    {"name": "Grant Application", "requirement": "Conditional", "description": "", "upload_allowed": True, "max_files": 1, "type": "grant_application", "source": "manual_upload"},
    {"name": "Assent / Short Forms", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "assent_short_forms", "source": "isf_only"},
    {"name": "Patient Diaries / e-PRO / Questionnaires", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "patient_diaries_epro_questionnaires", "source": "isf_only"},
    {"name": "Patient Recruitment Materials", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "patient_recruitment_materials", "source": "isf_only"},
    {"name": "External Site Permission Letters", "requirement": "Conditional", "description": "", "upload_allowed": True, "type": "external_site_permission_letters", "source": "manual_upload"},
    )

_TMC_IEC_REQUIREMENTS_CACHE = (
    {"name": "Cover Letter", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "tmc_cover_letter", "source": "manual_upload"},
    {"name": "IEC Application Form", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "tmc_iec_application_form", "source": "manual_upload"},
    {"name": "Principal Investigator Undertaking", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "tmc_principal_investigator_undertaking", "source": "manual_upload"},
    {"name": "Conflict of Interest (COI) Declaration", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 999, "type": "tmc_coi_declaration", "source": "isf_only"},
    {"name": "Main Clinical Trial Protocol", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "tmc_main_clinical_trial_protocol", "source": "isf_only"},
    {"name": "Master Informed Consent Document (ICD) - English", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 999, "type": "tmc_master_icd_english", "source": "isf_only"},
    {"name": "Translated ICDs", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 999, "type": "tmc_translated_icds", "source": "isf_only"},
    {"name": "Translation Certificates / Back Translations", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 999, "type": "tmc_translation_certificates_back_translations", "source": "isf_only"},
    {"name": "PI & Co-I CVs and Medical Registrations", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 999, "type": "tmc_pi_coi_cvs_medical_registrations", "source": "isf_only"},
    {"name": "Good Clinical Practice (GCP) Certificates", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 999, "type": "tmc_gcp_certificates", "source": "isf_only"},
    {"name": "Clinical Trial Agreement (CTA) / Draft Budget", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "tmc_cta_draft_budget", "source": "manual_upload"},
    {"name": "Insurance Policy / Certificate", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "tmc_insurance_policy_certificate", "source": "isf_only"},
    {"name": "Patient Compensation Formula / Undertaking", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "tmc_patient_compensation_formula_undertaking", "source": "isf_only"},
    {"name": "Investigator's Brochure (IB)", "requirement": "Conditional", "description": "", "upload_allowed": False, "max_files": 1, "type": "tmc_investigators_brochure", "source": "isf_only"},
    {"name": "Patient Diaries / Questionnaires / PROs", "requirement": "Conditional", "description": "", "upload_allowed": False, "max_files": 999, "type": "tmc_patient_diaries_questionnaires_pros", "source": "isf_only"},
    {"name": "Patient Recruitment Materials", "requirement": "Conditional", "description": "", "upload_allowed": False, "max_files": 999, "type": "tmc_patient_recruitment_materials", "source": "isf_only"},
    {"name": "CDSCO / DCGI Approval (NOC)", "requirement": "Conditional", "description": "", "upload_allowed": True, "max_files": 1, "type": "tmc_cdsco_dcgi_approval_noc", "source": "manual_upload"},
    {"name": "CTRI Registration Proof", "requirement": "Conditional", "description": "", "upload_allowed": True, "max_files": 1, "type": "tmc_ctri_registration_proof", "source": "manual_upload"},
    {"name": "HMSC Approval / Proof of Submission", "requirement": "Conditional", "description": "", "upload_allowed": True, "max_files": 1, "type": "tmc_hmsc_approval_submission_proof", "source": "manual_upload"},
)

_NCC_JAPAN_REQUIREMENTS_CACHE = (
        {"name": "Cover Letter", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "cover_letter", "source": "manual_upload"},
        {"name": "IRB Application Form", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "irb_application_form", "source": "manual_upload"},
        {"name": "Clinical Trial Protocol", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "clinical_trial_protocol", "source": "isf_only"},
        {"name": "Protocol Synopsis (Japanese)", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "protocol_synopsis_jp", "source": "isf_only"},
        {"name": "Investigator's Brochure (IB) / PMDA Package Insert", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "investigator_brochure_pmda", "source": "isf_only"},
        {"name": "Investigational Product (IP) Handling Manual", "requirement": "Mandatory", "description": "", "upload_allowed": False, "max_files": 1, "type": "ip_handling_manual", "source": "isf_only"},
        {"name": "Pharmacy/IP Receipt & Storage Plan", "requirement": "Conditional", "description": "", "upload_allowed": True, "max_files": 1, "type": "pharmacy_ip_receipt_storage_plan", "source": "manual_upload"},
        {"name": "Case Report Form (CRF / eCRF)", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "crf_ecrf", "source": "isf_only"},
        {"name": "Participant Information Sheet (PIS) & ICF (Japanese)", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "participant_information_sheet_icf_jp", "source": "isf_only"},
        {"name": "Subject Compensation Rules / Policy (Japanese)", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "subject_compensation_rules_jp", "source": "isf_only"},
        {"name": "Patient Diaries / Questionnaires / PROs (Japanese)", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "patient_diaries_questionnaires_pros_jp", "source": "isf_only"},
        {"name": "Patient Recruitment Materials (Japanese)", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "patient_recruitment_materials_jp", "source": "isf_only"},
        {"name": "PMDA Clinical Trial Notification (CTN)", "requirement": "Conditional", "description": "", "upload_allowed": False, "type": "pmda_clinical_trial_notification", "source": "isf_only"},
        {"name": "Certificate of Sponsor Insurance", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "sponsor_insurance_certificate", "source": "isf_only"},
        {"name": "Clinical Trial Agreement (Draft/Template) & Budget", "requirement": "Mandatory", "description": "", "upload_allowed": True, "type": "clinical_trial_agreement_budget", "source": "manual_upload"},
        {"name": "List of Investigators / Study Personnel", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1, "type": "investigator_list", "source": "manual_upload"},
        {"name": "PI & Sub-Investigator CVs", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "pi_sub_investigator_cvs", "source": "isf_only"},
        {"name": "PI & Sub-Investigator GCP Medical Licenses", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "pi_sub_investigator_gcp_medical_licenses", "source": "isf_only"},
        {"name": "GCP Training Certificates (PI, Sub-Is, CRCs)", "requirement": "Mandatory", "description": "", "upload_allowed": False, "type": "gcp_training_certificates", "source": "isf_only"},
        {"name": "Conflict of Interest (COI) Declarations (PI & Sub-Is)", "requirement": "Mandatory", "description": "", "upload_allowed": True, "type": "conflict_of_interest_declarations", "source": "manual_upload"},
    )

_HRA_OXFORD_REQUIREMENTS_CACHE = (
        {"name": "Integrated Research Application System (IRAS) Form", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1},
        {"name": "Cover Letter", "requirement": "Mandatory", "description": "", "upload_allowed": True, "max_files": 1},
        {"name": "Clinical Trial Protocol", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "Investigator's Brochure (IB)", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "Case Report Form (CRF / eCRF)", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "Data and Safety Monitoring Plan (DSMP)", "requirement": "Conditional", "description": "", "upload_allowed": False},
        {"name": "Summary of Study Design", "requirement": "Conditional", "description": "", "upload_allowed": False},
        {"name": "General Practitioner (GP) Letter - Master Template", "requirement": "Conditional", "description": "", "upload_allowed": True},
        {"name": "Patient Diaries / Questionnaires (PROs)", "requirement": "Conditional", "description": "", "upload_allowed": False},
        {"name": "Recruitment Materials (Posters, Adverts)", "requirement": "Conditional", "description": "", "upload_allowed": False},
        {"name": "Patient Identity Card (Wallet Card)", "requirement": "Conditional", "description": "", "upload_allowed": True},
        {"name": "Participant Information Sheet (PIS) and Consent Form (ICF)", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "Chief Investigator CV & GCP Certificates", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "Proof of Insurance / Indemnity", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "UK Local Information Pack (OID / mCTA)", "requirement": "Conditional", "description": "", "upload_allowed": False},
        {"name": "Schedule of Events Costing Template (SoECAT)", "requirement": "Optional", "description": "", "upload_allowed": True, "max_files": 1},
    )

_SMC_REQUIREMENTS_CACHE = (
        {"name": "eIRB Application Form", "requirement": "Mandatory", "description": "", "upload_allowed": True},
        {"name": "Clinical Trial Protocol", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "Investigator's Brochure (IB)", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "Informed Consent Form (translated into Korean)", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "Cover Letter", "requirement": "Mandatory", "description": "", "upload_allowed": True},
        {"name": "Data and Safety Monitoring Plan (DSMP)", "requirement": "Conditional", "description": "", "upload_allowed": False},
        {"name": "Case Report Form (CRF / eCRF)", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "Subject Compensation Policy / Rules (in Korean)", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "Patient-Facing Materials (Questionnaires)", "requirement": "Conditional", "description": "", "upload_allowed": False},
        {"name": "Clinical Trial Agreement (CTA) / Budget Details", "requirement": "Mandatory", "description": "", "upload_allowed": True},
        {"name": "Biobank / Material Transfer Agreement (MTA)", "requirement": "Conditional", "description": "", "upload_allowed": True},
        {"name": "Sub-Investigator & Site Staff Credentials (CVs, KAGC)", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "MFDS IND Approval Document", "requirement": "Conditional", "description": "", "upload_allowed": False},
        {"name": "Certificate of Insurance (covering Korean subjects)", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "PI CV, Medical License, and KAGC (Korean GCP) Training Certificate", "requirement": "Mandatory", "description": "", "upload_allowed": False},
        {"name": "Conflict of Interest (COI) Declaration", "requirement": "Mandatory", "description": "", "upload_allowed": True},
        {"name": "Recruitment Materials (in Korean)", "requirement": "Conditional", "description": "", "upload_allowed": False},
    )



def _heidelberg_medical_faculty_ec_requirements() -> List[Dict[str, Any]]:
    """Document set for Heidelberg University Ethics Committee (Germany)."""
    return list(_HEIDELBERG_REQUIREMENTS_CACHE)


def _peter_mac_hrec_requirements() -> List[Dict[str, Any]]:
    """Document set for Peter MacCallum Cancer Centre HREC (Australia)."""
    return list(_PETER_MAC_REQUIREMENTS_CACHE)


def _chcams_ethics_committee_requirements() -> List[Dict[str, Any]]:
    """Document set for National Cancer Center / CHCAMS Institutional Ethics Committee (China)."""
    return list(_CHCAMS_REQUIREMENTS_CACHE)


def _md_anderson_irb_requirements() -> List[Dict[str, Any]]:
    """Document set for MD Anderson Cancer Center Institutional Review Board."""
    return list(_MD_ANDERSON_REQUIREMENTS_CACHE)


def _tmc_iec_requirements() -> List[Dict[str, Any]]:
    """Document set for Tata Memorial Centre Institutional Ethics Committee (TMC-IEC), India."""
    return list(_TMC_IEC_REQUIREMENTS_CACHE)


def _ncc_irb_japan_requirements() -> List[Dict[str, Any]]:
    """Document set for National Cancer Center Institutional Review Board (NCC IRB), Japan."""
    return list(_NCC_JAPAN_REQUIREMENTS_CACHE)


def _hra_oxford_rec_uk_requirements() -> List[Dict[str, Any]]:
    """Document set for The Oxford Cancer & Heamatology Centre, United Kingdom."""
    return list(_HRA_OXFORD_REQUIREMENTS_CACHE)


def _smc_irb_requirements() -> List[Dict[str, Any]]:
    """Document set for Samsung Medical Center Institutional Review Board (SMC IRB), South Korea."""
    return list(_SMC_REQUIREMENTS_CACHE)


def _default_irb_requirements() -> List[Dict[str, Any]]:
    # Intentionally not tied to any hardcoded IRB list.
    # This is a baseline set; can be made configurable per IRB later.
    return [
        {"name": "Protocol", "requirement": "Mandatory", "description": "Study protocol document"},
        {"name": "Informed Consent form", "requirement": "Mandatory", "description": "Participant informed consent form"},
        {"name": "Investigators Brochure/ Product Monograph", "requirement": "Mandatory", "description": "Investigator brochure or product monograph"},
        {"name": "Study Budget/ Clinical trial Agreement(CTA)", "requirement": "Mandatory", "description": "Study budget and clinical trial agreement"},
        {"name": "Safety Monitoring Plan", "requirement": "Mandatory", "description": "Safety monitoring and reporting plan"},
        {"name": "Regulatory approvals", "requirement": "Mandatory", "description": "Required regulatory approvals"},
        {"name": "Data management plan", "requirement": "Mandatory", "description": "Plan for data collection and management"},
        {"name": "Principal Investigators CV and other information", "requirement": "Mandatory", "description": "Principal investigator CV and credentials"},
        {"name": "Conflict of Interest Declarations", "requirement": "Mandatory", "description": "Conflict of interest disclosures"},
        {"name": "Recruitment materials", "requirement": "Mandatory", "description": "Participant recruitment materials"},
    ]


@router.get("/irb-requirements")
async def get_irb_requirements(
    irb_id: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(IRB).where(IRB.id == int(irb_id)))
    irb: Optional[IRB] = result.scalar_one_or_none()
    if not irb:
        return {"success": False, "error": "IRB not found"}

    requirements = await resolve_requirements_for_irb(db, irb)
    return {"success": True, "data": {"irb_id": irb.id, "requirements": requirements}}

