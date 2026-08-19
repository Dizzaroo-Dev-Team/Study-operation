"""One-time catch-up for the Public Notice Board.

Walks every domain entity that the live hooks now write to the per-(study,
site) notice board (sites, site-status history, agreements, conversations,
tasks, monitoring visits, feasibility requests) and posts a corresponding
"backfilled" message for each one that doesn't already have a board entry.

Why this exists
---------------
The live hooks (see app/utils/system_notices.py + the per-domain call sites)
only fire when an event happens. Entities that already existed in Postgres /
Mongo when the hooks landed have no notice-board entry — this script writes
those missing entries so the board reflects the full history rather than
"things that happened from this moment forward".

Idempotency
-----------
Every message we post here embeds a deterministic
    message_metadata.backfill_source_id = "<kind>:<id>"
key (e.g. "site:<uuid>", "status_history:<uuid>", "agreement:<uuid>").
Before posting, we query the target notice board for a message with that
exact key and skip if it's already there. Re-running the script is a no-op.

Run
---
From repo root, with the same env the API uses:

    cd Backend-CRM
    python -m scripts.backfill_notice_board

Optional scoping (useful while testing on one study+site):

    python -m scripts.backfill_notice_board --study-id <study_uuid> --site-id <site_external_id>
    python -m scripts.backfill_notice_board --dry-run        # log, don't write
    python -m scripts.backfill_notice_board --kinds sites,agreements

The script reuses the live helpers (ensure_public_notice_board,
create_system_notice_message) so any future change to the board's data
shape stays in one place.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any, Iterable, Optional
from uuid import UUID

from sqlalchemy import select, text

from app.db import AsyncSessionLocal
from app.db.mongo import get_mongo_db, close_mongo_client
from app.models import (
    Agreement,
    FeasibilityRequest,
    Site,
    SiteStatusHistory,
    SiteWorkflowStep,
    StepStatus,
    Study,
    StudySite,
    WorkflowStepName,
)
from app.modules.communications.repositories import (
    ConversationRepository,
    MessageRepository,
)
from app.modules.communications.services.conversation_service import (
    ensure_public_notice_board,
)
from app.modules.operations.repositories import TaskRepository
from app.utils.system_notices import create_system_notice_message

logger = logging.getLogger("backfill_notice_board")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

ALL_KINDS = (
    "sites",
    "status_history",
    "agreements",
    "conversations",
    "tasks",
    "monitoring_visits",
    "monitoring_lifecycle",
    "feasibility",
    "workflow_steps",
)


class Counters:
    """Per-kind tally for the final summary print."""

    def __init__(self) -> None:
        self.scanned: dict[str, int] = {k: 0 for k in ALL_KINDS}
        self.posted: dict[str, int] = {k: 0 for k in ALL_KINDS}
        self.skipped: dict[str, int] = {k: 0 for k in ALL_KINDS}

    def summary(self) -> str:
        lines = ["", "Backfill summary:"]
        for kind in ALL_KINDS:
            lines.append(
                f"  {kind:18s}  scanned={self.scanned[kind]:5d}  "
                f"posted={self.posted[kind]:5d}  "
                f"skipped_dedup={self.skipped[kind]:5d}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Site / study resolution helpers (same convention as post_site_event_notice)
# ---------------------------------------------------------------------------


async def _resolve_site(db, ref: Any) -> Optional[Site]:
    if ref is None:
        return None
    if hasattr(ref, "site_id") and hasattr(ref, "id"):
        return ref
    s = str(ref).strip()
    if not s:
        return None
    try:
        uid = UUID(s)
        row = (await db.execute(select(Site).where(Site.id == uid))).scalar_one_or_none()
        if row:
            return row
    except (ValueError, TypeError):
        pass
    return (await db.execute(select(Site).where(Site.site_id == s))).scalar_one_or_none()


async def _study_ids_for_site(db, site: Site) -> list[Optional[str]]:
    """Return the canonical study-id strings (UUID-stringified) that this site
    is mapped to via StudySite. Falls back to ``[None]`` (site-only board)
    when there are no mappings — same fallback the live helper uses.
    """
    rows = await db.execute(
        select(StudySite.study_id).where(StudySite.site_id == site.id)
    )
    out: list[Optional[str]] = [str(r[0]) for r in rows.all() if r[0] is not None]
    return out or [None]


async def _resolve_study_id(db, ref: Any) -> Optional[str]:
    """Resolve to ``str(study.id)`` — same value the live frontend filter sends."""
    if ref is None:
        return None
    if hasattr(ref, "id"):
        return str(ref.id)
    s = str(ref).strip()
    if not s:
        return None
    try:
        uid = UUID(s)
        row = (await db.execute(select(Study).where(Study.id == uid))).scalar_one_or_none()
        if row:
            return str(row.id)
    except (ValueError, TypeError):
        pass
    row = (
        await db.execute(select(Study).where(Study.study_id == s))
    ).scalar_one_or_none()
    return str(row.id) if row else s


# ---------------------------------------------------------------------------
# Dedup-safe post
# ---------------------------------------------------------------------------


async def _post_backfill(
    db,
    *,
    site: Site,
    study_id: Optional[str],
    event_type: str,
    message: str,
    source_id: str,
    counters: Counters,
    kind: str,
    extra_metadata: Optional[dict] = None,
    dry_run: bool = False,
) -> None:
    """Ensure the board, dedup against a prior backfilled message with the
    same ``source_id``, then post via the live helper if not present.
    """
    site_key = site.site_id or str(site.id)

    # Ensure board exists (idempotent — uses Mongo upsert under the hood).
    # Signature is (site_id, study_id) — it talks to Mongo directly, no db session.
    board = await ensure_public_notice_board(site_key, study_id)
    board_id = board.get("id") if isinstance(board, dict) else board.id
    if not board_id:
        logger.warning(
            "could not resolve notice board for site=%s study=%s — skipping %s",
            site_key, study_id, source_id,
        )
        return

    mongo = await get_mongo_db()
    messages_coll = mongo[MessageRepository.COLLECTION_NAME]

    existing = await messages_coll.find_one({
        "conversation_id": str(board_id),
        "message_metadata.backfill_source_id": source_id,
    })
    if existing:
        counters.skipped[kind] += 1
        return

    if dry_run:
        logger.info(
            "[DRY] would post: site=%s study=%s event=%s source=%s msg=%r",
            site_key, study_id, event_type, source_id, message,
        )
        counters.posted[kind] += 1
        return

    merged: dict[str, Any] = {
        "backfill": True,
        "backfill_source_id": source_id,
    }
    if extra_metadata:
        merged.update(extra_metadata)

    try:
        await create_system_notice_message(
            db=db,
            site_id=site_key,
            study_id=study_id,
            message=message,
            event_type=event_type,
            metadata=merged,
        )
        counters.posted[kind] += 1
    except Exception:
        logger.exception(
            "post failed: site=%s study=%s event=%s source=%s",
            site_key, study_id, event_type, source_id,
        )


# ---------------------------------------------------------------------------
# Per-kind walkers
# ---------------------------------------------------------------------------


def _site_filter_match(site: Site, site_id_filter: Optional[str]) -> bool:
    if not site_id_filter:
        return True
    f = site_id_filter.strip()
    return f in (site.site_id or "", str(site.id))


def _study_filter_match(study_id: Optional[str], study_id_filter: Optional[str]) -> bool:
    if not study_id_filter:
        return True
    return study_id == study_id_filter.strip() if study_id else False


async def backfill_sites(
    db, counters: Counters, study_id_filter: Optional[str], site_id_filter: Optional[str], dry_run: bool
) -> None:
    sites = list((await db.execute(select(Site))).scalars().all())
    studies_cache: dict[Any, Study] = {}

    for site in sites:
        if not _site_filter_match(site, site_id_filter):
            continue

        # For each study this site is mapped to, post one entry.
        mappings = (
            await db.execute(select(StudySite).where(StudySite.site_id == site.id))
        ).scalars().all()
        if not mappings:
            counters.scanned["sites"] += 1
            continue

        for m in mappings:
            sid = str(m.study_id)
            if not _study_filter_match(sid, study_id_filter):
                continue
            counters.scanned["sites"] += 1

            study = studies_cache.get(m.study_id)
            if study is None:
                study = (
                    await db.execute(select(Study).where(Study.id == m.study_id))
                ).scalar_one_or_none()
                if study is None:
                    continue
                studies_cache[m.study_id] = study

            await _post_backfill(
                db,
                site=site,
                study_id=sid,
                event_type="site_created",
                message=(
                    f"Site '{site.name or site.site_id}' is mapped to study "
                    f"'{study.name or study.study_id}'."
                ),
                source_id=f"site:{site.id}:{study.id}",
                counters=counters,
                kind="sites",
                extra_metadata={
                    "site_id": str(site.id),
                    "site_external_id": site.site_id,
                    "study_id": str(study.id),
                    "study_external_id": study.study_id,
                },
                dry_run=dry_run,
            )


async def backfill_status_history(
    db, counters: Counters, study_id_filter: Optional[str], site_id_filter: Optional[str], dry_run: bool
) -> None:
    rows = list(
        (
            await db.execute(
                select(SiteStatusHistory).order_by(SiteStatusHistory.changed_at.asc())
            )
        ).scalars().all()
    )

    site_cache: dict[Any, Site] = {}

    for h in rows:
        counters.scanned["status_history"] += 1

        site = site_cache.get(h.site_id)
        if site is None:
            site = await _resolve_site(db, h.site_id)
            if site is None:
                continue
            site_cache[h.site_id] = site
        if not _site_filter_match(site, site_id_filter):
            continue

        study_ids = await _study_ids_for_site(db, site)
        new_label = h.status.value if hasattr(h.status, "value") else str(h.status)
        prev_label = (
            h.previous_status.value if hasattr(h.previous_status, "value") else (h.previous_status or "—")
        )
        msg = f"Site status changed from {prev_label} to {new_label}"
        if getattr(h, "triggering_event", None):
            msg += f" (trigger: {h.triggering_event})"
        if getattr(h, "reason", None):
            msg += f" — {h.reason}"

        for sid in study_ids:
            if not _study_filter_match(sid, study_id_filter):
                continue
            await _post_backfill(
                db,
                site=site,
                study_id=sid,
                event_type="site_status_changed",
                message=msg,
                source_id=f"status_history:{h.site_id}:{h.changed_at.isoformat() if h.changed_at else h.status}",
                counters=counters,
                kind="status_history",
                extra_metadata={
                    "previous_status": prev_label,
                    "new_status": new_label,
                    "triggering_event": getattr(h, "triggering_event", None),
                    "reason": getattr(h, "reason", None),
                    "changed_at": h.changed_at.isoformat() if h.changed_at else None,
                    "historical": True,
                },
                dry_run=dry_run,
            )


async def backfill_agreements(
    db, counters: Counters, study_id_filter: Optional[str], site_id_filter: Optional[str], dry_run: bool
) -> None:
    """Read agreements via raw SQL with an explicit column list.

    The `Agreement` ORM model declares some recently-added columns
    (e.g. ``amendment_of_id``) that may not yet exist on every deployed
    Postgres — Neon was behind one such migration when this walker first
    ran. Using ``select(Agreement)`` makes SQLAlchemy emit every mapped
    column, and one missing column makes the whole query fail.
    Hand-picking only what the walker actually reads sidesteps the drift
    and keeps the backfill resilient against future model additions too.
    """
    try:
        result = await db.execute(text(
            "SELECT id, site_id, study_site_id, study_id, title, status, "
            "agreement_type, created_at FROM agreements"
        ))
    except Exception as e:
        logger.warning("agreements scan failed (skipping): %s", e)
        return

    for row in result.mappings().all():
        counters.scanned["agreements"] += 1

        site = await _resolve_site(db, row.get("site_id"))
        if site is None:
            continue
        if not _site_filter_match(site, site_id_filter):
            continue

        # Resolve study via Agreement.study_id or StudySite mapping (mirrors
        # create_agreement_notice).
        study_id: Optional[str] = None
        if row.get("study_id"):
            study_id = str(row["study_id"])
        elif row.get("study_site_id"):
            ss = (
                await db.execute(
                    select(StudySite).where(StudySite.id == row["study_site_id"])
                )
            ).scalar_one_or_none()
            if ss:
                study_id = str(ss.study_id)
        if not _study_filter_match(study_id, study_id_filter):
            continue

        # Raw SQL returns enum columns as plain strings — no `.value` needed.
        type_code = str(row.get("agreement_type") or "agreement")
        status_label = str(row.get("status") or "")
        created_at = row.get("created_at")

        await _post_backfill(
            db,
            site=site,
            study_id=study_id,
            event_type="agreement_created",
            message=(
                f"{type_code.upper()} '{row.get('title') or row.get('id')}' exists for this site "
                f"(current status: {status_label})."
            ),
            source_id=f"agreement:{row.get('id')}",
            counters=counters,
            kind="agreements",
            extra_metadata={
                "agreement_id": str(row.get("id")),
                "agreement_type": type_code,
                "current_status": status_label,
                "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else (str(created_at) if created_at else None),
            },
            dry_run=dry_run,
        )


async def backfill_conversations(
    db, counters: Counters, study_id_filter: Optional[str], site_id_filter: Optional[str], dry_run: bool
) -> None:
    mongo = await get_mongo_db()
    coll = mongo[ConversationRepository.COLLECTION_NAME]

    query: dict[str, Any] = {
        "conversation_type": "thread",  # skip notice_board itself
        "site_id": {"$ne": None},
    }
    cursor = coll.find(query)
    async for conv in cursor:
        counters.scanned["conversations"] += 1

        site_ref = conv.get("site_id")
        study_ref = conv.get("study_id")
        site = await _resolve_site(db, site_ref)
        if site is None:
            continue
        if not _site_filter_match(site, site_id_filter):
            continue

        study_id = await _resolve_study_id(db, study_ref)
        if not _study_filter_match(study_id, study_id_filter):
            continue

        title = conv.get("title") or conv.get("subject") or "(no subject)"
        actor = conv.get("created_by") or "an earlier user"

        await _post_backfill(
            db,
            site=site,
            study_id=study_id,
            event_type="conversation_created",
            message=f"Conversation '{title}' was started by {actor}.",
            source_id=f"conversation:{conv.get('id')}",
            counters=counters,
            kind="conversations",
            extra_metadata={
                "conversation_id": str(conv.get("id")),
                "created_at": (
                    conv.get("created_at").isoformat()
                    if hasattr(conv.get("created_at"), "isoformat")
                    else conv.get("created_at")
                ),
            },
            dry_run=dry_run,
        )


async def backfill_tasks(
    db, counters: Counters, study_id_filter: Optional[str], site_id_filter: Optional[str], dry_run: bool
) -> None:
    mongo = await get_mongo_db()
    coll = mongo[TaskRepository.COLLECTION_NAME]

    cursor = coll.find({})
    async for task in cursor:
        counters.scanned["tasks"] += 1

        site_ref = task.get("siteId") or ((task.get("links") or {}).get("siteId"))
        if not site_ref:
            continue
        site = await _resolve_site(db, site_ref)
        if site is None:
            continue
        if not _site_filter_match(site, site_id_filter):
            continue

        study_ids = await _study_ids_for_site(db, site)
        title = task.get("title") or task.get("description") or "untitled task"
        actor = (
            task.get("assigneeName")
            or task.get("requestedBy")
            or task.get("createdByUserId")
            or "an earlier user"
        )

        for sid in study_ids:
            if not _study_filter_match(sid, study_id_filter):
                continue
            await _post_backfill(
                db,
                site=site,
                study_id=sid,
                event_type="task_created",
                message=f"Task '{title}' was created by {actor}.",
                source_id=f"task:{task.get('id')}",
                counters=counters,
                kind="tasks",
                extra_metadata={
                    "task_id": task.get("id"),
                    "status": task.get("status"),
                    "created_at": task.get("createdAt"),
                },
                dry_run=dry_run,
            )


async def backfill_monitoring_visits(
    db, counters: Counters, study_id_filter: Optional[str], site_id_filter: Optional[str], dry_run: bool
) -> None:
    # monitoring_visits is a raw-SQL table (see modules/monitoring/routes/visits.py).
    try:
        result = await db.execute(text(
            "SELECT id, site_id, study_id, visit_type, visit_date, visit_date_iso, "
            "priority, cra_name, site_visit_number "
            "FROM monitoring_visits"
        ))
    except Exception as e:
        logger.warning("monitoring_visits table not queryable, skipping (%s)", e)
        return

    for row in result.mappings().all():
        counters.scanned["monitoring_visits"] += 1
        site_ref = row.get("site_id")
        if not site_ref:
            continue
        site = await _resolve_site(db, site_ref)
        if site is None:
            continue
        if not _site_filter_match(site, site_id_filter):
            continue

        study_id = await _resolve_study_id(db, row.get("study_id"))
        if study_id is None:
            study_ids = await _study_ids_for_site(db, site)
        else:
            study_ids = [study_id]

        when = row.get("visit_date_iso") or row.get("visit_date") or "TBD"
        msg = (
            f"{row.get('visit_type') or 'Monitoring'} visit scheduled for {when} — "
            f"CRA {row.get('cra_name') or 'unassigned'}, priority "
            f"{row.get('priority') or 'medium'}."
        )

        for sid in study_ids:
            if not _study_filter_match(sid, study_id_filter):
                continue
            await _post_backfill(
                db,
                site=site,
                study_id=sid,
                event_type="monitoring_visit_created",
                message=msg,
                source_id=f"monitoring_visit:{row.get('id')}",
                counters=counters,
                kind="monitoring_visits",
                extra_metadata={
                    "visit_id": row.get("id"),
                    "visit_type": row.get("visit_type"),
                    "visit_date_iso": row.get("visit_date_iso"),
                    "priority": row.get("priority"),
                    "cra_name": row.get("cra_name"),
                    "site_visit_number": row.get("site_visit_number"),
                },
                dry_run=dry_run,
            )


async def backfill_feasibility(
    db, counters: Counters, study_id_filter: Optional[str], site_id_filter: Optional[str], dry_run: bool
) -> None:
    rows = list((await db.execute(select(FeasibilityRequest))).scalars().all())

    for fr in rows:
        counters.scanned["feasibility"] += 1
        ss = (
            await db.execute(select(StudySite).where(StudySite.id == fr.study_site_id))
        ).scalar_one_or_none()
        if ss is None:
            continue
        site = await _resolve_site(db, ss.site_id)
        if site is None:
            continue
        if not _site_filter_match(site, site_id_filter):
            continue
        study_id = await _resolve_study_id(db, ss.study_id)
        if not _study_filter_match(study_id, study_id_filter):
            continue

        # "Sent" notice — every request was sent at creation time.
        await _post_backfill(
            db,
            site=site,
            study_id=study_id,
            event_type="feasibility_request_sent",
            message=f"Feasibility form sent to {fr.email}.",
            source_id=f"feasibility_sent:{fr.id}",
            counters=counters,
            kind="feasibility",
            extra_metadata={
                "feasibility_request_id": str(fr.id),
                "study_site_id": str(ss.id),
                "recipient_email": fr.email,
                "created_at": fr.created_at.isoformat() if fr.created_at else None,
            },
            dry_run=dry_run,
        )

        # "Submitted" notice — only if completed.
        status = (
            fr.status.value if hasattr(fr.status, "value") else str(fr.status)
        ).strip().lower()
        if status == "completed":
            await _post_backfill(
                db,
                site=site,
                study_id=study_id,
                event_type="feasibility_submitted",
                message=f"Feasibility form was submitted by {fr.email}.",
                source_id=f"feasibility_submitted:{fr.id}",
                counters=counters,
                kind="feasibility",
                extra_metadata={
                    "feasibility_request_id": str(fr.id),
                    "study_site_id": str(ss.id),
                    "submitted_by_email": fr.email,
                    "updated_at": fr.updated_at.isoformat() if fr.updated_at else None,
                },
                dry_run=dry_run,
            )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


async def backfill_monitoring_lifecycle(
    db, counters: Counters, study_id_filter: Optional[str], site_id_filter: Optional[str], dry_run: bool
) -> None:
    """Catch-up for the four monitoring lifecycle hooks added later: visit
    closed, finding created, reschedule requested, report approved/rejected.

    Reads raw rows from the monitoring tables (no ORM models — these tables
    are raw-SQL-managed by monitoring/routes/visits.py & co), resolves each
    row's visit → (site, study), and posts a notice keyed on a per-row
    source_id so re-runs are idempotent.
    """
    # Lookup: visit_id → (site_id, study_id, visit_type, site_visit_number)
    async def _visit_info(visit_id: str) -> Optional[dict]:
        try:
            res = await db.execute(
                text(
                    "SELECT site_id, study_id, visit_type, site_visit_number, cra_name "
                    "FROM monitoring_visits WHERE id = :id"
                ),
                {"id": visit_id},
            )
            row = res.mappings().first()
            return dict(row) if row else None
        except Exception:
            return None

    # 1) Closed visits
    try:
        closed = await db.execute(
            text(
                "SELECT id, site_id, study_id, visit_type, site_visit_number, cra_name "
                "FROM monitoring_visits "
                "WHERE closed_at IS NOT NULL OR LOWER(status) = 'closed'"
            )
        )
    except Exception as e:
        logger.warning("monitoring_visits closed scan failed: %s", e)
        closed = None

    if closed is not None:
        for row in closed.mappings().all():
            counters.scanned["monitoring_lifecycle"] += 1
            site_ref = row.get("site_id")
            if not site_ref:
                continue
            site = await _resolve_site(db, site_ref)
            if site is None or not _site_filter_match(site, site_id_filter):
                continue
            study_id = await _resolve_study_id(db, row.get("study_id"))
            if not _study_filter_match(study_id, study_id_filter):
                continue
            num = row.get("site_visit_number")
            tail = f" (visit #{num})" if num else ""
            label = row.get("visit_type") or "Monitoring"
            await _post_backfill(
                db,
                site=site,
                study_id=study_id,
                event_type="monitoring_visit_closed",
                message=f"{label} visit{tail} was closed and locked by {row.get('cra_name') or 'CRA'}.",
                source_id=f"monitoring_visit_closed:{row.get('id')}",
                counters=counters,
                kind="monitoring_lifecycle",
                extra_metadata={"visit_id": row.get("id"), "cra_name": row.get("cra_name")},
                dry_run=dry_run,
            )

    # 2) Findings
    try:
        findings = await db.execute(
            text(
                "SELECT id, visit_id, category, severity, description, assignee_name, due_date "
                "FROM monitoring_findings"
            )
        )
    except Exception as e:
        logger.warning("monitoring_findings scan failed: %s", e)
        findings = None

    if findings is not None:
        for row in findings.mappings().all():
            counters.scanned["monitoring_lifecycle"] += 1
            info = await _visit_info(str(row.get("visit_id") or ""))
            if not info or not info.get("site_id"):
                continue
            site = await _resolve_site(db, info["site_id"])
            if site is None or not _site_filter_match(site, site_id_filter):
                continue
            study_id = await _resolve_study_id(db, info.get("study_id"))
            if not _study_filter_match(study_id, study_id_filter):
                continue
            cat = row.get("category") or "General"
            sev = row.get("severity") or "Major"
            desc = (row.get("description") or "").strip()
            short = (desc[:80] + "…") if len(desc) > 80 else desc
            num = info.get("site_visit_number")
            visit_label = f"visit #{num}" if num else "visit"
            await _post_backfill(
                db,
                site=site,
                study_id=study_id,
                event_type="monitoring_finding_created",
                message=(
                    f"Finding {row.get('id')} ({cat}, {sev}) on {visit_label}"
                    + (f": {short}" if short else ".")
                ),
                source_id=f"monitoring_finding:{row.get('id')}",
                counters=counters,
                kind="monitoring_lifecycle",
                extra_metadata={
                    "visit_id": row.get("visit_id"),
                    "finding_id": row.get("id"),
                    "category": cat,
                    "severity": sev,
                    "assignee_name": row.get("assignee_name"),
                    "due_date": row.get("due_date"),
                },
                dry_run=dry_run,
            )

    # 3) Reschedule requests
    try:
        resched = await db.execute(
            text(
                "SELECT id, visit_id, proposed_date, reason, status, created_at "
                "FROM visit_reschedule_requests"
            )
        )
    except Exception as e:
        logger.warning("visit_reschedule_requests scan failed: %s", e)
        resched = None

    if resched is not None:
        for row in resched.mappings().all():
            counters.scanned["monitoring_lifecycle"] += 1
            info = await _visit_info(str(row.get("visit_id") or ""))
            if not info or not info.get("site_id"):
                continue
            site = await _resolve_site(db, info["site_id"])
            if site is None or not _site_filter_match(site, site_id_filter):
                continue
            study_id = await _resolve_study_id(db, info.get("study_id"))
            if not _study_filter_match(study_id, study_id_filter):
                continue
            num = info.get("site_visit_number")
            tail = f" #{num}" if num else ""
            label = info.get("visit_type") or "Monitoring"
            proposed = row.get("proposed_date")
            proposed_iso = (
                proposed.isoformat()
                if hasattr(proposed, "isoformat")
                else (str(proposed) if proposed else "TBD")
            )
            await _post_backfill(
                db,
                site=site,
                study_id=study_id,
                event_type="monitoring_visit_rescheduled",
                message=(
                    f"{label} visit{tail} reschedule requested — "
                    f"proposed: {proposed_iso}. Reason: {row.get('reason') or '—'}"
                ),
                source_id=f"monitoring_reschedule:{row.get('id')}",
                counters=counters,
                kind="monitoring_lifecycle",
                extra_metadata={
                    "visit_id": row.get("visit_id"),
                    "reschedule_request_id": str(row.get("id")),
                    "proposed_datetime_iso": proposed_iso,
                    "reason": row.get("reason"),
                    "status": row.get("status"),
                },
                dry_run=dry_run,
            )

    # 4) Report approved / rejected — payload JSON column
    try:
        reports = await db.execute(
            text("SELECT visit_id, payload FROM monitoring_visit_reports")
        )
    except Exception as e:
        logger.warning("monitoring_visit_reports scan failed: %s", e)
        reports = None

    if reports is not None:
        for row in reports.mappings().all():
            counters.scanned["monitoring_lifecycle"] += 1
            payload = row.get("payload") or {}
            # payload comes back as dict (jsonb) — defensively handle str too
            if isinstance(payload, str):
                try:
                    import json as _json
                    payload = _json.loads(payload)
                except Exception:
                    payload = {}
            status_label = str((payload or {}).get("reportStatus") or "").strip().lower()
            if status_label not in ("approved", "rejected"):
                continue
            info = await _visit_info(str(row.get("visit_id") or ""))
            if not info or not info.get("site_id"):
                continue
            site = await _resolve_site(db, info["site_id"])
            if site is None or not _site_filter_match(site, site_id_filter):
                continue
            study_id = await _resolve_study_id(db, info.get("study_id"))
            if not _study_filter_match(study_id, study_id_filter):
                continue
            num = info.get("site_visit_number")
            tail = f" #{num}" if num else ""
            label = info.get("visit_type") or "Monitoring"
            if status_label == "approved":
                msg = f"{label} visit{tail} report was approved."
                event_type = "monitoring_visit_report_approved"
                src = f"monitoring_report_approved:{row.get('visit_id')}"
            else:
                reason = str((payload or {}).get("rejectionReason") or "").strip()
                reason_short = (reason[:120] + "…") if len(reason) > 120 else reason
                msg = (
                    f"{label} visit{tail} report was rejected"
                    + (f" — reason: {reason_short}" if reason_short else ".")
                )
                event_type = "monitoring_visit_report_rejected"
                src = f"monitoring_report_rejected:{row.get('visit_id')}"
            await _post_backfill(
                db,
                site=site,
                study_id=study_id,
                event_type=event_type,
                message=msg,
                source_id=src,
                counters=counters,
                kind="monitoring_lifecycle",
                extra_metadata={
                    "visit_id": row.get("visit_id"),
                    "report_status": status_label,
                    "rejection_reason": (payload or {}).get("rejectionReason"),
                },
                dry_run=dry_run,
            )


async def backfill_workflow_steps(
    db, counters: Counters, study_id_filter: Optional[str], site_id_filter: Optional[str], dry_run: bool
) -> None:
    """Catch up Under-Consideration workflow step completions.

    Mirrors the post-completion notice the live route now emits (see
    `modules/clinical_workflow/routes/workflow_steps.py`). Only rows whose
    status is COMPLETED produce a notice — in-progress / not-started rows
    are skipped (a notice for "step started" would just be noise).
    """
    rows = list(
        (
            await db.execute(
                select(SiteWorkflowStep)
                .where(SiteWorkflowStep.status == StepStatus.COMPLETED)
                .order_by(SiteWorkflowStep.completed_at.asc())
            )
        ).scalars().all()
    )

    def _label(v: Any) -> str:
        if v is None:
            return "—"
        return str(v).replace("_", " ").strip().title() or "—"

    site_cache: dict[Any, Site] = {}

    for step in rows:
        counters.scanned["workflow_steps"] += 1

        # Study-specific steps (Site Identification, CDA, Feasibility, Site
        # Selection Outcome) carry study_site_id with step.site_id = NULL.
        # Resolve via StudySite when site_id is missing — otherwise we'd
        # silently skip every row that matters (which is exactly what the
        # first version of this walker did: posted=0, skipped_dedup=0).
        resolved_site_id = step.site_id
        study_id: Optional[str] = None
        if step.study_site_id:
            ss = (
                await db.execute(select(StudySite).where(StudySite.id == step.study_site_id))
            ).scalar_one_or_none()
            if ss:
                if ss.study_id:
                    study_id = str(ss.study_id)
                if resolved_site_id is None and ss.site_id:
                    resolved_site_id = ss.site_id

        if resolved_site_id is None:
            continue

        site = site_cache.get(resolved_site_id)
        if site is None:
            site = await _resolve_site(db, resolved_site_id)
            if site is None:
                continue
            site_cache[resolved_site_id] = site
        if not _site_filter_match(site, site_id_filter):
            continue
        if not _study_filter_match(study_id, study_id_filter):
            continue

        sd = step.step_data or {}
        step_name_value = (
            step.step_name.value if hasattr(step.step_name, "value") else str(step.step_name)
        )

        if step_name_value == WorkflowStepName.SITE_IDENTIFICATION.value:
            msg = f"Step 1: Site Identification completed — Decision: {_label(sd.get('decision'))}"
            event_type = "workflow_site_identification_completed"
        elif step_name_value == WorkflowStepName.CDA_EXECUTION.value:
            req = sd.get("cda_required") or sd.get("cda_status")
            msg = f"Step 2: CDA Execution completed — CDA Required: {_label(req)}"
            event_type = "workflow_cda_execution_completed"
        elif step_name_value == WorkflowStepName.FEASIBILITY.value:
            visit = sd.get("onsite_visit") or sd.get("on_site_visit")
            resp = sd.get("feasibility_outcome") or sd.get("response_received")
            bits = []
            if visit is not None:
                bits.append(f"On-site Visit: {_label(visit)}")
            if resp is not None:
                bits.append(f"Outcome: {_label(resp)}")
            tail = " — " + " · ".join(bits) if bits else ""
            msg = f"Step 3: Feasibility completed{tail}"
            event_type = "workflow_feasibility_completed"
        elif step_name_value == WorkflowStepName.SITE_SELECTION_OUTCOME.value:
            outcome = sd.get("decision") or sd.get("outcome") or sd.get("selection_outcome")
            msg = f"Step 4: Final Site Selection completed — Decision: {_label(outcome)}"
            event_type = "workflow_site_selection_completed"
        else:
            msg = f"Workflow step '{step_name_value}' marked as completed."
            event_type = "workflow_step_completed"

        await _post_backfill(
            db,
            site=site,
            study_id=study_id,
            event_type=event_type,
            message=msg,
            source_id=f"workflow_step:{step.id}",
            counters=counters,
            kind="workflow_steps",
            extra_metadata={
                "step_name": step_name_value,
                "step_data": sd,
                "completed_at": step.completed_at.isoformat() if step.completed_at else None,
                "completed_by": step.completed_by,
                "site_id": str(resolved_site_id),
                "study_site_id": str(step.study_site_id) if step.study_site_id else None,
            },
            dry_run=dry_run,
        )


WALKERS = {
    "sites": backfill_sites,
    "status_history": backfill_status_history,
    "agreements": backfill_agreements,
    "conversations": backfill_conversations,
    "tasks": backfill_tasks,
    "monitoring_visits": backfill_monitoring_visits,
    "monitoring_lifecycle": backfill_monitoring_lifecycle,
    "feasibility": backfill_feasibility,
    "workflow_steps": backfill_workflow_steps,
}


async def run(
    *,
    study_id_filter: Optional[str],
    site_id_filter: Optional[str],
    kinds: Iterable[str],
    dry_run: bool,
) -> Counters:
    """Each walker runs in its OWN AsyncSession.

    Why per-walker sessions: Postgres aborts the whole transaction when any
    statement errors, and asyncpg then refuses every subsequent query in
    that session with `InFailedSQLTransactionError`. If walkers shared one
    session, an unrelated crash in `agreements` (e.g. a missing column on
    Neon) would silently zero-out every walker that runs after it. Giving
    each walker a fresh session means at worst the failing walker reports
    `posted=0` and the rest carry on with intact transactions.
    """
    counters = Counters()
    for kind in kinds:
        walker = WALKERS.get(kind)
        if walker is None:
            logger.warning("unknown kind %r — skipping", kind)
            continue
        logger.info("→ backfilling %s ...", kind)
        try:
            async with AsyncSessionLocal() as db:
                await walker(db, counters, study_id_filter, site_id_filter, dry_run)
        except Exception:
            logger.exception("walker %s crashed (continuing with next kind)", kind)
    return counters


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--study-id",
        dest="study_id",
        default=None,
        help="Only backfill rows whose resolved study_id matches (UUID string).",
    )
    p.add_argument(
        "--site-id",
        dest="site_id",
        default=None,
        help="Only backfill rows whose Site has this external site_id (or UUID).",
    )
    p.add_argument(
        "--kinds",
        default=",".join(ALL_KINDS),
        help=f"Comma-separated subset of {ALL_KINDS}. Default: all.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be posted without writing to the DB.",
    )
    return p.parse_args()


async def _main() -> None:
    args = _parse_args()
    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
    try:
        counters = await run(
            study_id_filter=args.study_id,
            site_id_filter=args.site_id,
            kinds=kinds,
            dry_run=args.dry_run,
        )
        print(counters.summary())
    finally:
        try:
            await close_mongo_client()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(_main())
