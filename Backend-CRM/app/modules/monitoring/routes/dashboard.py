"""REST API: dashboard cluster (Phase 2.2 extract).

Verbatim relocation from app/monitor/router.py. All helpers + Pydantic body
classes are imported from the parent router because they're defined before
the parent's include_router(...) lines, which means they're already available
when this module loads.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import io
import json
import logging
import os
import re
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import AsyncSessionLocal, get_db
from app.integrations.smtp_service import smtp_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["monitor"])

from app.modules.monitoring.utils import (
    dashboard_site_filter_sql,
    dashboard_study_filter_sql,
    effective_visit_status,
    relative_time_label,
)

# Pull legacy helpers + body schemas from the parent router.
from app.modules.monitoring.aggregator import (  # noqa: E402
    _ensure_monitor_tables,
    _normalize_visit_site_bucket,
    _require_monitoring_visit,
    _status_from_risk,
    _normalize_visit_site_bucket,
    _visit_label_from_site_number,
    _rewrite_visit_id_in_text,
)
# _single_dashboard_visit_payload is defined LATER in this same file -- it was
# pulled in alongside the dashboard endpoints during the Phase 2.2 split.


@router.get("/tables/status")
async def get_monitor_tables_status(db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    names = [
        "monitoring_visits",
        "monitoring_visit_objectives",
        "monitoring_visit_activity",
        "monitoring_confirmation_letters",
        "monitoring_pre_visit",
        "monitoring_pre_visit_checklist",
        "monitoring_findings",
        "monitoring_documents",
        "monitoring_threads",
        "monitoring_messages",
        "monitoring_post_visit",
        "monitoring_follow_up_letters",
        "monitoring_visit_reports",
        "monitoring_mvr_templates",
        "visit_reschedule_requests",
    ]
    present = set()
    for table_name in names:
        result = await db.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = :table_name
                )
                """
            ),
            {"table_name": table_name},
        )
        if result.scalar():
            present.add(table_name)
    return {
        "required_tables": names,
        "present_tables": sorted(list(present)),
        "missing_tables": [name for name in names if name not in present],
    }


@router.get("/notifications")
async def get_notifications(db: AsyncSession = Depends(get_db)):
    """
    Build real notifications from live DB data:
    - Overdue open findings (critical/major) → 🚨 alert
    - Upcoming visits in next 7 days → 📅 alert
    - Recent activity in last 48 hours → ✅/📝 info
    """
    await _ensure_monitor_tables(db)
    now = datetime.now(timezone.utc)
    notifs: List[Dict[str, Any]] = []

    def _sort_at_iso(dt: Any) -> str:
        """UTC ISO-8601 for ordering (newest first via lexicographic desc)."""
        if dt is None:
            return "1970-01-01T00:00:00+00:00"
        try:
            if isinstance(dt, str):
                s = dt.strip().replace("Z", "+00:00")
                if not s:
                    return "1970-01-01T00:00:00+00:00"
                if len(s) == 10 and s[4] == "-" and s[7] == "-":
                    dt = datetime.fromisoformat(f"{s}T12:00:00+00:00")
                else:
                    dt = datetime.fromisoformat(s)
            if getattr(dt, "tzinfo", None) is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            return "1970-01-01T00:00:00+00:00"

    # The four notification sources below are fully independent — neither
    # depends on data the others return. Previously they ran sequentially on
    # the request session, so dashboard /notifications paid for the sum of
    # four round-trips. Each is now its own short-lived AsyncSession (the
    # request-bound `db` cannot service concurrent execute() calls) and they
    # run in parallel via asyncio.gather.
    #
    # Per-block try/except is preserved so any one source failing still
    # returns the others — same semantics as the old sequential code.
    #
    # `id` numbering is dropped here because the function re-numbers below
    # after sorting, which means the old per-block `notif_id` increments
    # were already throwaway.

    async def _block_overdue_findings() -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    text(
                        """
                        SELECT f.id, f.category, f.severity, f.due_date, f.due_color,
                               COALESCE(s.name, v.site_id, 'Site') AS site_name,
                               v.id AS visit_id,
                               v.site_visit_number
                        FROM monitoring_findings f
                        LEFT JOIN monitoring_visits v ON v.id = f.visit_id
                        LEFT JOIN sites s ON (
                            v.site_id IS NOT NULL AND
                            (v.site_id = s.site_id OR v.site_id = CAST(s.id AS TEXT))
                        )
                        WHERE LOWER(TRIM(COALESCE(f.status, ''))) NOT IN ('resolved', 'archived', 'closed')
                          AND f.due_color IN ('red', 'orange')
                        ORDER BY f.id DESC
                        LIMIT 10
                        """
                    )
                )
                rows = res.mappings().all()
            for row in rows:
                icon = "🚨" if (row.get("severity") or "").lower() == "critical" else "⚠️"
                due_str = row.get("due_date") or "soon"
                site_str = row.get("site_name") or ""
                vid = str(row.get("visit_id") or "").strip()
                vlabel = _visit_label_from_site_number(row.get("site_visit_number"), vid) if vid else ""
                text_val = f"{row['severity']} finding ({row['category']}) due {due_str}"
                if site_str:
                    text_val += f" — {site_str}"
                if vlabel and vid and vlabel != vid:
                    text_val += f" ({vlabel})"
                sort_key = _sort_at_iso(row.get("due_date"))
                if sort_key.startswith("1970-01-01"):
                    sort_key = now.isoformat()
                out.append({
                    "icon": icon,
                    "text": text_val,
                    "time": f"Due {due_str}",
                    "unread": True,
                    "type": "finding",
                    "sort_at": sort_key,
                })
        except Exception:
            pass
        return out

    async def _block_upcoming_visits() -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    text(
                        """
                        SELECT v.id, v.visit_date, v.visit_date_iso, v.updated_at,
                               COALESCE(s.name, v.site_id, 'Unknown Site') AS site_name
                        FROM monitoring_visits v
                        LEFT JOIN sites s ON (
                            v.site_id IS NOT NULL AND
                            (v.site_id = s.site_id OR v.site_id = CAST(s.id AS TEXT))
                        )
                        WHERE v.status IN ('scheduled', 'site confirmed', 'post-visit action')
                          AND NULLIF(v.visit_date_iso, '') IS NOT NULL
                        ORDER BY v.visit_date_iso ASC
                        LIMIT 5
                        """
                    )
                )
                rows = res.mappings().all()
            for row in rows:
                iso = row.get("visit_date_iso") or ""
                try:
                    visit_dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                    delta = (visit_dt - now).days
                    if delta < 0:
                        continue
                    if delta == 0:
                        time_label = "Today"
                    elif delta == 1:
                        time_label = "Tomorrow"
                    else:
                        time_label = f"In {delta} days"
                    site_name = row.get("site_name") or "a site"
                    upd = row.get("updated_at")
                    if upd is not None and getattr(upd, "tzinfo", None) is None:
                        upd = upd.replace(tzinfo=timezone.utc)
                    visit_sort = upd if upd is not None else visit_dt
                    if visit_sort is not None and getattr(visit_sort, "tzinfo", None) is None:
                        visit_sort = visit_sort.replace(tzinfo=timezone.utc)
                    out.append({
                        "icon": "📅",
                        "text": f"Visit at {site_name} scheduled — {row['visit_date']}",
                        "time": time_label,
                        "unread": delta <= 3,
                        "type": "visit",
                        "sort_at": _sort_at_iso(visit_sort),
                    })
                except Exception:
                    pass
        except Exception:
            pass
        return out

    async def _block_confirmed_visits() -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    text(
                        """
                        SELECT
                            v.id,
                            v.visit_date,
                            COALESCE(s.name, v.site_id, 'Unknown Site') AS site_name,
                            c.confirmed_at
                        FROM monitoring_confirmation_letters c
                        JOIN monitoring_visits v ON v.id = c.visit_id
                        LEFT JOIN sites s ON (
                            v.site_id IS NOT NULL AND
                            (v.site_id = s.site_id OR v.site_id = CAST(s.id AS TEXT))
                        )
                        WHERE c.confirmed_at IS NOT NULL
                        ORDER BY c.confirmed_at DESC
                        LIMIT 10
                        """
                    )
                )
                rows = res.mappings().all()
            for row in rows:
                confirmed_at = row.get("confirmed_at")
                if confirmed_at is None:
                    continue
                try:
                    if confirmed_at.tzinfo is None:
                        confirmed_at = confirmed_at.replace(tzinfo=timezone.utc)
                    age_hours = (now - confirmed_at).total_seconds() / 3600
                except Exception:
                    age_hours = 999
                time_label = relative_time_label(confirmed_at, now=now)

                site_name = row.get("site_name") or "Unknown Site"
                visit_date = row.get("visit_date") or "TBD date"
                out.append(
                    {
                        "icon": "✅",
                        "text": f"Site {site_name} has confirmed the visit for {visit_date}.",
                        "time": time_label,
                        "unread": age_hours <= 72,
                        "type": "visit",
                        "sort_at": _sort_at_iso(confirmed_at),
                    }
                )
        except Exception:
            pass
        return out

    async def _block_recent_activity() -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    text(
                        """
                        SELECT
                            a.initials,
                            a.color,
                            a.activity_text,
                            a.activity_time,
                            a.created_at,
                            a.visit_id,
                            v.site_visit_number
                        FROM monitoring_visit_activity a
                        JOIN monitoring_visits v ON v.id = a.visit_id
                        ORDER BY a.id DESC
                        LIMIT 8
                        """
                    )
                )
                rows = res.mappings().all()
            for row in rows:
                created = row.get("created_at")
                try:
                    if created:
                        if getattr(created, "tzinfo", None) is None:
                            created = created.replace(tzinfo=timezone.utc)
                        age_hours = (now - created).total_seconds() / 3600
                    else:
                        age_hours = 999
                except Exception:
                    age_hours = 999
                if age_hours > 48:
                    continue
                vid = str(row.get("visit_id") or "")
                activity_text = _rewrite_visit_id_in_text(row.get("activity_text"), vid, row.get("site_visit_number"))
                time_label = relative_time_label(created, now=now)
                out.append({
                    "icon": "✅",
                    "text": activity_text,
                    "time": time_label,
                    "unread": age_hours < 6,
                    "type": "activity",
                    "sort_at": _sort_at_iso(created),
                })
        except Exception:
            pass
        return out

    results = await asyncio.gather(
        _block_overdue_findings(),
        _block_upcoming_visits(),
        _block_confirmed_visits(),
        _block_recent_activity(),
    )
    for sub in results:
        notifs.extend(sub)

    notifs.sort(key=lambda n: n.get("sort_at") or "", reverse=True)
    for idx, n in enumerate(notifs, start=1):
        n["id"] = idx

    return {"notifications": notifs, "unread_count": sum(1 for n in notifs if n.get("unread"))}


def _dashboard_visit_filters(
    site_id: Optional[str],
    study_id: Optional[str],
    status: Optional[str],
) -> tuple[str, Dict[str, Any]]:
    """Build WHERE clause for dashboard visit lists.

    Top-bar study/site selectors pass Postgres UUIDs while monitoring_visits
    often stores protocol codes (study_id / site_id columns). Match both via
    EXISTS so newly created visits appear after navigating back to dashboard.
    """
    clauses = ["1=1"]
    params: Dict[str, Any] = {}
    if site_id:
        clauses.append(dashboard_site_filter_sql())
        params["site_id"] = site_id.strip()
    if study_id:
        clauses.append(dashboard_study_filter_sql())
        params["study_id"] = study_id.strip()
    if status:
        st = status.strip().lower()
        if st == "closed":
            clauses.append(
                "(LOWER(COALESCE(v.status, '')) != 'archived' "
                "AND (v.closed_at IS NOT NULL OR LOWER(COALESCE(v.status, '')) = 'closed'))"
            )
        elif st == "archived":
            clauses.append("LOWER(COALESCE(v.status, '')) = 'archived'")
        else:
            clauses.append(
                "(v.closed_at IS NULL AND LOWER(COALESCE(v.status, '')) = LOWER(:status))"
            )
            params["status"] = status.strip()
    else:
        # Default dashboard view hides archived rows (matches frontend "All Statuses").
        clauses.append("LOWER(COALESCE(v.status, '')) != 'archived'")
    return " AND ".join(clauses), params


def _visit_row_to_dashboard_item(row: Any) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "site_id": row["site_id"],
        "site_name": row["site_name"],
        "study_id": row["study_id"],
        "study_name": row["study_name"],
        "date": row["visit_date"],
        "date_iso": row["visit_date_iso"],
        "end_date": row.get("visit_end_date") or "",
        "end_date_iso": row.get("visit_end_date_iso") or "",
        "priority": row.get("priority") or "Medium",
        "estimated_duration_days": float(row["estimated_duration_days"])
        if row.get("estimated_duration_days") is not None
        else None,
        "cra_name": row["cra_name"],
        "type": row["visit_type"],
        "status": effective_visit_status(row.get("status"), row.get("closed_at"))
        or _status_from_risk(row.get("risk_level", "")),
        "open_findings": int(row["open_findings"] or 0),
        "site_visit_number": int(row["site_visit_number"])
        if row.get("site_visit_number") is not None
        else None,
    }


@router.get("/dashboard")
async def get_dashboard_data(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    site_id: Optional[str] = Query(None),
    study_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_monitor_tables(db)
    where_sql, params = _dashboard_visit_filters(site_id, study_id, status)
    offset = (page - 1) * page_size
    params_with_page = {**params, "limit": page_size, "offset": offset}

    join_visits_sql = f"""
                SELECT
                    v.id,
                    v.site_id,
                    v.study_id,
                    COALESCE(NULLIF(v.cra_name, ''), 'Unassigned') AS cra_name,
                    CASE
                        WHEN LOWER(COALESCE(v.status, '')) = 'archived' THEN 'Archived'
                        WHEN v.closed_at IS NOT NULL THEN 'Closed'
                        ELSE COALESCE(NULLIF(v.status, ''), 'Scheduled')
                    END AS status,
                    v.closed_at,
                    v.visit_type,
                    v.risk_level,
                    v.visit_date,
                    v.visit_date_iso,
                    v.visit_end_date,
                    v.visit_end_date_iso,
                    v.priority,
                    v.estimated_duration_days,
                    v.site_visit_number,
                    COALESCE(s.name, v.site_id, 'Unknown Site')   AS site_name,
                    COALESCE(st.name, v.study_id, 'Unknown Study') AS study_name,
                    COALESCE(COUNT(f.id), 0)                       AS open_findings
                FROM monitoring_visits v
                LEFT JOIN sites s
                    ON (v.site_id IS NOT NULL
                        AND (v.site_id = s.site_id OR v.site_id = CAST(s.id AS TEXT)))
                LEFT JOIN studies st
                    ON (v.study_id IS NOT NULL
                        AND (v.study_id = st.study_id OR v.study_id = CAST(st.id AS TEXT)))
                LEFT JOIN monitoring_findings f
                    ON f.visit_id = v.id
                    AND LOWER(TRIM(COALESCE(f.status, ''))) NOT IN ('resolved', 'archived', 'closed')
                WHERE {where_sql}
                GROUP BY
                    v.id, v.site_id, v.study_id, v.cra_name, v.status, v.closed_at,
                    v.visit_type, v.risk_level, v.visit_date, v.visit_date_iso,
                    v.visit_end_date, v.visit_end_date_iso, v.priority, v.estimated_duration_days,
                    v.site_visit_number,
                    s.name, st.name
                ORDER BY
                    CASE WHEN LOWER(COALESCE(v.status, '')) = 'archived' THEN 1 ELSE 0 END ASC,
                    COALESCE(NULLIF(v.visit_date_iso, ''), '9999-12-31T00:00:00Z') ASC,
                    v.id ASC
                LIMIT :limit OFFSET :offset
                """

    fallback_visits_sql = f"""
                SELECT
                    v.id,
                    v.site_id,
                    v.study_id,
                    COALESCE(NULLIF(v.cra_name, ''), 'Unassigned') AS cra_name,
                    CASE
                        WHEN LOWER(COALESCE(v.status, '')) = 'archived' THEN 'Archived'
                        WHEN v.closed_at IS NOT NULL THEN 'Closed'
                        ELSE COALESCE(NULLIF(v.status, ''), 'Scheduled')
                    END AS status,
                    v.closed_at,
                    v.visit_type,
                    v.risk_level,
                    v.visit_date,
                    v.visit_date_iso,
                    v.visit_end_date,
                    v.visit_end_date_iso,
                    v.priority,
                    v.estimated_duration_days,
                    v.site_visit_number,
                    COALESCE(v.site_id,  'Unknown Site')  AS site_name,
                    COALESCE(v.study_id, 'Unknown Study') AS study_name,
                    0 AS open_findings
                FROM monitoring_visits v
                WHERE {where_sql}
                ORDER BY
                    CASE WHEN LOWER(COALESCE(v.status, '')) = 'archived' THEN 1 ELSE 0 END ASC,
                    COALESCE(NULLIF(v.visit_date_iso, ''), '9999-12-31T00:00:00Z') ASC,
                    v.id ASC
                LIMIT :limit OFFSET :offset
                """

    count_sql = f"SELECT COUNT(*) AS cnt FROM monitoring_visits v WHERE {where_sql}"

    try:
        total_row = await db.execute(text(count_sql), params)
        total = int(total_row.scalar() or 0)
        visits_rows = await db.execute(text(join_visits_sql), params_with_page)
    except Exception:
        total_row = await db.execute(text(count_sql), params)
        total = int(total_row.scalar() or 0)
        visits_rows = await db.execute(text(fallback_visits_sql), params_with_page)

    items = [_visit_row_to_dashboard_item(row) for row in visits_rows.mappings().all()]

    summary_row = await db.execute(
        text(
            f"""
            SELECT
                COUNT(*) AS total_visits,
                COUNT(*) FILTER (
                    WHERE v.closed_at IS NULL AND LOWER(COALESCE(v.status, '')) = 'scheduled'
                ) AS scheduled,
                COUNT(*) FILTER (
                    WHERE v.closed_at IS NULL AND LOWER(COALESCE(v.status, '')) = 'in progress'
                ) AS in_progress,
                COUNT(*) FILTER (
                    WHERE v.closed_at IS NOT NULL
                    OR LOWER(COALESCE(v.status, '')) IN ('completed', 'closed')
                ) AS completed,
                COUNT(*) FILTER (
                    WHERE v.closed_at IS NULL AND LOWER(COALESCE(v.status, '')) = 'cancelled'
                ) AS cancelled
            FROM monitoring_visits v
            WHERE {where_sql}
            """
        ),
        params,
    )
    summary = dict(summary_row.mappings().first() or {})

    # Apply the same site/study filters as the visits query so findings are
    # scoped to the currently selected study + site (not all findings globally).
    findings_where_clauses = ["LOWER(COALESCE(v.status, '')) <> 'archived'"]
    findings_params: Dict[str, Any] = {}
    if site_id:
        findings_where_clauses.append(dashboard_site_filter_sql())
        findings_params["site_id"] = site_id.strip()
    if study_id:
        findings_where_clauses.append(dashboard_study_filter_sql())
        findings_params["study_id"] = study_id.strip()
    findings_where_sql = " AND ".join(findings_where_clauses)

    findings_rows = await db.execute(
        text(
            f"""
            SELECT f.id, f.visit_id, f.category, f.description, f.severity, f.status, f.site,
                   f.assignee_initials, f.assignee_name, f.assignee_color, f.due_date, f.due_color, f.resolution,
                   f.subject_id
            FROM monitoring_findings f
            INNER JOIN monitoring_visits v ON v.id = f.visit_id
            WHERE {findings_where_sql}
            ORDER BY f.id DESC
            """
        ),
        findings_params,
    )

    today = datetime.now(timezone.utc).date()

    def _parse_due_date(due_date_str: str) -> Optional[Any]:
        """Parse stored due_date string ('Apr 26', '2026-04-30', etc.) into a date object."""
        if not due_date_str or due_date_str.strip().upper() == "TBD":
            return None
        s = due_date_str.strip()
        for fmt in ["%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"]:
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                pass
        # "Apr 26" — assume current year
        try:
            return datetime.strptime(f"{s}, {today.year}", "%b %d, %Y").date()
        except ValueError:
            pass
        return None

    findings = []
    overdue_count = 0
    for row in findings_rows.mappings().all():
        st = (row["status"] or "").lower()
        is_resolved = st == "resolved"
        is_archived_f = st == "archived"
        parsed = _parse_due_date(row["due_date"] or "")
        is_overdue = bool(not is_resolved and not is_archived_f and parsed and parsed < today)
        if is_overdue:
            overdue_count += 1
        findings.append(
            {
                "id": row["id"],
                "visit_id": row["visit_id"],
                "category": row["category"],
                "description": row["description"],
                "severity": row["severity"],
                "status": row["status"],
                "site": row["site"],
                "assignee": {
                    "initials": row["assignee_initials"],
                    "name": row["assignee_name"],
                    "color": row["assignee_color"],
                },
                "dueDate": row["due_date"],
                "dueColor": row["due_color"],
                "resolution": row["resolution"],
                "subjectId": (row.get("subject_id") or "").strip(),
                "reference": (row.get("reference") or "").strip(),
                "isOverdue": is_overdue,
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "visits": items,
        "findings": findings,
        "overdue_count": overdue_count,
        "summary": summary,
    }


async def _single_dashboard_visit_payload(db: AsyncSession, visit_id: str) -> Dict[str, Any]:
    """Same visit row shape as GET /monitor/dashboard (names resolved via joins)."""
    try:
        row_result = await db.execute(
            text(
                """
                SELECT
                    v.id,
                    v.site_id,
                    v.study_id,
                    COALESCE(NULLIF(v.cra_name, ''), 'Unassigned') AS cra_name,
                    CASE
                        WHEN LOWER(COALESCE(v.status, '')) = 'archived' THEN 'Archived'
                        WHEN v.closed_at IS NOT NULL THEN 'Closed'
                        ELSE COALESCE(NULLIF(v.status, ''), 'Scheduled')
                    END AS status,
                    v.closed_at,
                    v.visit_type,
                    v.risk_level,
                    v.visit_date,
                    v.visit_date_iso,
                    v.visit_end_date,
                    v.visit_end_date_iso,
                    v.priority,
                    v.estimated_duration_days,
                    v.site_visit_number,
                    COALESCE(s.name, v.site_id, 'Unknown Site')   AS site_name,
                    COALESCE(st.name, v.study_id, 'Unknown Study') AS study_name,
                    COALESCE(COUNT(f.id), 0)                       AS open_findings
                FROM monitoring_visits v
                LEFT JOIN sites s
                    ON (v.site_id IS NOT NULL
                        AND (v.site_id = s.site_id OR v.site_id = CAST(s.id AS TEXT)))
                LEFT JOIN studies st
                    ON (v.study_id IS NOT NULL
                        AND (v.study_id = st.study_id OR v.study_id = CAST(st.id AS TEXT)))
                LEFT JOIN monitoring_findings f
                    ON f.visit_id = v.id
                    AND LOWER(TRIM(COALESCE(f.status, ''))) NOT IN ('resolved', 'archived', 'closed')
                WHERE v.id = :visit_id
                GROUP BY
                    v.id, v.site_id, v.study_id, v.cra_name, v.status, v.closed_at,
                    v.visit_type, v.risk_level, v.visit_date, v.visit_date_iso,
                    v.visit_end_date, v.visit_end_date_iso, v.priority, v.estimated_duration_days,
                    v.site_visit_number,
                    s.name, st.name
                LIMIT 1
                """
            ),
            {"visit_id": visit_id},
        )
        row = row_result.mappings().first()
    except Exception:
        row = None
    if not row:
        row_result = await db.execute(
            text(
                """
                SELECT
                    v.id,
                    v.site_id,
                    v.study_id,
                    COALESCE(NULLIF(v.cra_name, ''), 'Unassigned') AS cra_name,
                    CASE
                        WHEN LOWER(COALESCE(v.status, '')) = 'archived' THEN 'Archived'
                        WHEN v.closed_at IS NOT NULL THEN 'Closed'
                        ELSE COALESCE(NULLIF(v.status, ''), 'Scheduled')
                    END AS status,
                    v.closed_at,
                    v.visit_type,
                    v.risk_level,
                    v.visit_date,
                    v.visit_date_iso,
                    v.visit_end_date,
                    v.visit_end_date_iso,
                    v.priority,
                    v.estimated_duration_days,
                    v.site_visit_number,
                    COALESCE(v.site_id, 'Unknown Site')   AS site_name,
                    COALESCE(v.study_id, 'Unknown Study') AS study_name,
                    0 AS open_findings
                FROM monitoring_visits v
                WHERE v.id = :visit_id
                LIMIT 1
                """
            ),
            {"visit_id": visit_id},
        )
        row = row_result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Visit not found")

    return {
        "id": row["id"],
        "site_id": row["site_id"],
        "site_name": row["site_name"],
        "study_id": row["study_id"],
        "study_name": row["study_name"],
        "date": row["visit_date"],
        "date_iso": row["visit_date_iso"],
        "end_date": row.get("visit_end_date") or "",
        "end_date_iso": row.get("visit_end_date_iso") or "",
        "priority": row.get("priority") or "Medium",
        "estimated_duration_days": float(row["estimated_duration_days"])
        if row.get("estimated_duration_days") is not None
        else None,
        "cra_name": row["cra_name"],
        "type": row["visit_type"],
        "status": effective_visit_status(row.get("status"), row.get("closed_at"))
        or _status_from_risk(row.get("risk_level", "")),
        "open_findings": int(row["open_findings"] or 0),
        "site_visit_number": int(row["site_visit_number"])
        if row.get("site_visit_number") is not None
        else None,
    }


