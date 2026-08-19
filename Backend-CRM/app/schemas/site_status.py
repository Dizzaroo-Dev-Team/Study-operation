"""Site status dashboard schemas and per-status metadata validation."""
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ValidationError

from app.models import PrimarySiteStatus


class UnderEvaluationMetadata(BaseModel):
    """Secondary status fields for UNDER_EVALUATION phase."""

    identified: bool
    cda_status: Literal["SENT", "SIGNED"]
    sfq_status: Literal["SENT", "RECEIVED"]
    sqv_status: Literal["SCHEDULED", "COMPLETED"]
    sqv_outcome: Literal["SELECTED", "NOT_SELECTED", "HOLD"]


class StartupMetadata(BaseModel):
    """Secondary status fields for STARTUP phase."""

    cta_status: Literal["INITIATED", "SIGNED"]
    ethics_status: Literal["NOT_SUBMITTED", "SUBMITTED", "APPROVED", "QUERY_RECEIVED", "REJECTED"]
    essential_documents_collected: bool


class InitiatingMetadata(BaseModel):
    """Secondary status fields for INITIATING phase."""

    siv_kit_dispatched: bool
    study_material_available: bool
    ip_available: bool
    non_ip_available: bool
    siv_date: date
    siv_completed: bool


class InitiatedNotRecruitingMetadata(BaseModel):
    """Secondary status fields for INITIATED_NOT_RECRUITING phase."""

    initiation_completed_at: datetime
    recruitment_blockers: List[str]


class RecruitingMetadata(BaseModel):
    """Secondary status fields for RECRUITING phase."""

    recruitment_enabled_at: datetime


class ActiveNotRecruitingMetadata(BaseModel):
    """Secondary status fields for ACTIVE_NOT_RECRUITING phase."""

    enrollment_closed_at: datetime


class CompletedMetadata(BaseModel):
    """Secondary status fields for COMPLETED phase."""

    all_subjects_completed_at: datetime


class ClosedMetadata(BaseModel):
    """Secondary status fields for CLOSED phase."""

    close_out_visit_date: date


SECONDARY_STATUS_MODELS: Dict[PrimarySiteStatus, Any] = {
    PrimarySiteStatus.UNDER_EVALUATION: UnderEvaluationMetadata,
    PrimarySiteStatus.STARTUP: StartupMetadata,
    PrimarySiteStatus.INITIATING: InitiatingMetadata,
    PrimarySiteStatus.INITIATED_NOT_RECRUITING: InitiatedNotRecruitingMetadata,
    PrimarySiteStatus.RECRUITING: RecruitingMetadata,
    PrimarySiteStatus.ACTIVE_NOT_RECRUITING: ActiveNotRecruitingMetadata,
    PrimarySiteStatus.COMPLETED: CompletedMetadata,
    PrimarySiteStatus.CLOSED: ClosedMetadata,
    # SUSPENDED and TERMINATED deliberately have no extra metadata schema
}


def validate_site_status_metadata(
    status: PrimarySiteStatus,
    raw_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Validate secondary status metadata for a given primary status.

    Uses strict Pydantic schemas that mirror the clinical trial definition
    (e.g. CDA/SFQ/SQV milestones, ethics/CTA, SIV, recruitment, close-out).
    Raises ValidationError on invalid shapes or values.
    """

    if raw_metadata is None:
        raw_metadata = {}

    model = SECONDARY_STATUS_MODELS.get(status)
    if model is None:
        # No structured schema for this status (e.g. SUSPENDED, TERMINATED)
        # Still ensure JSON-serialisable by forcing a shallow copy.
        return dict(raw_metadata)

    try:
        obj = model(**raw_metadata)
    except ValidationError as exc:
        # Re-raise so callers can turn this into a 4xx or audit event.
        raise exc
    return obj.model_dump()


class SiteStatusHistoryEntry(BaseModel):
    status: PrimarySiteStatus
    previous_status: Optional[PrimarySiteStatus] = None
    metadata: Optional[Dict[str, Any]] = None
    changed_at: datetime
    triggering_event: Optional[str] = None
    reason: Optional[str] = None


class SiteStatusDetail(BaseModel):
    site_id: str  # internal UUID
    site_external_id: Optional[str] = None
    study_id: Optional[str] = None  # Study.study_id string
    name: str
    country: Optional[str] = None
    current_status: Optional[PrimarySiteStatus] = None
    previous_status: Optional[PrimarySiteStatus] = None
    secondary_statuses: Optional[Dict[str, Any]] = None
    history: List[SiteStatusHistoryEntry] = []


class CountryStatusSummary(BaseModel):
    country: str
    status: Optional[PrimarySiteStatus] = None
    total_sites: int
    recruiting_sites: int
    status_counts: Dict[PrimarySiteStatus, int]
