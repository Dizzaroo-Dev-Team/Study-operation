"""
Protocol-deviation summary from the DV domain.

DV.DVCAT is restricted to {Major, Minor} in this dataset — there is no
"Critical" category, so the Critical KPI shows 0 / N/A. The mockup's per-site
column is also unavailable: DV has no SITEID, so we surface the deviation
category and overall count instead.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import (
    DeviationsResponse,
    DeviationsCategoryRow,
    DeviationsWeeklyPoint,
)
from .enrollment import _resolve_study_id


async def build_deviations(
    session: AsyncSession,
    study_id: Optional[str] = None,
) -> DeviationsResponse:
    study_id = await _resolve_study_id(session, study_id)
    if not study_id:
        return DeviationsResponse(
            study_id="",
            total=0,
            critical=0,
            major=0,
            minor=0,
            pd_rate_per_subject=0.0,
            weekly=[],
            top_categories=[],
        )

    # Severity totals
    totals_row = (
        await session.execute(
            text(
                """
                SELECT
                    COUNT(*)::int AS total,
                    COUNT(*) FILTER (WHERE dvcat = 'Major')::int AS major,
                    COUNT(*) FILTER (WHERE dvcat = 'Minor')::int AS minor,
                    COUNT(DISTINCT usubjid)::int AS subjects_with_dv
                FROM dv
                WHERE studyid = :sid
                """
            ),
            {"sid": study_id},
        )
    ).one()
    total, major, minor, subjects_with_dv = totals_row

    # Total enrolled subjects (denominator for per-subject rate)
    enrolled = int(
        (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM dm
                    WHERE studyid = :sid AND rfxstdtc IS NOT NULL
                      AND (armcd IS NULL OR armcd <> 'SCRNFAIL')
                    """
                ),
                {"sid": study_id},
            )
        ).scalar()
        or 0
    )
    pd_rate = round(total / enrolled, 2) if enrolled else 0.0

    # Weekly volume — last 12 weeks anchored to the latest DV in the data.
    weekly_rows = (
        await session.execute(
            text(
                """
                WITH bounds AS (
                    SELECT MAX(dvstdtc::date) AS max_date FROM dv WHERE studyid = :sid
                )
                SELECT to_char(date_trunc('week', dvstdtc::date), 'YYYY-MM-DD') AS week_start,
                       COUNT(*)::int AS cnt
                FROM dv, bounds
                WHERE studyid = :sid
                  AND dvstdtc IS NOT NULL
                  AND dvstdtc::date >= bounds.max_date - INTERVAL '84 days'
                GROUP BY 1
                ORDER BY 1
                """
            ),
            {"sid": study_id},
        )
    ).all()
    weekly = [DeviationsWeeklyPoint(week_start=r[0], count=int(r[1])) for r in weekly_rows]

    # Top deviation categories (DVDECOD)
    cat_rows = (
        await session.execute(
            text(
                """
                SELECT dvdecod, COUNT(*)::int AS cnt,
                       COUNT(*) FILTER (WHERE dvcat = 'Major')::int AS major_cnt
                FROM dv
                WHERE studyid = :sid AND dvdecod IS NOT NULL
                GROUP BY dvdecod
                ORDER BY cnt DESC
                LIMIT 6
                """
            ),
            {"sid": study_id},
        )
    ).all()
    top_categories = [
        DeviationsCategoryRow(label=r[0], count=int(r[1]), major_count=int(r[2])) for r in cat_rows
    ]

    return DeviationsResponse(
        study_id=study_id,
        total=int(total or 0),
        critical=0,  # DVCAT has no "Critical" tier in this dataset
        major=int(major or 0),
        minor=int(minor or 0),
        pd_rate_per_subject=pd_rate,
        weekly=weekly,
        top_categories=top_categories,
    )
