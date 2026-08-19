"""
Subject disposition service.

Reads DS (disposition events), DM (subject status flags), and IE
(inclusion/exclusion criteria not met) to produce:
  - status breakdown (active / completed / screen-failed / discontinued)
  - discontinuation reasons (DS DSDECOD where DSCAT='DISPOSITION EVENT')
  - screen-failure reasons (IE.IETEST where the subject screen-failed)
  - time-to-event medians (TT screen-fail, time on study, TT withdrawal)
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import (
    DispositionBreakdownItem,
    DispositionResponse,
    DispositionStatusCounts,
)
from .enrollment import DISCONTINUATION_TERMS, _resolve_study_id


async def build_disposition(
    session: AsyncSession,
    study_id: Optional[str] = None,
) -> DispositionResponse:
    study_id = await _resolve_study_id(session, study_id)
    if not study_id:
        return DispositionResponse(
            study_id="",
            counts=DispositionStatusCounts(active=0, completed=0, screen_failed=0, discontinued=0, total_screened=0),
            discontinuation_reasons=[],
            screen_failure_reasons=[],
            median_tt_screen_fail_days=None,
            median_time_on_study_days=None,
            median_tt_withdrawal_days=None,
            discontinuation_rate_pct=None,
        )

    # ── Status counts ───────────────────────────────────────────────────────
    base = (
        await session.execute(
            text(
                """
                SELECT
                    COUNT(*)::int AS screened,
                    COUNT(*) FILTER (WHERE armcd = 'SCRNFAIL')::int AS screen_failed,
                    COUNT(*) FILTER (
                        WHERE rfxstdtc IS NOT NULL AND (armcd IS NULL OR armcd <> 'SCRNFAIL')
                    )::int AS enrolled
                FROM dm WHERE studyid = :sid
                """
            ),
            {"sid": study_id},
        )
    ).one()
    screened, screen_failed, enrolled = base

    discontinued = int(
        (
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
        ).scalar()
        or 0
    )

    completed = int(
        (
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
        ).scalar()
        or 0
    )

    active = max(0, enrolled - completed - discontinued)
    counts = DispositionStatusCounts(
        active=int(active),
        completed=completed,
        screen_failed=int(screen_failed),
        discontinued=discontinued,
        total_screened=int(screened),
    )

    # ── Discontinuation reasons donut ───────────────────────────────────────
    disco_rows = (
        await session.execute(
            text(
                """
                SELECT dsdecod, COUNT(DISTINCT usubjid)::int
                FROM ds
                WHERE studyid = :sid
                  AND dscat = 'DISPOSITION EVENT'
                  AND dsdecod = ANY(:terms)
                GROUP BY dsdecod
                ORDER BY 2 DESC
                """
            ),
            {"sid": study_id, "terms": list(DISCONTINUATION_TERMS)},
        )
    ).all()
    disco_reasons = [
        DispositionBreakdownItem(label=str(r[0]).title(), count=int(r[1])) for r in disco_rows
    ]

    # ── Screen-failure reasons from IE ──────────────────────────────────────
    # IETEST is the full criterion text; we group by IETESTCD and take the
    # max IETEST as label for readability.
    sf_rows = (
        await session.execute(
            text(
                """
                SELECT ietestcd, MAX(ietest) AS label, COUNT(DISTINCT usubjid)::int AS cnt
                FROM ie
                WHERE studyid = :sid AND iestresc IN ('Y', 'N')
                GROUP BY ietestcd
                ORDER BY cnt DESC
                LIMIT 6
                """
            ),
            {"sid": study_id},
        )
    ).all()
    screen_failure_reasons: list[DispositionBreakdownItem] = []
    for code, label, cnt in sf_rows:
        # Trim long criterion text
        short = (label or code or "").strip()
        if len(short) > 80:
            short = short[:77].rstrip() + "…"
        screen_failure_reasons.append(
            DispositionBreakdownItem(label=f"{code} · {short}" if code else short, count=int(cnt))
        )

    # ── Medians (days) ──────────────────────────────────────────────────────
    median_row = (
        await session.execute(
            text(
                """
                WITH withdrawal_events AS (
                    SELECT usubjid, MIN(dsstdtc::date) AS event_date
                    FROM ds
                    WHERE studyid = :sid
                      AND dscat = 'DISPOSITION EVENT'
                      AND dsdecod = 'WITHDRAWAL BY SUBJECT'
                    GROUP BY usubjid
                ),
                screen_fail_events AS (
                    SELECT usubjid, MIN(dsstdtc::date) AS event_date
                    FROM ds
                    WHERE studyid = :sid
                      AND dsdecod = 'SCREEN FAILURE'
                    GROUP BY usubjid
                )
                SELECT
                    percentile_cont(0.5) WITHIN GROUP (
                        ORDER BY (sf.event_date - dm.rficdtc::date)
                    ) FILTER (WHERE sf.event_date IS NOT NULL AND dm.rficdtc IS NOT NULL) AS median_tt_sf,
                    percentile_cont(0.5) WITHIN GROUP (
                        ORDER BY (dm.rfendtc::date - dm.rfstdtc::date)
                    ) FILTER (
                        WHERE dm.rfendtc IS NOT NULL AND dm.rfstdtc IS NOT NULL
                          AND (dm.armcd IS NULL OR dm.armcd <> 'SCRNFAIL')
                    ) AS median_time_on_study,
                    percentile_cont(0.5) WITHIN GROUP (
                        ORDER BY (w.event_date - dm.rfstdtc::date)
                    ) FILTER (WHERE w.event_date IS NOT NULL AND dm.rfstdtc IS NOT NULL) AS median_tt_w
                FROM dm
                LEFT JOIN withdrawal_events w ON w.usubjid = dm.usubjid
                LEFT JOIN screen_fail_events sf ON sf.usubjid = dm.usubjid
                WHERE dm.studyid = :sid
                """
            ),
            {"sid": study_id},
        )
    ).one()
    median_tt_sf, median_time_on_study, median_tt_w = median_row

    def _round_or_none(v):
        try:
            return None if v is None else int(round(float(v)))
        except (TypeError, ValueError):
            return None

    discontinuation_rate_pct = None
    if enrolled and enrolled > 0:
        discontinuation_rate_pct = round((discontinued / enrolled) * 100, 1)

    return DispositionResponse(
        study_id=study_id,
        counts=counts,
        discontinuation_reasons=disco_reasons,
        screen_failure_reasons=screen_failure_reasons,
        median_tt_screen_fail_days=_round_or_none(median_tt_sf),
        median_time_on_study_days=_round_or_none(median_time_on_study),
        median_tt_withdrawal_days=_round_or_none(median_tt_w),
        discontinuation_rate_pct=discontinuation_rate_pct,
    )
