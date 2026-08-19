"""
Visit-compliance summary.

Compares actual visits (SV) vs planned visits (TV) per planned-visit position.
Without protocol visit windows we can only mark each visit as "performed" (in
SV) or "not yet performed" (in TV but not in SV for an active subject), and
"upcoming" for subjects whose enrolment is later than the typical performance
date for that visit.

Once visit-window config arrives we tighten the on-window / out-of-window
split. For now the response carries: per-visit performed/missed/upcoming
counts and a top-line "% of expected visits completed".
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import VisitComplianceResponse, VisitComplianceRow
from .enrollment import DISCONTINUATION_TERMS, _resolve_study_id


async def build_visit_compliance(
    session: AsyncSession,
    study_id: Optional[str] = None,
    max_visits: int = 20,
) -> VisitComplianceResponse:
    study_id = await _resolve_study_id(session, study_id)
    if not study_id:
        return VisitComplianceResponse(
            study_id="", rows=[], total_performed=0, total_expected=0, compliance_pct=0.0
        )

    # Planned visits ordered by visitnum
    tv = (
        await session.execute(
            text(
                """
                SELECT DISTINCT visitnum, visit
                FROM tv
                WHERE studyid = :sid
                ORDER BY visitnum
                LIMIT :lim
                """
            ),
            {"sid": study_id, "lim": max_visits},
        )
    ).all()

    if not tv:
        return VisitComplianceResponse(
            study_id=study_id, rows=[], total_performed=0, total_expected=0, compliance_pct=0.0
        )

    # Total enrolled (= "expected to perform every visit")
    enrolled = int(
        (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM dm
                    WHERE studyid = :sid
                      AND rfxstdtc IS NOT NULL
                      AND (armcd IS NULL OR armcd <> 'SCRNFAIL')
                    """
                ),
                {"sid": study_id},
            )
        ).scalar()
        or 0
    )

    # Discontinued subjects (so we can subtract from "expected" for visits
    # after their disposition)
    discontinued = int(
        (
            await session.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT usubjid) FROM ds
                    WHERE studyid = :sid AND dscat = 'DISPOSITION EVENT' AND dsdecod = ANY(:terms)
                    """
                ),
                {"sid": study_id, "terms": list(DISCONTINUATION_TERMS)},
            )
        ).scalar()
        or 0
    )

    # Per-visit performed counts from SV (distinct subjects who performed it)
    sv_rows = (
        await session.execute(
            text(
                """
                SELECT visitnum, COUNT(DISTINCT usubjid)::int
                FROM sv
                WHERE studyid = :sid AND visitnum IS NOT NULL
                GROUP BY visitnum
                """
            ),
            {"sid": study_id},
        )
    ).all()
    performed_by_visit = {float(r[0]): int(r[1]) for r in sv_rows}

    rows: list[VisitComplianceRow] = []
    total_performed = 0
    total_expected = 0
    # For each planned visit, expected = enrolled (subjects who could have done it).
    # Performed = SV count for that visitnum.
    # Missed = expected - performed - (subjects discontinued before this visit) — approximated as 0
    # for v1, with "off-study" lumped into 'na' on the matrix; here we collapse:
    #   performed + (expected-performed) where excess is "not performed".
    for visitnum, visit_label in tv:
        v = float(visitnum)
        performed = performed_by_visit.get(v, 0)
        # Approximate "still expected" = enrolled - discontinued (rough lower bound)
        still_in = max(0, enrolled - discontinued)
        expected = max(still_in, performed)
        missed = max(0, expected - performed)
        rows.append(
            VisitComplianceRow(
                visitnum=v,
                visit=visit_label,
                performed=performed,
                missed=missed,
                upcoming=max(0, enrolled - expected),
            )
        )
        total_performed += performed
        total_expected += expected

    compliance_pct = round((total_performed / total_expected) * 100, 1) if total_expected else 0.0
    return VisitComplianceResponse(
        study_id=study_id,
        rows=rows,
        total_performed=total_performed,
        total_expected=total_expected,
        compliance_pct=compliance_pct,
    )
