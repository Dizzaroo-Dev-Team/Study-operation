"""
Patient × Visit matrix service.

Builds the per-subject × per-planned-visit grid by combining:
  - TV  (Trial Visits)     — planned visits for the study
  - DM  (Demographics)     — subject roster (USUBJID, SITEID, ARM)
  - SV  (Subject Visits)   — actual visits performed
  - DS  (Disposition)      — latest disposition event per subject

SDTM identifiers (table & column names) are CDISC-standard upper-case but
Postgres folds unquoted identifiers to lower-case, so the loader most likely
created them as `ae`, `dm`, etc. We use lower-case identifiers to match that
common case; if the actual schema is quoted upper-case the queries will fail
fast and we'll switch to `"AE"`.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import (
    MatrixCell,
    PatientVisitMatrixResponse,
    PlannedVisit,
    SubjectRow,
)


def _parse_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value)[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


async def build_patient_visit_matrix(
    session: AsyncSession,
    study_id: Optional[str] = None,
    limit_subjects: int = 200,
) -> PatientVisitMatrixResponse:
    # If no study_id was given, take whatever STUDYID is present in DM
    # (this DB is single-study).
    if not study_id:
        row = (
            await session.execute(text("SELECT DISTINCT studyid FROM dm LIMIT 1"))
        ).first()
        if row is None:
            return PatientVisitMatrixResponse(
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
        study_id = row[0]

    # 1) Planned visits from TV
    tv_rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT visitnum, visit
                FROM tv
                WHERE studyid = :sid
                ORDER BY visitnum
                """
            ),
            {"sid": study_id},
        )
    ).all()
    visits = [PlannedVisit(visitnum=float(r[0]), visit=r[1]) for r in tv_rows]
    visitnum_to_idx = {v.visitnum: i for i, v in enumerate(visits)}

    # 2) Subjects from DM
    dm_rows = (
        await session.execute(
            text(
                """
                SELECT usubjid, siteid, arm, rfxstdtc
                FROM dm
                WHERE studyid = :sid AND (armcd IS NULL OR armcd <> 'SCRNFAIL')
                ORDER BY usubjid
                LIMIT :lim
                """
            ),
            {"sid": study_id, "lim": limit_subjects},
        )
    ).all()
    subject_meta = {
        r[0]: {"siteid": r[1], "arm": r[2], "rfxstdtc": _parse_date(r[3])}
        for r in dm_rows
    }
    subject_ids = list(subject_meta.keys())

    if not subject_ids or not visits:
        return PatientVisitMatrixResponse(
            study_id=study_id,
            visits=visits,
            subjects=[],
            summary={
                "total_subjects": 0,
                "total_visits_planned": len(visits),
                "visits_done": 0,
                "visits_missed": 0,
                "visits_due": 0,
            },
        )

    # 3) Actual visits from SV (only for the subjects we care about)
    sv_rows = (
        await session.execute(
            text(
                """
                SELECT usubjid, visitnum, svstdtc
                FROM sv
                WHERE studyid = :sid AND usubjid = ANY(:subs)
                """
            ),
            {"sid": study_id, "subs": subject_ids},
        )
    ).all()
    actual: dict[str, dict[float, Optional[date]]] = {s: {} for s in subject_ids}
    for usubjid, visitnum, svstdtc in sv_rows:
        if visitnum is None:
            continue
        actual[usubjid][float(visitnum)] = _parse_date(svstdtc)

    # 4) Latest DISPOSITION EVENT per subject
    ds_rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT ON (usubjid) usubjid, dsdecod
                FROM ds
                WHERE studyid = :sid
                  AND dscat = 'DISPOSITION EVENT'
                  AND usubjid = ANY(:subs)
                ORDER BY usubjid, dsstdtc DESC NULLS LAST
                """
            ),
            {"sid": study_id, "subs": subject_ids},
        )
    ).all()
    disposition = {r[0]: r[1] for r in ds_rows}

    # 5) Assemble cells. Cell status logic:
    #     - actual visit recorded → "done"
    #     - subject has discontinued/dropped → cells after disposition: "na"
    #     - planned date in past (per SVSTDY or today-vs-RFXSTDTC) → "missed"
    #     - else → "due"
    # We don't have visit windows in TV, so "missed vs due" is best-effort using
    # RFXSTDTC + a coarse per-visit-offset heuristic. For v1 we mark anything not
    # in SV as "due" — once visit windows are supplied we tighten.
    today = date.today()
    visits_done = visits_missed = visits_due = 0
    subjects_out: list[SubjectRow] = []
    DISCONTINUED_TERMS = {
        "SCREEN FAILURE",
        "WITHDRAWAL BY SUBJECT",
        "ADVERSE EVENT",
        "DEATH",
        "PHYSICIAN DECISION",
        "PROGRESSIVE DISEASE",
        "OTHER",
        "LOST TO FOLLOW-UP",
    }
    for sid in subject_ids:
        meta = subject_meta[sid]
        dispo = disposition.get(sid)
        is_off_study = dispo in DISCONTINUED_TERMS
        cells: list[MatrixCell] = []
        for v in visits:
            actual_date = actual.get(sid, {}).get(v.visitnum)
            if actual_date is not None:
                cells.append(
                    MatrixCell(status="done", date=actual_date.isoformat())
                )
                visits_done += 1
            elif is_off_study:
                cells.append(MatrixCell(status="na"))
            else:
                cells.append(MatrixCell(status="due"))
                visits_due += 1
        subjects_out.append(
            SubjectRow(
                usubjid=sid,
                siteid=meta["siteid"],
                arm=meta["arm"],
                disposition=dispo,
                cells=cells,
            )
        )

    return PatientVisitMatrixResponse(
        study_id=study_id,
        visits=visits,
        subjects=subjects_out,
        summary={
            "total_subjects": len(subjects_out),
            "total_visits_planned": len(visits),
            "visits_done": visits_done,
            "visits_missed": visits_missed,
            "visits_due": visits_due,
        },
    )
