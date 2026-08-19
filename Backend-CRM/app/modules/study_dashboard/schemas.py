"""Pydantic response schemas for the study dashboard endpoints."""
from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel


# ─────────────────────────────────────────────────────────────────────────────
# Patient × Visit matrix
# ─────────────────────────────────────────────────────────────────────────────
class PlannedVisit(BaseModel):
    visitnum: float
    visit: str


class MatrixCell(BaseModel):
    # status: "done" | "missed" | "due" | "na"
    status: str
    date: Optional[str] = None  # SVSTDTC of actual visit, ISO yyyy-mm-dd


class SubjectRow(BaseModel):
    usubjid: str
    siteid: Optional[int] = None
    arm: Optional[str] = None
    disposition: Optional[str] = None
    cells: List[MatrixCell]


class PatientVisitMatrixResponse(BaseModel):
    study_id: str
    visits: List[PlannedVisit]
    subjects: List[SubjectRow]
    summary: dict


# ─────────────────────────────────────────────────────────────────────────────
# AE summary (kept for backend smoke / future use; not surfaced in mockup)
# ─────────────────────────────────────────────────────────────────────────────
class AeKpis(BaseModel):
    total_events: int
    subjects_with_ae: int
    serious_events: int
    related_events: int
    fatal_events: int
    discontinuations_due_to_ae: int


class AeBreakdown(BaseModel):
    label: str
    count: int


class AeSummaryResponse(BaseModel):
    study_id: str
    kpis: AeKpis
    by_severity: List[AeBreakdown]
    by_soc: List[AeBreakdown]
    by_preferred_term: List[AeBreakdown]
    by_outcome: List[AeBreakdown]


# ─────────────────────────────────────────────────────────────────────────────
# Enrollment overview
# ─────────────────────────────────────────────────────────────────────────────
class EnrollmentFunnelBucket(BaseModel):
    label: str
    count: int
    tone: Optional[str] = None  # 'success' | 'danger' | 'warning' | None


class EnrollmentMonthlyPoint(BaseModel):
    month: str  # YYYY-MM
    monthly: int
    cumulative: int


class EnrollmentResponse(BaseModel):
    study_id: str
    target: Optional[int] = None
    enrolled: int
    rate_per_month: float
    projected_lpi: Optional[str] = None  # e.g. "Jul 2026"
    funnel: List[EnrollmentFunnelBucket]
    monthly: List[EnrollmentMonthlyPoint]


# ─────────────────────────────────────────────────────────────────────────────
# Disposition
# ─────────────────────────────────────────────────────────────────────────────
class DispositionStatusCounts(BaseModel):
    active: int
    completed: int
    screen_failed: int
    discontinued: int
    total_screened: int


class DispositionBreakdownItem(BaseModel):
    label: str
    count: int


class DispositionResponse(BaseModel):
    study_id: str
    counts: DispositionStatusCounts
    discontinuation_reasons: List[DispositionBreakdownItem]
    screen_failure_reasons: List[DispositionBreakdownItem]
    median_tt_screen_fail_days: Optional[int] = None
    median_time_on_study_days: Optional[int] = None
    median_tt_withdrawal_days: Optional[int] = None
    discontinuation_rate_pct: Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
# Visit compliance
# ─────────────────────────────────────────────────────────────────────────────
class VisitComplianceRow(BaseModel):
    visitnum: float
    visit: str
    performed: int
    missed: int
    upcoming: int


class VisitComplianceResponse(BaseModel):
    study_id: str
    rows: List[VisitComplianceRow]
    total_performed: int
    total_expected: int
    compliance_pct: float


# ─────────────────────────────────────────────────────────────────────────────
# Deviations
# ─────────────────────────────────────────────────────────────────────────────
class DeviationsWeeklyPoint(BaseModel):
    week_start: str  # YYYY-MM-DD
    count: int


class DeviationsCategoryRow(BaseModel):
    label: str
    count: int
    major_count: int


class DeviationsResponse(BaseModel):
    study_id: str
    total: int
    critical: int
    major: int
    minor: int
    pd_rate_per_subject: float
    weekly: List[DeviationsWeeklyPoint]
    top_categories: List[DeviationsCategoryRow]


# ─────────────────────────────────────────────────────────────────────────────
# Milestones
# ─────────────────────────────────────────────────────────────────────────────
class MilestoneItem(BaseModel):
    key: str  # fsi | fpi | enr25 | enr50 | enr75 | lpi | lpo | dblock
    label: str
    date: Optional[str] = None  # ISO yyyy-mm-dd
    tone: str  # 'success' | 'warning' | 'danger' | 'secondary'


class MilestonesResponse(BaseModel):
    study_id: str
    milestones: List[MilestoneItem]


# ─────────────────────────────────────────────────────────────────────────────
# AI Assistant
# ─────────────────────────────────────────────────────────────────────────────
class ChartSpec(BaseModel):
    type: Literal["kpi", "table", "bar", "line", "pie", "stacked_bar"]
    title: str
    x_field: Optional[str] = None
    y_field: Optional[str] = None
    series_field: Optional[str] = None
    value_field: Optional[str] = None


class AssistantData(BaseModel):
    columns: List[str]
    rows: List[List[Any]]


class AssistantResponse(BaseModel):
    status: Literal["ok", "no_data", "rejected", "execution_error"]
    narrative: Optional[str] = None
    sql: Optional[str] = None
    chart: Optional[ChartSpec] = None
    data: Optional[AssistantData] = None
    row_count: Optional[int] = None
    elapsed_ms: Optional[int] = None
    reason: Optional[str] = None


class AssistantQueryRequest(BaseModel):
    question: str
    history: Optional[List[dict]] = None
    # Data Platform registry study to answer against; None/"local" → study_db_01.
    registry_study_id: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Study Registry (Data Platform)
# ─────────────────────────────────────────────────────────────────────────────
class StudyRegistryItem(BaseModel):
    """One selectable study for the dashboard dropdown.

    Deliberately excludes the registry connection string — database credentials
    never leave the backend; the frontend addresses a study by studyId only.
    """

    studyId: str
    studyName: str
    databaseName: Optional[str] = None
    activeFlag: bool = True


class StudyRegistryResponse(BaseModel):
    items: List[StudyRegistryItem]
