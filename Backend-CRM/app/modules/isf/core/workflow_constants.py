from enum import Enum


class WorkflowState(str, Enum):
    INTAKE = "INTAKE"
    QC_VALIDATION = "QC_VALIDATION"
    REVIEW_PREPARATION = "REVIEW_PREPARATION"
    IN_REVIEW = "IN_REVIEW"
    PRE_APPROVAL = "PRE_APPROVAL"
    APPROVAL = "APPROVAL"
    ACTIVATION = "ACTIVATION"
    MONITORING = "MONITORING"
    REVISION = "REVISION"
    OBSOLETE = "OBSOLETE"
    ARCHIVED = "ARCHIVED"


class WorkflowRouteType(str, Enum):
    SERIAL = "SERIAL"
    PARALLEL = "PARALLEL"


class WorkflowEscalationMethod(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    SYSTEM = "SYSTEM"
    NONE = "NONE"


class WorkflowEscalationLevel(str, Enum):
    DOCUMENT_OWNER = "DOCUMENT_OWNER"
    STUDY_LEAD = "STUDY_LEAD"
    QUALITY_MANAGER = "QUALITY_MANAGER"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class WorkflowStageStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


class WorkflowOverallStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class WorkflowDistributionStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class WorkflowTrainingStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class RejectionCategory(str, Enum):
    INCOMPLETE_METADATA = "INCOMPLETE_METADATA"
    INCORRECT_CLASSIFICATION = "INCORRECT_CLASSIFICATION"
    QUALITY_ISSUE = "QUALITY_ISSUE"
    COMPLIANCE_ISSUE = "COMPLIANCE_ISSUE"
    CONTENT_ERROR = "CONTENT_ERROR"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    SECURITY_CONCERN = "SECURITY_CONCERN"
    OTHER = "OTHER"


# Default workflow stages configuration
DEFAULT_REVIEW_STAGES = [
    {
        "key": "medical-review",
        "name": "Medical Review",
        "role": "Medical Monitor",
        "type": WorkflowRouteType.SERIAL,
        "assignees": ["Medical Monitor"],
        "status": WorkflowStageStatus.PENDING,
        "sla_hours": 48
    },
    {
        "key": "qa-review",
        "name": "Regulatory QA Review",
        "role": "Regulatory QA Manager",
        "type": WorkflowRouteType.SERIAL,
        "assignees": ["Regulatory QA Manager"],
        "status": WorkflowStageStatus.PENDING,
        "sla_hours": 48
    }
]


DEFAULT_APPROVAL_STAGES = [
    {
        "key": "clinical-operations",
        "name": "Clinical Operations Approval",
        "role": "Principal Investigator",
        "assignees": ["Principal Investigator"],
        "status": WorkflowStageStatus.PENDING,
        "meaning": "Approve for site distribution",
        "requirements": ["21 CFR Part 11 signature"],
        "escalation_hours": 24
    },
    {
        "key": "qa-release",
        "name": "Quality Release",
        "role": "QA Director",
        "assignees": ["QA Director"],
        "status": WorkflowStageStatus.PENDING,
        "meaning": "Release for controlled distribution",
        "requirements": ["Audit trail review"],
        "escalation_hours": 24
    }
]


def _to_camel(s: str) -> str:
    """Convert snake_case to camelCase."""
    parts = s.split("_")
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])


def _dict_to_camel(d: dict) -> dict:
    """Recursively convert dict keys from snake_case to camelCase. Leaves values unchanged."""
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in d.items():
        new_k = _to_camel(k) if isinstance(k, str) and "_" in k else k
        if isinstance(v, dict):
            out[new_k] = _dict_to_camel(v)
        elif isinstance(v, list):
            out[new_k] = [_dict_to_camel(x) if isinstance(x, dict) else x for x in v]
        else:
            out[new_k] = v
    return out


def build_default_isf_workflow(document: dict = None) -> dict:
    """Build default ISF workflow object matching Node.js buildDefaultISFWorkflow. Returns camelCase for MongoDB/frontend."""
    document = document or {}
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Review stages with camelCase keys (Node uses slaHours, dueDate, etc.)
    review_stages = [
        {"key": "medical-review", "name": "Medical Review", "role": "Medical Monitor", "type": "SERIAL",
         "assignees": ["Medical Monitor"], "status": "PENDING", "slaHours": 48, "dueDate": None,
         "escalationNotifiedAt": None, "comments": [], "attachments": []},
        {"key": "qa-review", "name": "Regulatory QA Review", "role": "Regulatory QA Manager", "type": "SERIAL",
         "assignees": ["Regulatory QA Manager"], "status": "PENDING", "slaHours": 48, "dueDate": None,
         "escalationNotifiedAt": None, "comments": [], "attachments": []}
    ]
    approval_stages = [
        {"key": "clinical-operations", "name": "Clinical Operations Approval", "role": "Principal Investigator",
         "assignees": ["Principal Investigator"], "status": "PENDING", "meaning": "Approve for site distribution",
         "requirements": ["21 CFR Part 11 signature"], "escalationHours": 24, "dueDate": None,
         "escalationNotifiedAt": None, "comments": [], "attachments": []},
        {"key": "qa-release", "name": "Quality Release", "role": "QA Director", "assignees": ["QA Director"],
         "status": "PENDING", "meaning": "Release for controlled distribution", "requirements": ["Audit trail review"],
         "escalationHours": 12, "dueDate": None, "escalationNotifiedAt": None, "comments": [], "attachments": []}
    ]

    return {
        "lifecycleState": "INTAKE",
        "previousState": None,
        "initializedAt": now,
        "lastTransitionAt": now,
        "status": "ACTIVE",
        "stateHistory": [
            {"fromState": None, "toState": "INTAKE", "changedAt": now, "notes": "Workflow initialised"}
        ],
        "intake": {
            "ingestionMethod": "MANUAL_UPLOAD",
            "sourceSystem": None,
            "metadataConfidence": 0,
            "duplicateCheck": {"status": "CLEAR", "matchedDocumentId": None, "checkedAt": None},
            "virusScan": {"status": "CLEAN", "scannedAt": None, "engine": None},
            "extractedMetadata": {
                "protocolId": document.get("protocolId") or None,
                "siteId": document.get("site") or None,
                "tmfArtifact": document.get("tmfReference") or document.get("tmf_reference") or None
            },
            "metadataVerification": {
                "zoneVerified": False, "sectionVerified": False, "artifactVerified": False, "subArtifactVerified": False,
                "verifiedAt": None, "verifiedBy": None
            },
            "markComplete": False,
            "notes": None,
            "updatedAt": None,
            "rejection": {
                "isRejected": False, "rejectedAt": None, "rejectedBy": None, "rejectedByName": None, "reason": None,
                "category": "OTHER", "returnToStage": None, "actionRequired": None, "dueDate": None,
                "resolvedAt": None, "resolvedBy": None, "resolutionNotes": None
            }
        },
        "qcValidation": {
            "status": "NOT_STARTED",
            "startedAt": None,
            "completedAt": None,
            "updatedAt": None,
            "updatedBy": None,
            "checklist": {
                "intakeReportReviewed": False, "metadataVerified": False, "securityChecksConfirmed": False,
                "duplicateCleared": False, "virusScanReviewed": False, "packageComplete": False
            },
            "reviewStages": [],
            "sponsorPersons": [],
            "markComplete": False,
            "auditLog": [],
            "rejection": {
                "isRejected": False, "rejectedAt": None, "rejectedBy": None, "rejectedByName": None, "reason": None,
                "category": "OTHER", "returnToStage": None, "actionRequired": None, "dueDate": None,
                "resolvedAt": None, "resolvedBy": None, "resolutionNotes": None
            }
        },
        "review": {
            "overallStatus": "NOT_STARTED",
            "startedAt": None,
            "completedAt": None,
            "route": {
                "type": "SERIAL",
                "slaHours": 72,
                "escalationMethod": "EMAIL",
                "escalationLevel": "QUALITY_MANAGER",
                "escalationRecipients": [],
                "notifyBeforeHours": 24
            },
            "supportingMaterials": [],
            "stages": review_stages
        },
        "approval": {
            "overallStatus": "NOT_STARTED",
            "startedAt": None,
            "completedAt": None,
            "route": {
                "type": "SERIAL",
                "slaHours": 48,
                "escalationMethod": "EMAIL",
                "escalationLevel": "STUDY_LEAD",
                "escalationRecipients": [],
                "notifyBeforeHours": 12
            },
            "eSignature": {"provider": None, "manifestId": None, "completedAt": None, "certificateUrl": None},
            "stages": approval_stages
        },
        "reviewPreparation": {"status": "NOT_STARTED", "startedAt": None, "completedAt": None},
        "activation": {
            "reviewDate": None,
            "plannedEffectiveDate": document.get("documentDate") or document.get("document_date") or None,
            "actualEffectiveDate": None,
            "status": "INACTIVE",
            "isActive": False,
            "distributionStatus": "NOT_STARTED",
            "trainingStatus": "NOT_STARTED",
            "controlledCopies": {"issued": 0, "acknowledged": 0, "lastIssuedAt": None},
            "dateEditComment": None,
            "distributionList": [],
            "acknowledgements": [],
            "trainingAssignments": [],
            "notes": None,
            "publishedAt": None,
            "publishedBy": None,
            "retiredAt": None,
            "retiredBy": None,
            "retireReason": None
        },
        "archive": {"archivedAt": None, "archivedBy": None, "bundleLocation": None, "manifestUrl": None, "reason": None},
        "auditTrail": [],
        "rejectionHistory": [],
        "metrics": {
            "reviewProgress": 0,
            "approvalProgress": 0,
            "overdueCount": 0,
            "cycleTimeDays": 0,
            "auditReadiness": 0,
            "complianceScore": 0,
            "lastEvaluatedAt": now
        },
        "compliance": {
            "training": {"required": True, "assignments": 0, "completed": 0, "dueDate": None},
            "distribution": {"controlledCopies": 0, "pendingAcknowledgements": 0, "lastRun": None},
            "regulatory": {"tmfCompleteness": 0, "lastInspection": None, "issuesOpen": 0},
            "validation": {"aiValidation": "UNKNOWN", "metadataCompleteness": "0%", "checksum": "UNKNOWN"}
        }
    }


def build_workflow_summary(workflow: dict) -> dict:
    """Build workflow summary from workflow doc (Node buildWorkflowSummary). Returns camelCase."""
    w = workflow or {}
    metrics = w.get("metrics") or {}
    return {
        "lifecycleState": w.get("lifecycleState") or "INTAKE",
        "reviewOverallStatus": (w.get("review") or {}).get("overallStatus") or "NOT_STARTED",
        "approvalOverallStatus": (w.get("approval") or {}).get("overallStatus") or "NOT_STARTED",
        "metrics": {
            "reviewProgress": metrics.get("reviewProgress", 0),
            "approvalProgress": metrics.get("approvalProgress", 0),
            "auditReadiness": metrics.get("auditReadiness", metrics.get("complianceScore", 0)),
            "overdueCount": metrics.get("overdueCount", 0)
        },
        "lastTransitionAt": w.get("lastTransitionAt") or w.get("initializedAt")
    }


def calculate_workflow_metrics(workflow: dict) -> dict:
    """Calculate workflow metrics (Node calculateWorkflowMetrics). Returns camelCase."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not workflow:
        return {"reviewProgress": 0, "approvalProgress": 0, "overdueCount": 0, "cycleTimeDays": 0, "lastEvaluatedAt": now}
    review_stages = (workflow.get("review") or {}).get("stages") or []
    approval_stages = (workflow.get("approval") or {}).get("stages") or []
    review_completed = sum(1 for s in review_stages if (s.get("status") or "").upper() == "COMPLETED")
    approval_completed = sum(1 for s in approval_stages if (s.get("status") or "").upper() in ("COMPLETED", "SIGNED"))
    review_progress = round((review_completed / len(review_stages)) * 100) if review_stages else 0
    approval_progress = round((approval_completed / len(approval_stages)) * 100) if approval_stages else 0
    try:
        now_ts = now.timestamp() if hasattr(now, "timestamp") else 0
        overdue = 0
        for s in review_stages + approval_stages:
            due = s.get("dueDate")
            if not due:
                continue
            status = (s.get("status") or "").upper()
            if status == "COMPLETED":
                continue
            due_ts = due.timestamp() if hasattr(due, "timestamp") else (due if isinstance(due, (int, float)) else None)
            if due_ts is not None and due_ts < now_ts:
                overdue += 1
    except Exception:
        overdue = 0
    first_history = (workflow.get("stateHistory") or [None])[0]
    cycle_time = 0.0
    if first_history and first_history.get("changedAt"):
        try:
            changed = first_history["changedAt"]
            if hasattr(changed, "timestamp"):
                cycle_time = max((now.timestamp() - changed.timestamp()) / (24 * 3600), 0)
        except Exception:
            pass
    return {
        "reviewProgress": review_progress,
        "approvalProgress": approval_progress,
        "overdueCount": overdue,
        "cycleTimeDays": cycle_time,
        "lastEvaluatedAt": now
    }
