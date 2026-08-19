"""
Adverse Event safety summary service.

Reads from the AE domain to produce KPI totals and breakdowns by severity (CTCAE
grade), system organ class, preferred term, and outcome.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import AeBreakdown, AeKpis, AeSummaryResponse


async def build_ae_summary(
    session: AsyncSession,
    study_id: Optional[str] = None,
) -> AeSummaryResponse:
    if not study_id:
        row = (
            await session.execute(text("SELECT DISTINCT studyid FROM ae LIMIT 1"))
        ).first()
        if row is None:
            return AeSummaryResponse(
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
        study_id = row[0]

    # KPI roll-up
    kpi_row = (
        await session.execute(
            text(
                """
                SELECT
                    COUNT(*)::int AS total_events,
                    COUNT(DISTINCT usubjid)::int AS subjects_with_ae,
                    COUNT(*) FILTER (WHERE aeser = 'Y')::int AS serious_events,
                    COUNT(*) FILTER (WHERE aerel = 'RELATED')::int AS related_events,
                    COUNT(*) FILTER (WHERE aesdth = 'Y')::int AS fatal_events,
                    COUNT(*) FILTER (WHERE aeacn = 'DRUG WITHDRAWN')::int AS disc_due_ae
                FROM ae
                WHERE studyid = :sid
                """
            ),
            {"sid": study_id},
        )
    ).one()
    kpis = AeKpis(
        total_events=kpi_row[0] or 0,
        subjects_with_ae=kpi_row[1] or 0,
        serious_events=kpi_row[2] or 0,
        related_events=kpi_row[3] or 0,
        fatal_events=kpi_row[4] or 0,
        discontinuations_due_to_ae=kpi_row[5] or 0,
    )

    # CTCAE grade 1..5
    sev_rows = (
        await session.execute(
            text(
                """
                SELECT aetoxgr::int AS grade, COUNT(*)::int AS cnt
                FROM ae
                WHERE studyid = :sid AND aetoxgr IS NOT NULL
                GROUP BY aetoxgr
                ORDER BY aetoxgr
                """
            ),
            {"sid": study_id},
        )
    ).all()
    by_severity = [
        AeBreakdown(label=f"Grade {int(r[0])}", count=int(r[1])) for r in sev_rows
    ]

    soc_rows = (
        await session.execute(
            text(
                """
                SELECT aesoc, COUNT(*)::int AS cnt
                FROM ae
                WHERE studyid = :sid AND aesoc IS NOT NULL
                GROUP BY aesoc
                ORDER BY cnt DESC
                LIMIT 10
                """
            ),
            {"sid": study_id},
        )
    ).all()
    by_soc = [AeBreakdown(label=r[0], count=int(r[1])) for r in soc_rows]

    pt_rows = (
        await session.execute(
            text(
                """
                SELECT aedecod, COUNT(*)::int AS cnt
                FROM ae
                WHERE studyid = :sid AND aedecod IS NOT NULL
                GROUP BY aedecod
                ORDER BY cnt DESC
                LIMIT 10
                """
            ),
            {"sid": study_id},
        )
    ).all()
    by_preferred_term = [AeBreakdown(label=r[0], count=int(r[1])) for r in pt_rows]

    out_rows = (
        await session.execute(
            text(
                """
                SELECT aeout, COUNT(*)::int AS cnt
                FROM ae
                WHERE studyid = :sid AND aeout IS NOT NULL
                GROUP BY aeout
                ORDER BY cnt DESC
                """
            ),
            {"sid": study_id},
        )
    ).all()
    by_outcome = [AeBreakdown(label=r[0], count=int(r[1])) for r in out_rows]

    return AeSummaryResponse(
        study_id=study_id,
        kpis=kpis,
        by_severity=by_severity,
        by_soc=by_soc,
        by_preferred_term=by_preferred_term,
        by_outcome=by_outcome,
    )
