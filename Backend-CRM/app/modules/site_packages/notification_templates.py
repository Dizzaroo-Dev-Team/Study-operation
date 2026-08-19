"""
Submission template registry backed by MongoDB.

Holds the template data that drives the Site Packages create flows:
  - the 7 submission types (labels + descriptions for the step-1 cards)
  - per-submission-type required document sets (Amendment, Continuing Review,
    Safety Report, Study Closure, Protocol Deviation)
  - the Notification wizard registry (categories, notification types with
    fields + documents + due-day timelines, and the reusable field library)

The collections are auto-seeded from the defaults below on first access, after
which MongoDB is the source of truth — templates can be edited there (or via
future admin endpoints) without a code deploy.

Collections:
  - submission_types            {name, description, workflow, order}
  - submission_type_documents   {submissionType, documents: [...], order}
  - notification_categories     {id, color, order}
  - notification_types          {typeId, category, name, fields, fieldLabelOverrides,
                                 documents, dueDays, active, order}
  - notification_field_library  {key, label, type, options?}

Note: `max_files` uses 10000 to mean "unlimited" (Mongo/JSON cannot store
Infinity); the frontend converts values >= 10000 back to Infinity.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.db.mongo import get_mongo_db

logger = logging.getLogger(__name__)

SUBMISSION_TYPES_COLLECTION = "submission_types"
WORKFLOW_DOCS_COLLECTION = "submission_type_documents"
CATEGORIES_COLLECTION = "notification_categories"
TYPES_COLLECTION = "notification_types"
FIELDS_COLLECTION = "notification_field_library"

UNLIMITED_FILES = 10_000

# ---------------------------------------------------------------------------
# Default submission types (step-1 cards)
# ---------------------------------------------------------------------------
DEFAULT_SUBMISSION_TYPES: List[Dict[str, Any]] = [
    {"name": "Initial Submission", "description": "First-time application package for a new study site.", "workflow": "irb"},
    {"name": "Amendment / Modification Package", "description": "Protocol, ICF, or material changes requiring re-approval.", "workflow": "fixed"},
    {"name": "Continuing Review / (Annual Renewal)", "description": "Periodic renewal to keep an active study in good standing.", "workflow": "fixed"},
    {"name": "Safety Report Submission / Package", "description": "SAE, SUSAR, and other safety-related reporting.", "workflow": "fixed"},
    {"name": "Protocol Deviation / Violation Package", "description": "Documentation for deviations or violations from protocol.", "workflow": "fixed"},
    {"name": "Study Closure Package", "description": "Final reporting and archival for a completed study.", "workflow": "fixed"},
    {"name": "Notification", "description": "Site, study, and administrative notifications.", "workflow": "notification"},
]

# ---------------------------------------------------------------------------
# Default per-submission-type document sets (mirrors the frontend lists)
# ---------------------------------------------------------------------------
DEFAULT_WORKFLOW_DOCUMENTS: Dict[str, List[Dict[str, Any]]] = {
    "Amendment / Modification Package": [
        {"name": "Summary of Changes", "requirement": "Mandatory", "description": "Required", "type": "summary_of_changes", "max_files": 1, "uploadAllowed": True},
        {"name": "Amended Protocol (clean + tracked/redline)", "requirement": "Conditional", "description": "Multiple files allowed", "type": "amended_protocol_clean_tracked", "max_files": UNLIMITED_FILES, "uploadAllowed": True},
        {"name": "Updated ICF (if applicable)", "requirement": "Conditional", "description": "Multiple files allowed", "type": "updated_icf", "max_files": UNLIMITED_FILES, "uploadAllowed": True},
        {"name": "Revised Recruitment Materials", "requirement": "Conditional", "description": "Multiple files allowed", "type": "revised_recruitment_materials", "max_files": UNLIMITED_FILES, "uploadAllowed": True},
        {"name": "Updated IB (if safety/efficacy changes)", "requirement": "Conditional", "description": "Single file", "type": "updated_ib_safety_efficacy", "max_files": 1, "uploadAllowed": True},
        {"name": "Impact Assessment (risk/benefit)", "requirement": "Conditional", "description": "Single file", "type": "impact_assessment_risk_benefit", "max_files": 1, "uploadAllowed": True},
        {"name": "Updated Questionnaires or CRFs", "requirement": "Conditional", "description": "Multiple files allowed", "type": "updated_questionnaires_crfs", "max_files": UNLIMITED_FILES, "uploadAllowed": True},
    ],
    "Continuing Review / (Annual Renewal)": [
        {"name": "Progress Report / Status Summary", "requirement": "Mandatory", "description": "Single file", "type": "progress_report_status_summary", "max_files": 1, "uploadAllowed": True},
        {"name": "Site Enrollment Numbers", "requirement": "Mandatory", "description": "Single file", "type": "site_enrollment_numbers", "max_files": 1, "uploadAllowed": True},
        {"name": "Safety Summary (AE/SAE overview)", "requirement": "Mandatory", "description": "Single file", "type": "safety_summary_ae_sae_overview", "max_files": 1, "uploadAllowed": True},
        {"name": "Protocol Deviation / Violation Log Summary", "requirement": "Mandatory", "description": "Single file", "type": "protocol_deviation_violation_log_summary", "max_files": 1, "uploadAllowed": True},
        {"name": "Updated Risk-Benefit Assessment", "requirement": "Mandatory", "description": "Single file", "type": "updated_risk_benefit_assessment", "max_files": 1, "uploadAllowed": True},
        {"name": "Current ICF (latest approved version)", "requirement": "Conditional", "description": "Multiple files allowed", "type": "current_icf_latest_approved_version", "max_files": UNLIMITED_FILES, "uploadAllowed": True},
        {"name": "Current IRB Approval Letter", "requirement": "Mandatory", "description": "Single file", "type": "current_irb_approval_letter", "max_files": 1, "uploadAllowed": True},
        {"name": "Publication Summary (if any)", "requirement": "Conditional", "description": "Multiple files allowed", "type": "publication_summary_if_any", "max_files": UNLIMITED_FILES, "uploadAllowed": True},
    ],
    "Safety Report Submission / Package": [
        {"name": "SAE Report / SUSAR Report", "requirement": "Mandatory", "description": "Multiple files allowed", "type": "sae_report_susar_report", "max_files": UNLIMITED_FILES, "uploadAllowed": True},
        {"name": "Narrative Report", "requirement": "Mandatory", "description": "Single file", "type": "narrative_report", "max_files": 1, "uploadAllowed": True},
        {"name": "Causality Assessment", "requirement": "Mandatory", "description": "Single file", "type": "causality_assessment", "max_files": 1, "uploadAllowed": True},
        {"name": "Line Listing", "requirement": "Mandatory", "description": "Single file", "type": "line_listing", "max_files": 1, "uploadAllowed": True},
        {"name": "DSMB Recommendations", "requirement": "Mandatory", "description": "Single file", "type": "dsmb_recommendations", "max_files": 1, "uploadAllowed": True},
        {"name": "Updated IB", "requirement": "Mandatory", "description": "Single file", "type": "updated_ib", "max_files": 1, "uploadAllowed": True},
    ],
    "Study Closure Package": [
        {"name": "Final Study Report / Close-Out Report", "requirement": "Mandatory", "description": "Single file", "type": "final_study_report_close_out_report", "max_files": 1, "uploadAllowed": True},
        {"name": "Enrollment Summary (final)", "requirement": "Mandatory", "description": "Single file", "type": "enrollment_summary_final", "max_files": 1, "uploadAllowed": True},
        {"name": "Safety Summary (cumulative)", "requirement": "Mandatory", "description": "Single file", "type": "safety_summary_cumulative", "max_files": 1, "uploadAllowed": True},
        {"name": "Deviations Summary", "requirement": "Mandatory", "description": "Single file", "type": "deviations_summary", "max_files": 1, "uploadAllowed": True},
        {"name": "Publication Status", "requirement": "Mandatory", "description": "Multiple files allowed", "type": "publication_status", "max_files": UNLIMITED_FILES, "uploadAllowed": True},
        {"name": "IRB Closure Acknowledgment Letter", "requirement": "Mandatory", "description": "Single file", "type": "irb_closure_acknowledgment_letter", "max_files": 1, "uploadAllowed": True},
        {"name": "Drug/Device Accountability Records", "requirement": "Mandatory", "description": "Multiple files allowed", "type": "drug_device_accountability_records", "max_files": UNLIMITED_FILES, "uploadAllowed": True},
        {"name": "Archival Plan Statement", "requirement": "Mandatory", "description": "Single file", "type": "archival_plan_statement", "max_files": 1, "uploadAllowed": True},
        {"name": "Final Study Financial Disclosure Log", "requirement": "Mandatory", "description": "Multiple files allowed", "type": "final_study_financial_disclosure_log", "max_files": UNLIMITED_FILES, "uploadAllowed": True},
    ],
    "Protocol Deviation / Violation Package": [
        {"name": "Cover Letter", "requirement": "Mandatory", "description": "Generate the protocol deviation notification cover letter", "type": "protocol_deviation_cover_letter", "max_files": 1, "uploadAllowed": True},
        {"name": "Deviation Report Form", "requirement": "Mandatory", "description": "Single file", "type": "deviation_report_form", "max_files": 1, "uploadAllowed": True},
        {"name": "Root Cause Analysis", "requirement": "Mandatory", "description": "Single file", "type": "root_cause_analysis", "max_files": 1, "uploadAllowed": True},
        {"name": "CAPA (Corrective and Preventive Actions)", "requirement": "Mandatory", "description": "Single file", "type": "capa_corrective_preventive_actions", "max_files": 1, "uploadAllowed": True},
        {"name": "Impact on Subject Safety/Data Integrity", "requirement": "Mandatory", "description": "Single file", "type": "impact_subject_safety_data_integrity", "max_files": 1, "uploadAllowed": True},
        {"name": "PI Acknowledgement / Memo to File (MTF)", "requirement": "Mandatory", "description": "Multiple files allowed", "type": "pi_acknowledgement_memo_to_file_mtf", "max_files": UNLIMITED_FILES, "uploadAllowed": True},
    ],
}

# ---------------------------------------------------------------------------
# Default field library (mirrors the frontend FIELD_LIBRARY)
# ---------------------------------------------------------------------------
DEFAULT_FIELD_LIBRARY: Dict[str, Dict[str, Any]] = {
    "personName": {"label": "Person Name", "type": "text"},
    "role": {"label": "Role", "type": "text"},
    "previousValue": {"label": "Previous Value", "type": "text"},
    "newValue": {"label": "New Value", "type": "text"},
    "effectiveDate": {"label": "Effective Date", "type": "date"},
    "startDate": {"label": "Start Date", "type": "date"},
    "endDate": {"label": "End Date / Expected Resume Date", "type": "date"},
    "reason": {"label": "Reason", "type": "textarea"},
    "delegationLogUpdated": {"label": "Delegation Log Updated", "type": "yesno"},
    "trainingCompleted": {"label": "Training Completed", "type": "yesno"},
    "irbRequired": {"label": "IRB/IEC Notification Required", "type": "yesno"},
    "regulatoryRequired": {"label": "Regulatory Notification Required", "type": "yesno"},
    "subjectsImpacted": {"label": "Subjects Impacted", "type": "number"},
    "subjectsAffected": {"label": "Subjects Affected", "type": "number"},
    "sponsorApproval": {"label": "Sponsor Approval", "type": "yesno"},
    "enrollmentStatus": {"label": "Enrollment Status", "type": "select", "options": ["Open", "Paused", "Closed"]},
    "impImpact": {"label": "IMP Impact", "type": "textarea"},
    "safetyImpact": {"label": "Safety Impact", "type": "textarea"},
    "description": {"label": "Description", "type": "textarea"},
    "severityGrade": {"label": "Severity / Grade", "type": "select", "options": ["Minor", "Moderate", "Major", "Critical"]},
    "actionTaken": {"label": "Action Taken", "type": "textarea"},
    "reportedToAuthority": {"label": "Reported to Authority", "type": "yesno"},
    "transitionPlan": {"label": "Transition Plan", "type": "textarea"},
    "storageLocation": {"label": "Storage Location", "type": "text"},
    "excursionRange": {"label": "Temperature Excursion Range", "type": "text"},
    "excursionDuration": {"label": "Excursion Duration (hours)", "type": "number"},
    "delayDays": {"label": "Delay (days)", "type": "number"},
    "facilityName": {"label": "Facility / Entity Name", "type": "text"},
    "equipmentDetails": {"label": "Equipment Details", "type": "textarea"},
    "milestoneDate": {"label": "Milestone Date", "type": "date"},
    "subjectsEnrolledToDate": {"label": "Subjects Enrolled to Date", "type": "number"},
    "comments": {"label": "Comments", "type": "textarea"},
}

# ---------------------------------------------------------------------------
# Default categories and notification type names
# ---------------------------------------------------------------------------
DEFAULT_CATEGORIES: List[Dict[str, Any]] = [
    {"id": "Personnel", "color": "blue", "names": ["Principal Investigator Change", "Sub Investigator Added", "Sub Investigator Removed", "Study Coordinator Added", "Study Coordinator Removed", "Pharmacist Changed", "Laboratory Staff Change", "Radiologist Added", "Delegation Log Update", "CV Update", "Medical License Renewal", "GCP Certificate Update"]},
    {"id": "Site", "color": "violet", "names": ["Site Address Change", "Telephone Change", "Email Change", "Site Expansion", "New Facility Added", "Pharmacy Changed", "Laboratory Changed", "Imaging Facility Changed", "Equipment Upgrade", "New Satellite Clinic", "Site Temporarily Closed", "Site Reopened"]},
    {"id": "Study", "color": "emerald", "names": ["Recruitment Started", "Recruitment Paused", "Recruitment Restarted", "Enrollment Completed", "First Patient In", "Last Patient In", "Last Patient Last Visit", "Temporary Study Hold", "Study Restart", "Sponsor Contact Changed", "DSMB Recommendation", "Administrative Update"]},
    {"id": "Safety", "color": "rose", "names": ["Urgent Safety Measure", "New Risk Identified", "Safety Communication", "SUSAR Notification", "DSMB Recommendation", "IB Safety Update", "Safety Letter Distribution"]},
    {"id": "Laboratory", "color": "cyan", "names": ["Local Lab Changed", "Central Lab Changed", "Sample Processing Change", "Reference Range Updated", "Equipment Calibration", "Lab Closure", "New Lab Added"]},
    {"id": "Pharmacy", "color": "amber", "names": ["Pharmacy Changed", "New Pharmacist", "IMP Storage Location", "Temperature Excursion Notification", "IMP Shipment Delay", "Pharmacy Closure"]},
    {"id": "Vendor", "color": "orange", "names": ["CRO Change", "Imaging Vendor", "Laboratory Vendor", "Courier Vendor", "ePRO Vendor", "IRT Vendor", "ECG Vendor", "Central Reading Vendor"]},
    {"id": "Regulatory", "color": "indigo", "names": ["IRB/IEC Approval Renewal", "Regulatory Authority Notification", "Protocol Amendment Notification", "ICF Version Update", "Annual Report Submission"]},
    {"id": "Administrative", "color": "slate", "names": ["Contact Information Update", "Document Filing Update", "Insurance Certificate Update", "Contract Amendment", "Miscellaneous Administrative Update"]},
    {"id": "Other", "color": "teal", "names": ["Other / Custom Notification"]},
]

DUE_DAYS_BY_CATEGORY: Dict[str, int] = {
    "Personnel": 15, "Site": 15, "Study": 10, "Safety": 2, "Laboratory": 15,
    "Pharmacy": 7, "Vendor": 15, "Regulatory": 30, "Administrative": 30, "Other": 30,
}


def _auto_fields(name: str, category: str) -> List[str]:
    n = name.lower()
    if category == "Personnel":
        if "added" in n:
            return ["personName", "role", "effectiveDate", "delegationLogUpdated", "trainingCompleted", "comments"]
        if "removed" in n:
            return ["personName", "role", "effectiveDate", "reason", "delegationLogUpdated", "comments"]
        return ["previousValue", "newValue", "effectiveDate", "reason", "irbRequired", "regulatoryRequired", "subjectsImpacted", "comments"]
    if category == "Site":
        if "temporarily closed" in n:
            return ["reason", "startDate", "endDate", "subjectsAffected", "comments"]
        if "reopened" in n:
            return ["effectiveDate", "reason", "comments"]
        if "expansion" in n or "new facility" in n or "satellite" in n:
            return ["facilityName", "effectiveDate", "description", "equipmentDetails", "comments"]
        if "equipment" in n:
            return ["facilityName", "equipmentDetails", "effectiveDate", "comments"]
        return ["previousValue", "newValue", "effectiveDate", "reason", "irbRequired", "regulatoryRequired", "comments"]
    if category == "Study":
        if "hold" in n:
            return ["reason", "startDate", "endDate", "sponsorApproval", "subjectsAffected", "enrollmentStatus", "impImpact", "safetyImpact"]
        if "restart" in n:
            return ["effectiveDate", "sponsorApproval", "enrollmentStatus", "comments"]
        if "dsmb" in n:
            return ["milestoneDate", "description", "actionTaken", "reportedToAuthority", "comments"]
        if "sponsor contact" in n:
            return ["previousValue", "newValue", "effectiveDate", "comments"]
        if "administrative" in n:
            return ["description", "effectiveDate", "comments"]
        return ["milestoneDate", "subjectsEnrolledToDate", "comments"]
    if category == "Safety":
        return ["description", "severityGrade", "startDate", "actionTaken", "subjectsAffected", "reportedToAuthority", "comments"]
    if category == "Laboratory":
        if "closure" in n:
            return ["reason", "startDate", "endDate", "comments"]
        if "calibration" in n or "reference range" in n:
            return ["facilityName", "effectiveDate", "description", "comments"]
        return ["previousValue", "newValue", "effectiveDate", "reason", "comments"]
    if category == "Pharmacy":
        if "closure" in n:
            return ["reason", "startDate", "endDate", "comments"]
        if "temperature excursion" in n:
            return ["storageLocation", "excursionRange", "excursionDuration", "startDate", "actionTaken", "comments"]
        if "shipment delay" in n:
            return ["delayDays", "startDate", "reason", "impImpact", "comments"]
        if "storage location" in n:
            return ["storageLocation", "effectiveDate", "reason", "comments"]
        if "new pharmacist" in n:
            return ["personName", "effectiveDate", "comments"]
        return ["previousValue", "newValue", "effectiveDate", "reason", "comments"]
    if category == "Vendor":
        return ["previousValue", "newValue", "effectiveDate", "reason", "transitionPlan", "comments"]
    if category == "Regulatory":
        return ["effectiveDate", "description", "regulatoryRequired", "comments"]
    if category == "Administrative":
        return ["description", "effectiveDate", "comments"]
    return ["description", "comments"]


def _auto_documents(name: str, category: str) -> List[str]:
    n = name.lower()
    if category == "Personnel":
        if "added" in n:
            return ["Notification Letter", "CV", "GCP Certificate", "Medical License", "Delegation Log"]
        if "removed" in n:
            return ["Notification Letter", "Delegation Log Update"]
        return ["Notification Letter", "Updated CV", "Delegation Log"]
    if category == "Site":
        if "temporarily closed" in n:
            return ["Closure Notification Letter", "Subject Transfer Plan"]
        if "reopened" in n:
            return ["Reopening Notification Letter", "Facility Readiness Confirmation"]
        if "expansion" in n or "new facility" in n or "satellite" in n:
            return ["Facility Notification Letter", "Facility Inspection Report", "Equipment List"]
        return ["Notification Letter", "Updated Site Information Form"]
    if category == "Study":
        if "hold" in n:
            return ["Sponsor Letter", "Hold Justification", "Risk Assessment", "Safety Assessment", "Subject Communication", "IMP Management Plan"]
        if "restart" in n:
            return ["Restart Notification Letter", "Sponsor Approval"]
        if "dsmb" in n:
            return ["DSMB Recommendation Letter", "Sponsor Response"]
        return ["Milestone Notification Letter"]
    if category == "Safety":
        if "susar" in n:
            return ["SUSAR Report Form", "Investigator Notification Letter", "Regulatory Submission Confirmation"]
        return ["Safety Notification Letter", "Event Description Report"]
    if category == "Laboratory":
        if "closure" in n:
            return ["Closure Notification Letter", "Sample Transfer Plan"]
        return ["Notification Letter", "Updated Lab Certification"]
    if category == "Pharmacy":
        if "closure" in n:
            return ["Closure Notification Letter", "IMP Transfer Plan"]
        if "temperature excursion" in n:
            return ["Excursion Report", "Temperature Log", "IMP Impact Assessment"]
        return ["Notification Letter"]
    if category == "Vendor":
        return ["Notification Letter", "Vendor Qualification Documentation", "Transition Plan"]
    if category == "Regulatory":
        return ["Notification Letter", "Supporting Regulatory Documentation"]
    return ["Notification Letter"]


# Spec-exact overrides (mirrors the frontend registry)
TYPE_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "Principal Investigator Change": {
        "fieldLabelOverrides": {"previousValue": "Current PI", "newValue": "New PI"},
        "documents": ["Notification Letter", "Updated CV", "Medical License", "GCP Certificate", "Financial Disclosure", "Delegation Log", "PI Signature", "Sponsor Approval"],
    },
    "Temporary Study Hold": {
        "fieldLabelOverrides": {"endDate": "Expected Resume Date"},
    },
    "Study Coordinator Added": {
        "fieldLabelOverrides": {"personName": "Coordinator Name"},
    },
}


def build_default_types() -> List[Dict[str, Any]]:
    types: List[Dict[str, Any]] = []
    counter = 0
    for cat in DEFAULT_CATEGORIES:
        for name in cat["names"]:
            counter += 1
            t: Dict[str, Any] = {
                "typeId": f"NTYPE-{counter:03d}",
                "category": cat["id"],
                "name": name,
                "fields": _auto_fields(name, cat["id"]),
                "fieldLabelOverrides": {},
                "documents": _auto_documents(name, cat["id"]),
                "dueDays": DUE_DAYS_BY_CATEGORY[cat["id"]],
                "active": True,
                "order": counter,
            }
            override = TYPE_OVERRIDES.get(name)
            if override:
                t.update(override)
            types.append(t)
    return types


# Natural key per collection — used for the unique index and upsert filters,
# so concurrent seeding (two requests both seeing an empty collection) cannot
# produce duplicates.
_UNIQUE_KEYS = {
    SUBMISSION_TYPES_COLLECTION: "name",
    WORKFLOW_DOCS_COLLECTION: "submissionType",
    TYPES_COLLECTION: "typeId",
    CATEGORIES_COLLECTION: "id",
    FIELDS_COLLECTION: "key",
}

_indexes_ensured = False


async def _ensure_unique_indexes(db) -> None:
    global _indexes_ensured
    if _indexes_ensured:
        return
    for coll, key in _UNIQUE_KEYS.items():
        try:
            await db[coll].create_index(key, unique=True, name=f"{key}_unique")
        except Exception as e:
            # Existing duplicates block index creation; seeding still works,
            # just without the DB-level duplicate guard.
            logger.warning("[NotificationTemplates] Could not create unique index on %s.%s: %s", coll, key, e)
    _indexes_ensured = True


async def _upsert_seed(db, collection: str, key: str, docs: List[Dict[str, Any]], label: str) -> None:
    """Seed via per-key upserts ($setOnInsert): idempotent and race-safe."""
    if await db[collection].count_documents({}) > 0:
        return
    from pymongo import UpdateOne

    ops = [UpdateOne({key: d[key]}, {"$setOnInsert": d}, upsert=True) for d in docs]
    try:
        result = await db[collection].bulk_write(ops, ordered=False)
        if result.upserted_count:
            logger.info("[NotificationTemplates] Seeded %d %s", result.upserted_count, label)
    except Exception as e:
        # Duplicate-key errors from a concurrent seeder are benign.
        logger.warning("[NotificationTemplates] Seeding %s hit conflicts (concurrent seed?): %s", label, e)


async def _seed_if_empty(db) -> None:
    """Idempotent: seed the registry collections when they are empty."""
    await _ensure_unique_indexes(db)
    await _upsert_seed(
        db,
        SUBMISSION_TYPES_COLLECTION,
        "name",
        [{**t, "order": i} for i, t in enumerate(DEFAULT_SUBMISSION_TYPES)],
        "submission types",
    )
    await _upsert_seed(
        db,
        WORKFLOW_DOCS_COLLECTION,
        "submissionType",
        [
            {"submissionType": st_name, "documents": docs, "order": i}
            for i, (st_name, docs) in enumerate(DEFAULT_WORKFLOW_DOCUMENTS.items())
        ],
        "workflow document sets",
    )
    await _upsert_seed(db, TYPES_COLLECTION, "typeId", [dict(t) for t in build_default_types()], "notification types")
    await _upsert_seed(
        db,
        CATEGORIES_COLLECTION,
        "id",
        [{"id": c["id"], "color": c["color"], "order": i} for i, c in enumerate(DEFAULT_CATEGORIES)],
        "categories",
    )
    await _upsert_seed(
        db,
        FIELDS_COLLECTION,
        "key",
        [{"key": k, **v} for k, v in DEFAULT_FIELD_LIBRARY.items()],
        "field definitions",
    )


async def get_notification_registry() -> Dict[str, Any]:
    """Return {categories, types, fieldLibrary} from Mongo, seeding defaults on first use."""
    db = await get_mongo_db()
    await _seed_if_empty(db)

    categories = await (
        db[CATEGORIES_COLLECTION].find({}, {"_id": 0}).sort("order", 1).to_list(length=200)
    )
    types = await (
        db[TYPES_COLLECTION]
        .find({"active": {"$ne": False}}, {"_id": 0})
        .sort("order", 1)
        .to_list(length=2000)
    )
    field_docs = await db[FIELDS_COLLECTION].find({}, {"_id": 0}).to_list(length=500)
    field_library = {
        d["key"]: {k: v for k, v in d.items() if k != "key"} for d in field_docs if d.get("key")
    }
    submission_types = await (
        db[SUBMISSION_TYPES_COLLECTION].find({}, {"_id": 0}).sort("order", 1).to_list(length=50)
    )
    workflow_docs = await db[WORKFLOW_DOCS_COLLECTION].find({}, {"_id": 0}).to_list(length=50)
    workflow_documents = {
        d["submissionType"]: d.get("documents") or []
        for d in workflow_docs
        if d.get("submissionType")
    }

    return {
        "categories": categories,
        "types": types,
        "fieldLibrary": field_library,
        "submissionTypes": submission_types,
        "workflowDocuments": workflow_documents,
    }


# ---------------------------------------------------------------------------
# Workflow requirements lookup for services.py (progress computation).
# Mongo-backed with a short in-process cache; falls back to the defaults.
# ---------------------------------------------------------------------------
_WORKFLOW_CACHE: Dict[str, Any] = {"map": None, "ts": 0.0}
_WORKFLOW_CACHE_TTL_SECONDS = 60.0


async def _workflow_documents_map() -> Dict[str, List[Dict[str, Any]]]:
    now = time.monotonic()
    if _WORKFLOW_CACHE["map"] is not None and (now - _WORKFLOW_CACHE["ts"]) < _WORKFLOW_CACHE_TTL_SECONDS:
        return _WORKFLOW_CACHE["map"]
    try:
        db = await get_mongo_db()
        await _seed_if_empty(db)
        docs = await db[WORKFLOW_DOCS_COLLECTION].find({}, {"_id": 0}).to_list(length=50)
        mapping = {
            d["submissionType"]: d.get("documents") or []
            for d in docs
            if d.get("submissionType")
        }
        if mapping:
            _WORKFLOW_CACHE["map"] = mapping
            _WORKFLOW_CACHE["ts"] = now
            return mapping
    except Exception as e:
        # Mongo down → serve defaults, and cache them for one TTL so hot paths
        # (list progress) don't pay a connection timeout on every request.
        logger.warning("[NotificationTemplates] Workflow docs lookup failed, using defaults: %s", e)
    _WORKFLOW_CACHE["map"] = DEFAULT_WORKFLOW_DOCUMENTS
    _WORKFLOW_CACHE["ts"] = now
    return DEFAULT_WORKFLOW_DOCUMENTS


async def workflow_requirements_for(submission_type: Optional[str]) -> List[Dict[str, Any]]:
    """Required-document list for a submission type (Mongo-backed, cached).

    Returns [] for submission types without a fixed workflow list
    (Initial Submission → IRB-driven; Notification → wizard-driven).
    """
    raw = str(submission_type or "").strip()
    if raw == "Safety Report":
        raw = "Safety Report Submission / Package"
    mapping = await _workflow_documents_map()
    return [dict(r) for r in (mapping.get(raw) or [])]
