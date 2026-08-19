"""
Enrollment overview service.

KPIs + funnel buckets + monthly S-curve, derived from DM (subject roster), DS
(disposition events), and TS (trial summary parameters).

Single-study DB caveat: the SDTM data is historical (study completed), so the
"rate / month" and "projected LPI" KPIs are computed against the enrollment
span found in the data — not against `today()` — otherwise they would always
read as zero / N/A.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import EnrollmentFunnelBucket, EnrollmentMonthlyPoint, EnrollmentResponse


DISCONTINUATION_TERMS = (
    "ADVERSE EVENT",
    "WITHDRAWAL BY SUBJECT",
    "DEATH",
    "PROGRESSIVE DISEASE",
    "PHYSICIAN DECISION",
    "LOST TO FOLLOW-UP",
    "OTHER",
)


async def _resolve_study_id(session: AsyncSession, study_id: Optional[str]) -> Optional[str]:
    if study_id:
        return study_id
    row = (await session.execute(text("SELECT DISTINCT studyid FROM dm LIMIT 1"))).first()
    return row[0] if row else None


def _parse_dt(value) -> Optional[date]:
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


async def build_enrollment(
    session: AsyncSession,
    study_id: Optional[str] = None,
) -> EnrollmentResponse:
    study_id = await _resolve_study_id(session, study_id)
    if not study_id:
        return EnrollmentResponse(
            study_id="",
            target=None,
            enrolled=0,
            rate_per_month=0.0,
            projected_lpi=None,
            funnel=[],
            monthly=[],
        )

    # Target (planned subjects) from TS — fall back to None if missing
    target_row = (
        await session.execute(
            text(
                """
                SELECT tsval FROM ts
                WHERE studyid = :sid AND tsparmcd IN ('PLANSUB', 'ACTSUB')
                ORDER BY CASE tsparmcd WHEN 'PLANSUB' THEN 1 ELSE 2 END
                LIMIT 1
                """
            ),
            {"sid": study_id},
        )
    ).first()
    try:
        target = int(target_row[0]) if target_row and target_row[0] is not None else None
    except (ValueError, TypeError):
        target = None

    # Funnel buckets
    pre_screened = (
        await session.execute(
            text(
                """
                SELECT COUNT(DISTINCT usubjid) FROM ds
                WHERE studyid = :sid AND dsdecod = 'INFORMED CONSENT OBTAINED'
                """
            ),
            {"sid": study_id},
        )
    ).scalar() or 0

    screened = (
        await session.execute(
            text("SELECT COUNT(DISTINCT usubjid) FROM dm WHERE studyid = :sid"),
            {"sid": study_id},
        )
    ).scalar() or 0

    screen_failed = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM dm WHERE studyid = :sid AND armcd = 'SCRNFAIL'"
            ),
            {"sid": study_id},
        )
    ).scalar() or 0

    enrolled_row = (
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
    ).scalar() or 0
    enrolled = int(enrolled_row)

    randomized = (
        await session.execute(
            text(
                """
                SELECT COUNT(DISTINCT usubjid) FROM ds
                WHERE studyid = :sid AND dsdecod = 'RANDOMIZED'
                """
            ),
            {"sid": study_id},
        )
    ).scalar() or 0

    discontinued = (
        await session.execute(
            text(
                """
                SELECT COUNT(DISTINCT usubjid) FROM ds
                WHERE studyid = :sid
                  AND dscat = 'DISPOSITION EVENT'
                  AND dsdecod = ANY(:terms)
                """
            ),
            {"sid": study_id, "terms": list(DISCONTINUATION_TERMS)},
        )
    ).scalar() or 0

    # Completed = enrolled subjects who reached follow-up / completion
    # SDTM uses 'COMPLETED' but the sample data here uses 'ALIVE' or end-of-treatment.
    # Best proxy: enrolled - discontinued - still-active. We don't have an explicit
    # "study completed" flag, so derive: enrolled with RFENDTC IS NOT NULL and not in
    # discontinued list.
    completed_row = (
        await session.execute(
            text(
                """
                SELECT COUNT(*) FROM dm dm0
                WHERE dm0.studyid = :sid
                  AND dm0.rfxstdtc IS NOT NULL
                  AND dm0.rfendtc IS NOT NULL
                  AND (dm0.armcd IS NULL OR dm0.armcd <> 'SCRNFAIL')
                  AND NOT EXISTS (
                    SELECT 1 FROM ds
                    WHERE ds.studyid = dm0.studyid
                      AND ds.usubjid = dm0.usubjid
                      AND ds.dscat = 'DISPOSITION EVENT'
                      AND ds.dsdecod = ANY(:terms)
                  )
                """
            ),
            {"sid": study_id, "terms": list(DISCONTINUATION_TERMS)},
        )
    ).scalar() or 0
    completed = int(completed_row)

    funnel = [
        EnrollmentFunnelBucket(label="Pre-screened", count=int(pre_screened)),
        EnrollmentFunnelBucket(label="Screened", count=int(screened)),
        EnrollmentFunnelBucket(label="Screen-failed", count=int(screen_failed), tone="danger"),
        EnrollmentFunnelBucket(label="Enrolled", count=enrolled),
        EnrollmentFunnelBucket(label="Randomized", count=int(randomized)),
        EnrollmentFunnelBucket(label="Completed", count=completed, tone="success"),
        EnrollmentFunnelBucket(label="Discontinued", count=int(discontinued), tone="warning"),
    ]

    # Monthly cumulative enrollment from DM.RFXSTDTC
    monthly_rows = (
        await session.execute(
            text(
                """
                SELECT to_char(date_trunc('month', rfxstdtc::date), 'YYYY-MM') AS month,
                       COUNT(*)::int AS cnt
                FROM dm
                WHERE studyid = :sid AND rfxstdtc IS NOT NULL
                GROUP BY 1
                ORDER BY 1
                """
            ),
            {"sid": study_id},
        )
    ).all()
    cumulative = 0
    monthly: list[EnrollmentMonthlyPoint] = []
    for month, cnt in monthly_rows:
        cumulative += int(cnt)
        monthly.append(EnrollmentMonthlyPoint(month=month, monthly=int(cnt), cumulative=cumulative))

    # Rate / projection — use enrollment span in the actual data
    rate_per_month = 0.0
    projected_lpi: Optional[str] = None
    if len(monthly) >= 2 and enrolled > 0:
        first = datetime.strptime(monthly[0].month + "-01", "%Y-%m-%d").date()
        last = datetime.strptime(monthly[-1].month + "-01", "%Y-%m-%d").date()
        span_months = max(1, (last.year - first.year) * 12 + (last.month - first.month) + 1)
        rate_per_month = round(enrolled / span_months, 1)
        if target and enrolled < target and rate_per_month > 0:
            months_to_target = (target - enrolled) / rate_per_month
            projected = last + timedelta(days=int(months_to_target * 30))
            projected_lpi = projected.strftime("%b %Y")
        elif target and enrolled >= target:
            # already met — show last enrollment month as actual LPI
            projected_lpi = last.strftime("%b %Y") + " (actual)"

    return EnrollmentResponse(
        study_id=study_id,
        target=target,
        enrolled=enrolled,
        rate_per_month=rate_per_month,
        projected_lpi=projected_lpi,
        funnel=funnel,
        monthly=monthly,
    )
