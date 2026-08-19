"""
Study Dashboard routes — read-only views over the per-study SDTM Postgres.

Endpoints (all under /api/study-dashboard):
  GET /health
  GET /study-registry            (Data Platform registry proxy — active studies)
  GET /study-registry/{study_id}
  GET /patient-visit-matrix
  GET /ae-summary
  GET /enrollment
  GET /disposition
  GET /visit-compliance
  GET /deviations
  GET /milestones

Every data endpoint accepts an optional ``registry_study_id``. When absent (or
"local") the request runs against the default hardcoded study DB (study_db_01)
exactly as before; when set, the study's connection details are resolved from
the Data Platform Study Registry and the queries run against that database.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai_assistant.service import answer_query
from ..engine import get_registry_study_session, get_study_db_session
from ..registry import StudyRegistryError, fetch_registry_studies, fetch_registry_study, resolve_connection_string
from ..schemas import (
    AeKpis,
    AeSummaryResponse,
    AssistantQueryRequest,
    AssistantResponse,
    DeviationsResponse,
    DispositionResponse,
    DispositionStatusCounts,
    EnrollmentResponse,
    MilestonesResponse,
    PatientVisitMatrixResponse,
    StudyRegistryItem,
    StudyRegistryResponse,
    VisitComplianceResponse,
)
from ..services.ae_summary import build_ae_summary
from ..services.deviations import build_deviations
from ..services.disposition import build_disposition
from ..services.enrollment import build_enrollment
from ..services.milestones import build_milestones
from ..services.patient_visit import build_patient_visit_matrix
from ..services.visit_compliance import build_visit_compliance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/study-dashboard", tags=["study-dashboard"])


def _sdtm_schema_error(exc: BaseException) -> bool:
    """True when Postgres/asyncpg reports a missing relation or column — a DB
    without SDTM tables (CRM DB) or with a partial SDTM load (registry studies
    mid-ingestion). Both degrade to empty payloads instead of 500s."""
    err: BaseException | None = exc
    seen: set[int] = set()
    while err is not None and id(err) not in seen:
        seen.add(id(err))
        if isinstance(err, (ProgrammingError, DBAPIError)):
            detail = str(getattr(err, "orig", err)).lower()
            compact = detail.replace(" ", "").replace("_", "")
            if "undefinedtable" in compact or "undefinedcolumn" in compact:
                return True
            if "does not exist" in detail and ("relation" in detail or "column" in detail):
                return True
        err = err.__cause__ or getattr(err, "__context__", None)
    return False


@asynccontextmanager
async def _study_session(registry_study_id: Optional[str]) -> AsyncIterator[AsyncSession]:
    """Yield a DB session for the requested study.

    None / "" / "local" → the existing hardcoded study_db_01 engine, byte-for-
    byte the pre-registry behavior. Anything else → resolve the study's
    connection string from the Data Platform registry and use its database.
    """
    if not registry_study_id or registry_study_id == "local":
        async with get_study_db_session() as session:
            yield session
        return

    try:
        connection_string = await resolve_connection_string(registry_study_id)
    except StudyRegistryError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail.lower() else 503
        raise HTTPException(status_code=status, detail=detail) from exc

    async with get_registry_study_session(connection_string) as session:
        yield session


_EMPTY_PATIENT_VISIT_MATRIX = PatientVisitMatrixResponse(
    study_id="",
    visits=[],
    subjects=[],
    summary={
        "total_subjects": 0,
        "total_visits_planned": 0,
        "visits_done": 0,
        "visits_missed": 0,
        "visits_due": 0,
    },
)
_EMPTY_AE_SUMMARY = AeSummaryResponse(
    study_id="",
    kpis=AeKpis(
        total_events=0,
        subjects_with_ae=0,
        serious_events=0,
        related_events=0,
        fatal_events=0,
        discontinuations_due_to_ae=0,
    ),
    by_severity=[],
    by_soc=[],
    by_preferred_term=[],
    by_outcome=[],
)
_EMPTY_ENROLLMENT = EnrollmentResponse(
    study_id="",
    target=None,
    enrolled=0,
    rate_per_month=0.0,
    projected_lpi=None,
    funnel=[],
    monthly=[],
)
_EMPTY_DISPOSITION = DispositionResponse(
    study_id="",
    counts=DispositionStatusCounts(
        active=0,
        completed=0,
        screen_failed=0,
        discontinued=0,
        total_screened=0,
    ),
    discontinuation_reasons=[],
    screen_failure_reasons=[],
    median_tt_screen_fail_days=None,
    median_time_on_study_days=None,
    median_tt_withdrawal_days=None,
    discontinuation_rate_pct=None,
)
_EMPTY_VISIT_COMPLIANCE = VisitComplianceResponse(
    study_id="",
    rows=[],
    total_performed=0,
    total_expected=0,
    compliance_pct=0.0,
)
_EMPTY_DEVIATIONS = DeviationsResponse(
    study_id="",
    total=0,
    critical=0,
    major=0,
    minor=0,
    pd_rate_per_subject=0.0,
    weekly=[],
    top_categories=[],
)
_EMPTY_MILESTONES = MilestonesResponse(study_id="", milestones=[])
_EMPTY_ASSISTANT = AssistantResponse(
    status="no_data",
    narrative="Study SDTM tables are not available in this database.",
)


@router.get("/health")
async def study_dashboard_health() -> dict:
    try:
        async with get_study_db_session() as session:
            row = (await session.execute(text("SELECT 1"))).scalar()
        return {"status": "ok", "study_db_round_trip": row == 1}
    except Exception as exc:
        logger.exception("study-dashboard health check failed")
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/study-registry", response_model=StudyRegistryResponse)
async def study_registry_list() -> StudyRegistryResponse:
    """Active studies from the Data Platform Study Registry (proxied so the
    browser never talks to the Data Platform or sees connection strings)."""
    try:
        studies = await fetch_registry_studies()
    except StudyRegistryError as exc:
        logger.warning("study-registry list failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
    return StudyRegistryResponse(
        items=[
            StudyRegistryItem(
                studyId=s["studyId"],
                studyName=s["studyName"],
                databaseName=s.get("databaseName"),
                activeFlag=True,
            )
            for s in studies
            if s.get("activeFlag")
        ]
    )


@router.get("/study-registry/{study_id}", response_model=StudyRegistryItem)
async def study_registry_get(study_id: str) -> StudyRegistryItem:
    try:
        study = await fetch_registry_study(study_id)
    except StudyRegistryError as exc:
        logger.warning("study-registry get %s failed: %s", study_id, exc)
        raise HTTPException(status_code=503, detail=str(exc))
    if study is None:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found in registry")
    return StudyRegistryItem(
        studyId=study["studyId"],
        studyName=study["studyName"],
        databaseName=study.get("databaseName"),
        activeFlag=bool(study.get("activeFlag")),
    )


@router.get("/patient-visit-matrix", response_model=PatientVisitMatrixResponse)
async def patient_visit_matrix(
    study_id: Optional[str] = Query(default=None),
    limit_subjects: int = Query(default=200, ge=1, le=1000),
    registry_study_id: Optional[str] = Query(default=None),
) -> PatientVisitMatrixResponse:
    try:
        async with _study_session(registry_study_id) as session:
            return await build_patient_visit_matrix(
                session, study_id=study_id, limit_subjects=limit_subjects
            )
    except HTTPException:
        raise
    except Exception as exc:
        if _sdtm_schema_error(exc):
            logger.warning("patient-visit-matrix: SDTM schema missing, returning empty payload")
            return _EMPTY_PATIENT_VISIT_MATRIX
        logger.exception("patient-visit-matrix failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/ae-summary", response_model=AeSummaryResponse)
async def ae_summary(
    study_id: Optional[str] = Query(default=None),
    registry_study_id: Optional[str] = Query(default=None),
) -> AeSummaryResponse:
    try:
        async with _study_session(registry_study_id) as session:
            return await build_ae_summary(session, study_id=study_id)
    except HTTPException:
        raise
    except Exception as exc:
        if _sdtm_schema_error(exc):
            logger.warning("ae-summary: SDTM schema missing, returning empty payload")
            return _EMPTY_AE_SUMMARY
        logger.exception("ae-summary failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/enrollment", response_model=EnrollmentResponse)
async def enrollment(
    study_id: Optional[str] = Query(default=None),
    registry_study_id: Optional[str] = Query(default=None),
) -> EnrollmentResponse:
    try:
        async with _study_session(registry_study_id) as session:
            return await build_enrollment(session, study_id=study_id)
    except HTTPException:
        raise
    except Exception as exc:
        if _sdtm_schema_error(exc):
            logger.warning("enrollment: SDTM schema missing, returning empty payload")
            return _EMPTY_ENROLLMENT
        logger.exception("enrollment failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/disposition", response_model=DispositionResponse)
async def disposition(
    study_id: Optional[str] = Query(default=None),
    registry_study_id: Optional[str] = Query(default=None),
) -> DispositionResponse:
    try:
        async with _study_session(registry_study_id) as session:
            return await build_disposition(session, study_id=study_id)
    except HTTPException:
        raise
    except Exception as exc:
        if _sdtm_schema_error(exc):
            logger.warning("disposition: SDTM schema missing, returning empty payload")
            return _EMPTY_DISPOSITION
        logger.exception("disposition failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/visit-compliance", response_model=VisitComplianceResponse)
async def visit_compliance(
    study_id: Optional[str] = Query(default=None),
    max_visits: int = Query(default=20, ge=1, le=80),
    registry_study_id: Optional[str] = Query(default=None),
) -> VisitComplianceResponse:
    try:
        async with _study_session(registry_study_id) as session:
            return await build_visit_compliance(session, study_id=study_id, max_visits=max_visits)
    except HTTPException:
        raise
    except Exception as exc:
        if _sdtm_schema_error(exc):
            logger.warning("visit-compliance: SDTM schema missing, returning empty payload")
            return _EMPTY_VISIT_COMPLIANCE
        logger.exception("visit-compliance failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/deviations", response_model=DeviationsResponse)
async def deviations(
    study_id: Optional[str] = Query(default=None),
    registry_study_id: Optional[str] = Query(default=None),
) -> DeviationsResponse:
    try:
        async with _study_session(registry_study_id) as session:
            return await build_deviations(session, study_id=study_id)
    except HTTPException:
        raise
    except Exception as exc:
        if _sdtm_schema_error(exc):
            logger.warning("deviations: SDTM schema missing, returning empty payload")
            return _EMPTY_DEVIATIONS
        logger.exception("deviations failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/milestones", response_model=MilestonesResponse)
async def milestones(
    study_id: Optional[str] = Query(default=None),
    registry_study_id: Optional[str] = Query(default=None),
) -> MilestonesResponse:
    try:
        async with _study_session(registry_study_id) as session:
            return await build_milestones(session, study_id=study_id)
    except HTTPException:
        raise
    except Exception as exc:
        if _sdtm_schema_error(exc):
            logger.warning("milestones: SDTM schema missing, returning empty payload")
            return _EMPTY_MILESTONES
        logger.exception("milestones failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ai-assistant", response_model=AssistantResponse)
async def ai_assistant(req: AssistantQueryRequest) -> AssistantResponse:
    try:
        async with _study_session(req.registry_study_id) as session:
            return await answer_query(session, req.question, req.history)
    except HTTPException:
        raise
    except Exception as exc:
        if _sdtm_schema_error(exc):
            logger.warning("ai-assistant: SDTM schema missing, returning no_data")
            return _EMPTY_ASSISTANT
        logger.exception("ai-assistant failed")
        raise HTTPException(status_code=500, detail=str(exc))
