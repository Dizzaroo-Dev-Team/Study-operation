"""
Study milestone tracker.

Derives macro milestones from the SDTM data:
  - FSI  : min DM.RFICDTC          (first informed consent)
  - FPI  : min DM.RFXSTDTC         (first patient first dose)
  - 25/50/75% enrolled : Nth-percentile date of DM.RFXSTDTC
  - LPI  : max DM.RFXSTDTC         (last patient in)
  - LPO  : max DM.RFENDTC          (last patient out)
  - DB lock / Activation : not present in DB → null
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import MilestoneItem, MilestonesResponse
from .enrollment import _resolve_study_id


def _iso(d) -> Optional[str]:
    if d is None:
        return None
    if isinstance(d, date):
        return d.isoformat()
    s = str(d)[:10]
    return s if s else None


async def build_milestones(
    session: AsyncSession,
    study_id: Optional[str] = None,
) -> MilestonesResponse:
    study_id = await _resolve_study_id(session, study_id)
    if not study_id:
        return MilestonesResponse(study_id="", milestones=[])

    # FSI / FPI / LPI / LPO single-row roll-up
    row = (
        await session.execute(
            text(
                """
                SELECT
                    MIN(rficdtc::date)  AS fsi,
                    MIN(rfxstdtc::date) AS fpi,
                    MAX(rfxstdtc::date) AS lpi,
                    MAX(rfendtc::date)  AS lpo
                FROM dm
                WHERE studyid = :sid
                """
            ),
            {"sid": study_id},
        )
    ).one()
    fsi, fpi, lpi, lpo = row

    # 25/50/75 percentile dates of RFXSTDTC — use percentile_disc (discrete)
    # because percentile_cont needs a numeric argument and we want an actual
    # observed enrolment date, not an interpolated one anyway.
    pct_row = (
        await session.execute(
            text(
                """
                SELECT
                    percentile_disc(0.25) WITHIN GROUP (
                        ORDER BY rfxstdtc::date
                    ) FILTER (WHERE rfxstdtc IS NOT NULL) AS q25,
                    percentile_disc(0.50) WITHIN GROUP (
                        ORDER BY rfxstdtc::date
                    ) FILTER (WHERE rfxstdtc IS NOT NULL) AS q50,
                    percentile_disc(0.75) WITHIN GROUP (
                        ORDER BY rfxstdtc::date
                    ) FILTER (WHERE rfxstdtc IS NOT NULL) AS q75
                FROM dm
                WHERE studyid = :sid AND (armcd IS NULL OR armcd <> 'SCRNFAIL')
                """
            ),
            {"sid": study_id},
        )
    ).one()
    q25, q50, q75 = pct_row

    milestones = [
        MilestoneItem(key="fsi", label="FSI", date=_iso(fsi), tone="success"),
        MilestoneItem(key="fpi", label="FPI", date=_iso(fpi), tone="success"),
        MilestoneItem(key="enr25", label="25% enr", date=_iso(q25), tone="success"),
        MilestoneItem(key="enr50", label="50% enr", date=_iso(q50), tone="success"),
        MilestoneItem(key="enr75", label="75% enr", date=_iso(q75), tone="success"),
        MilestoneItem(key="lpi", label="LPI", date=_iso(lpi), tone="success"),
        MilestoneItem(key="lpo", label="LPO", date=_iso(lpo), tone="success"),
        MilestoneItem(key="dblock", label="DB lock", date=None, tone="secondary"),
    ]

    return MilestonesResponse(study_id=study_id, milestones=milestones)
