from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import (
    Study,
    Site,
    SiteStatus,
    SiteStatusHistory,
    PrimarySiteStatus,
    StudySite,
)
from app import crud
from app.schemas import (
    validate_site_status_metadata,
)


async def record_site_status_change(
    db: AsyncSession,
    site_db_id: UUID,
    new_status: PrimarySiteStatus,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    triggering_event: Optional[str] = None,
    reason: Optional[str] = None,
) -> SiteStatus:
    """
    Update a site's primary status and append to history.

    IMPORTANT:
    - This must be invoked ONLY from backend domain events
      (EC approval, SIV completed, recruitment enabled, etc.).
    - The UI stays read‑only; no direct public API should call this.

    TODO: Wire this into the actual event pipeline once defined (RBAC hooks too).
    """

    from app.models import SiteStatus as SiteStatusModel, SiteStatusHistory as SiteStatusHistoryModel

    result = await db.execute(select(SiteStatusModel).where(SiteStatusModel.site_id == site_db_id))
    current: Optional[SiteStatusModel] = result.scalar_one_or_none()

    previous_status = current.current_status if current else None

    now = datetime.now(timezone.utc)
    validated_meta: Dict[str, Any] = validate_site_status_metadata(new_status, metadata or {})

    if current:
        current.previous_status = previous_status
        current.current_status = new_status
        current.status_metadata = validated_meta
        current.effective_at = now
        current.updated_at = now  # type: ignore[assignment]
    else:
        current = SiteStatusModel(
            site_id=site_db_id,
            current_status=new_status,
            previous_status=None,
            status_metadata=validated_meta,
            effective_at=now,
        )
        db.add(current)

    history_entry = SiteStatusHistoryModel(
        site_id=site_db_id,
        status=new_status,
        previous_status=previous_status,
        status_metadata=validated_meta,
        triggering_event=triggering_event,
        reason=reason,
        changed_at=now,
    )
    db.add(history_entry)

    await db.commit()
    await db.refresh(current)

    # Reflect the change on every Public Notice Board this site participates
    # in (one per study mapping). Best-effort — a notice-board write must not
    # roll back the just-committed status change, so the helper handles its
    # own failures internally.
    try:
        from app.utils.system_notices import post_site_event_notice

        prev_label = (
            previous_status.value if hasattr(previous_status, "value") else (previous_status or "—")
        )
        new_label = new_status.value if hasattr(new_status, "value") else str(new_status)
        msg = f"Site status changed from {prev_label} to {new_label}"
        if triggering_event:
            msg += f" (trigger: {triggering_event})"
        if reason:
            msg += f" — {reason}"

        await post_site_event_notice(
            db,
            site_ref=site_db_id,
            study_ref=None,  # fan out to every (study, site) board
            event_type="site_status_changed",
            message=msg,
            metadata={
                "previous_status": prev_label,
                "new_status": new_label,
                "triggering_event": triggering_event,
                "reason": reason,
            },
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "record_site_status_change: notice-board hook failed for site=%s", site_db_id
        )

    return current


def _status_priority(status: PrimarySiteStatus) -> int:
    """
    Priority ordering for derived Study/Country statuses.

    RECRUITING is treated specially in higher-level logic; this function is
    used when no site is recruiting and we need the “highest‑priority active”.

    TODO: Confirm final ordering with clinical operations stakeholders.
    """

    ordering = [
        PrimarySiteStatus.RECRUITING,
        PrimarySiteStatus.INITIATED_NOT_RECRUITING,
        PrimarySiteStatus.ACTIVE_NOT_RECRUITING,
        PrimarySiteStatus.INITIATING,
        PrimarySiteStatus.STARTUP,
        PrimarySiteStatus.UNDER_EVALUATION,
        PrimarySiteStatus.COMPLETED,
        PrimarySiteStatus.SUSPENDED,
        PrimarySiteStatus.TERMINATED,
        PrimarySiteStatus.WITHDRAWN,
        PrimarySiteStatus.CLOSED,
    ]
    try:
        return ordering.index(status)
    except ValueError:
        return len(ordering)


def derive_aggregate_status(statuses: List[PrimarySiteStatus]) -> Optional[PrimarySiteStatus]:
    """
    Derive a Country/Study status from a list of site statuses.

    - If ANY site is RECRUITING → RECRUITING
    - Else highest‑priority state according to _status_priority
    """

    if not statuses:
        return None

    if PrimarySiteStatus.RECRUITING in statuses:
        return PrimarySiteStatus.RECRUITING

    return sorted(statuses, key=_status_priority)[0]


async def get_study_status_summary(
    db: AsyncSession,
    study_identifier: str,
) -> Optional[Tuple[Study, Dict[str, Any]]]:
    """
    Build a backend‑driven study status dashboard summary.

    Returns (Study, summary_dict) or None if study not found.
    """

    # Resolve study by UUID id or by study_id string
    try:
        study_uuid = UUID(str(study_identifier))
        study_result = await db.execute(select(Study).where(Study.id == study_uuid))
        study = study_result.scalar_one_or_none()
    except (ValueError, TypeError):
        study_result = await db.execute(select(Study).where(Study.study_id == study_identifier))
        study = study_result.scalar_one_or_none()

    if not study:
        return None

    sites_result = await db.execute(
        select(Site)
        .join(StudySite, StudySite.site_id == Site.id)
        .where(StudySite.study_id == study.id)
    )
    sites = list(sites_result.scalars().all())
    if not sites:
        return study, {
            "study_id": study.study_id,
            "study_name": study.name,
            "study_status": None,
            "total_sites": 0,
            "recruiting_sites": 0,
            "status_counts": {},
            "countries": [],
        }

    site_ids = [s.id for s in sites]

    status_result = await db.execute(select(SiteStatus).where(SiteStatus.site_id.in_(site_ids)))
    status_rows: List[SiteStatus] = list(status_result.scalars().all())

    status_by_site: Dict[UUID, PrimarySiteStatus] = {
        row.site_id: row.current_status for row in status_rows if row.current_status is not None
    }

    status_counter: Counter[PrimarySiteStatus] = Counter()
    country_statuses: Dict[str, List[PrimarySiteStatus]] = defaultdict(list)
    total_sites = len(sites)

    for site in sites:
        current_status = status_by_site.get(site.id)
        if not current_status:
            continue

        status_counter[current_status] += 1
        country_key = site.country or "Unknown"
        country_statuses[country_key].append(current_status)

    recruiting_sites = status_counter.get(PrimarySiteStatus.RECRUITING, 0)

    countries_summary: List[Dict[str, Any]] = []
    for country_name, country_site_statuses in country_statuses.items():
        country_status = derive_aggregate_status(country_site_statuses)
        country_counter = Counter(country_site_statuses)
        countries_summary.append(
            {
                "country": country_name,
                "status": country_status,
                "total_sites": len(country_site_statuses),
                "recruiting_sites": country_counter.get(PrimarySiteStatus.RECRUITING, 0),
                "status_counts": dict(country_counter),
            }
        )

    study_status = derive_aggregate_status(list(status_counter.elements()))

    summary: Dict[str, Any] = {
        "study_id": study.study_id,
        "study_name": study.name,
        "study_status": study_status,
        "total_sites": total_sites,
        "recruiting_sites": recruiting_sites,
        "status_counts": dict(status_counter),
        "countries": countries_summary,
    }
    return study, summary


async def get_country_site_counts(
    db: AsyncSession,
    study_identifier: str,
) -> List[Dict[str, Any]]:
    """
    Return country‑wise site counts and derived status for a given study.
    """

    result = await get_study_status_summary(db, study_identifier)
    if not result:
        return []
    _study, summary = result
    return summary.get("countries", [])


async def get_sites_by_status(
    db: AsyncSession,
    study_identifier: str,
    status: Optional[PrimarySiteStatus] = None,
) -> List[Dict[str, Any]]:
    """
    List sites for a study filtered by current primary status (if provided).
    """

    # Resolve study
    try:
        study_uuid = UUID(str(study_identifier))
        study_result = await db.execute(select(Study).where(Study.id == study_uuid))
        study = study_result.scalar_one_or_none()
    except (ValueError, TypeError):
        study_result = await db.execute(select(Study).where(Study.study_id == study_identifier))
        study = study_result.scalar_one_or_none()

    if not study:
        return []

    sites_result = await db.execute(
        select(Site)
        .join(StudySite, StudySite.site_id == Site.id)
        .where(StudySite.study_id == study.id)
    )
    sites = list(sites_result.scalars().all())
    if not sites:
        return []

    site_ids = [s.id for s in sites]

    status_query = select(SiteStatus).where(SiteStatus.site_id.in_(site_ids))
    if status is not None:
        status_query = status_query.where(SiteStatus.current_status == status)

    status_result = await db.execute(status_query)
    status_rows: List[SiteStatus] = list(status_result.scalars().all())
    status_by_site: Dict[UUID, SiteStatus] = {row.site_id: row for row in status_rows}

    output: List[Dict[str, Any]] = []
    for site in sites:
        st = status_by_site.get(site.id)
        if status is not None and (not st or st.current_status != status):
            continue
        output.append(
            {
                "site_id": str(site.id),
                "site_external_id": site.site_id,
                "name": site.name,
                "country": site.country,
                "current_status": st.current_status if st else None,
                "previous_status": st.previous_status if st else None,
            }
        )
    return output


async def get_site_status_detail(
    db: AsyncSession,
    site_identifier: str,
) -> Optional[Dict[str, Any]]:
    """
    Return detailed status + full history for a given site.
    """

    # Resolve site by UUID id or by site_id string
    try:
        site_uuid = UUID(str(site_identifier))
        site_result = await db.execute(select(Site).where(Site.id == site_uuid))
        site = site_result.scalar_one_or_none()
    except (ValueError, TypeError):
        site_result = await db.execute(select(Site).where(Site.site_id == site_identifier))
        site = site_result.scalar_one_or_none()

    if not site:
        return None

    status_result = await db.execute(select(SiteStatus).where(SiteStatus.site_id == site.id))
    status_row: Optional[SiteStatus] = status_result.scalar_one_or_none()

    history_result = await db.execute(
        select(SiteStatusHistory)
        .where(SiteStatusHistory.site_id == site.id)
        .order_by(SiteStatusHistory.changed_at.asc())
    )
    history_rows: List[SiteStatusHistory] = list(history_result.scalars().all())

    history_serialized: List[Dict[str, Any]] = []
    for row in history_rows:
        history_serialized.append(
            {
                "status": row.status,
                "previous_status": row.previous_status,
                "metadata": row.status_metadata or {},
                "changed_at": row.changed_at,
                "triggering_event": row.triggering_event,
                "reason": row.reason,
            }
        )

    detail: Dict[str, Any] = {
        "site_id": str(site.id),
        "site_external_id": site.site_id,
        "study_id": None,  # optional, keep simple for now
        "name": site.name,
        "country": site.country,
        "current_status": status_row.current_status if status_row else None,
        "previous_status": status_row.previous_status if status_row else None,
        # Secondary statuses/milestones live in metadata for the *current* row
        "secondary_statuses": (status_row.status_metadata or {}) if status_row else {},
        "history": history_serialized,
    }
    return detail


