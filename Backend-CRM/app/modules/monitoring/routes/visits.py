"""REST API: visits cluster (Phase 2.2 extract).

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
from app.db import get_db
from app.integrations.smtp_service import smtp_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["monitor"])

from app.modules.monitoring.utils import (
    effective_visit_status,
    relative_time_label,
    resolve_monitor_site_id,
    resolve_monitor_study_id,
    site_profile_join_sql,
)

# Pull legacy helpers + body schemas from the parent router.
from app.modules.monitoring.aggregator import (  # noqa: E402
    _ensure_monitor_tables,
    _require_monitoring_visit,
    _append_visit_activity,
    _sync_pre_visit_checklist,
    _sync_visit_objectives,
    _sync_pre_visit_checklist,
    _build_visit_date_fields_from_date_and_time,
    _build_optional_visit_date_fields,
    _effective_visit_schedule_from_row,
    _parse_optional_decimal,
    _normalize_visit_type,
    _normalize_visit_site_bucket,
    _monitor_pg_advisory_lock_site_bucket,
    _next_site_visit_sequence,
    _visit_label_from_site_number,
    _format_utc_label_from_iso,
    _rewrite_visit_id_in_text,
    _status_from_risk,
    PROTOCOL_VISIT_OBJECTIVES,
)
# _single_dashboard_visit_payload was pulled into routes/dashboard.py during
# the Phase 2.2 split because it lived inline between dashboard endpoints.
from app.modules.monitoring.routes.dashboard import _single_dashboard_visit_payload  # noqa: E402


@router.delete("/visits/{visit_id}")
async def delete_visit(visit_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    result = await db.execute(
        text("DELETE FROM monitoring_visits WHERE id = :visit_id"),
        {"visit_id": visit_id},
    )
    if (result.rowcount or 0) == 0:
        raise HTTPException(status_code=404, detail="Visit not found")
    await db.commit()
    return {"status": "deleted"}


@router.patch("/visits/{visit_id}")
async def update_visit(visit_id: str, payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    existing_row = await db.execute(
        text("SELECT id FROM monitoring_visits WHERE id = :visit_id"),
        {"visit_id": visit_id},
    )
    if not existing_row.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Visit not found")
    current_row = await db.execute(
        text(
            """
                 SELECT visit_type, status, closed_at, cra_name, visit_date, visit_date_iso, site_id, study_id,
                    protocol, site_address, site_visit_number, duration, priority,
                    visit_end_date, visit_end_date_iso, estimated_duration_days
            FROM monitoring_visits
            WHERE id = :visit_id
            LIMIT 1
            """
        ),
        {"visit_id": visit_id},
    )
    current = current_row.mappings().first() or {}

    is_locked_closed = current.get("closed_at") is not None
    current_status = str(current.get("status") or "").strip().lower()
    requested_status = (
        str(payload.get("status") or "").strip().lower()
        if payload.get("status") is not None
        else None
    )
    if requested_status is not None:
        if requested_status == "archived":
            pass  # archiving is allowed even after formal close
        elif current_status == "archived":
            pass  # unarchive back to active pipeline
        elif (is_locked_closed or current_status == "closed") and requested_status != "closed":
            raise HTTPException(
                status_code=400,
                detail="This visit is closed and locked. Reopen is not supported.",
            )

    site_name_input = payload.get("site")
    study_name_input = payload.get("study")
    cra_name_input = payload.get("cra")
    visit_type_input = payload.get("type")
    site_name = str(site_name_input).strip() if site_name_input is not None else ""
    study_name = str(study_name_input).strip() if study_name_input is not None else ""
    cra_name = (
        str(cra_name_input).strip()
        if cra_name_input is not None
        else str(current.get("cra_name") or "").strip()
    ) or "Unassigned"
    visit_type = (
        str(visit_type_input).strip()
        if visit_type_input is not None
        else str(current.get("visit_type") or "").strip()
    ) or "On-Site Monitoring"
    priority_input = payload.get("priority")
    if priority_input is None:
        priority = str(current.get("priority") or "Medium").strip() or "Medium"
    else:
        priority = str(priority_input).strip() or "Medium"
    visit_date_iso_input = str(payload.get("date") or "").strip()
    visit_time_input = str(payload.get("time") or "").strip()
    duration_input = payload.get("duration")
    if duration_input is None:
        duration = str(current.get("duration") or "Full Day (8 hours)")
    else:
        duration = str(duration_input).strip() or "Full Day (8 hours)"
    status = (
        str(payload.get("status")).strip()
        if payload.get("status") is not None
        else str(current.get("status") or "").strip()
    ) or "Scheduled"
    if is_locked_closed and requested_status != "archived" and current_status != "archived":
        status = "Closed"
    estimated_duration_days = current.get("estimated_duration_days")
    if "estimated_duration_days" in payload:
        estimated_duration_days = _parse_optional_decimal(payload.get("estimated_duration_days"))

    if "end_date" in payload or "end_time" in payload:
        end_date_input = (payload.get("end_date") or "").strip()
        end_time_input = (payload.get("end_time") or "").strip()
        visit_end_date, visit_end_date_iso = _build_optional_visit_date_fields(
            end_date_input, end_time_input or None
        )
    else:
        visit_end_date = str(current.get("visit_end_date") or "")
        visit_end_date_iso = str(current.get("visit_end_date_iso") or "")

    site_id = str(current.get("site_id") or "").strip()
    study_id = str(current.get("study_id") or "").strip()
    if site_name or payload.get("site_pg_id") or payload.get("siteId"):
        resolved_site = await resolve_monitor_site_id(
            db,
            site_name=site_name,
            site_pg_id=str(payload.get("site_pg_id") or payload.get("siteId") or ""),
        )
        if resolved_site:
            site_id = resolved_site
    if study_name or payload.get("study_pg_id") or payload.get("studyId"):
        resolved_study = await resolve_monitor_study_id(
            db,
            study_name=study_name,
            study_pg_id=str(payload.get("study_pg_id") or payload.get("studyId") or ""),
        )
        if resolved_study:
            study_id = resolved_study

    if "date" in payload or "time" in payload:
        visit_date, visit_date_iso = _build_visit_date_fields_from_date_and_time(
            visit_date_iso_input, visit_time_input or None
        )
    else:
        visit_date = str(current.get("visit_date") or "")
        visit_date_iso = str(current.get("visit_date_iso") or "")

    old_bucket = _normalize_visit_site_bucket(
        str(current["site_id"]) if current.get("site_id") is not None else None,
    )
    new_bucket = _normalize_visit_site_bucket(str(site_id) if site_id is not None else None)
    next_site_visit_number: Optional[int] = None
    cur_svn = current.get("site_visit_number")

    if old_bucket != new_bucket:
        await _monitor_pg_advisory_lock_site_bucket(db, new_bucket)
        next_site_visit_number = await _next_site_visit_sequence(db, new_bucket)
    else:
        try:
            cur_svn_int = int(cur_svn) if cur_svn is not None else None
        except (TypeError, ValueError):
            cur_svn_int = None
        if cur_svn_int is None or cur_svn_int < 1:
            await _monitor_pg_advisory_lock_site_bucket(db, new_bucket)
            next_site_visit_number = await _next_site_visit_sequence(db, new_bucket)

    await db.execute(
        text(
            """
            UPDATE monitoring_visits SET
                site_id = :site_id,
                study_id = :study_id,
                cra_name = :cra_name,
                status = :status,
                priority = :priority,
                visit_type = :visit_type,
                visit_date = :visit_date,
                visit_date_iso = :visit_date_iso,
                visit_end_date = :visit_end_date,
                visit_end_date_iso = :visit_end_date_iso,
                estimated_duration_days = :estimated_duration_days,
                duration = :duration,
                protocol = :protocol,
                site_address = :site_address,
                site_visit_number = COALESCE(:svn_new, site_visit_number),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :visit_id
            RETURNING site_visit_number
            """
        ),
        {
            "visit_id": visit_id,
            "site_id": site_id or None,
            "study_id": study_id or None,
            "cra_name": cra_name,
            "status": status,
            "priority": priority,
            "visit_type": visit_type,
            "visit_date": visit_date,
            "visit_date_iso": visit_date_iso,
            "visit_end_date": visit_end_date,
            "visit_end_date_iso": visit_end_date_iso,
            "estimated_duration_days": estimated_duration_days,
            "duration": duration,
            "protocol": study_name or str(current.get("protocol") or "N/A"),
            "site_address": site_name or str(current.get("site_address") or "N/A"),
            "svn_new": next_site_visit_number,
        },
    )
    previous_type = str(current.get("visit_type") or "").strip()
    if previous_type != visit_type:
        await _sync_pre_visit_checklist(db, visit_id, visit_type, replace_template=True)
    else:
        await _sync_pre_visit_checklist(db, visit_id, visit_type)
    changes: List[str] = []
    previous_status = str(current.get("status") or "").strip()
    previous_cra = str(current.get("cra_name") or "").strip()
    previous_date_iso = str(current.get("visit_date_iso") or "").strip()
    next_date_iso = (visit_date_iso or "").strip()
    previous_priority = str(current.get("priority") or "").strip()
    previous_end_iso = str(current.get("visit_end_date_iso") or "").strip()
    next_end_iso = (visit_end_date_iso or "").strip()
    previous_estimated_days = current.get("estimated_duration_days")

    if previous_type != visit_type:
        if previous_type:
            changes.append(f"visit type from {previous_type} to {visit_type}")
        else:
            changes.append(f"visit type to {visit_type}")
    if previous_status != status:
        if previous_status:
            changes.append(f"status from {previous_status} to {status}")
        else:
            changes.append(f"status to {status}")
    if previous_cra != cra_name:
        if previous_cra:
            changes.append(f"CRA from {previous_cra} to {cra_name}")
        else:
            changes.append(f"CRA to {cra_name}")
    if previous_date_iso != next_date_iso:
        if previous_date_iso and next_date_iso:
            changes.append(
                f"visit date from {_format_utc_label_from_iso(previous_date_iso)} to {_format_utc_label_from_iso(next_date_iso)}"
            )
        elif next_date_iso:
            changes.append(f"visit date to {_format_utc_label_from_iso(next_date_iso)}")
        else:
            changes.append("visit date updated")

    if previous_priority != priority:
        if previous_priority:
            changes.append(f"priority from {previous_priority} to {priority}")
        else:
            changes.append(f"priority to {priority}")

    if previous_end_iso != next_end_iso:
        if previous_end_iso and next_end_iso:
            changes.append(
                f"visit end date from {_format_utc_label_from_iso(previous_end_iso)} to {_format_utc_label_from_iso(next_end_iso)}"
            )
        elif next_end_iso:
            changes.append(f"visit end date to {_format_utc_label_from_iso(next_end_iso)}")
        else:
            changes.append("visit end date cleared")

    if "estimated_duration_days" in payload and previous_estimated_days != estimated_duration_days:
        if estimated_duration_days is None:
            changes.append("estimated duration days cleared")
        elif previous_estimated_days is None:
            changes.append(f"estimated duration days to {estimated_duration_days}")
        else:
            changes.append(f"estimated duration days from {previous_estimated_days} to {estimated_duration_days}")

    activity_text = (
        f"Updated visit details: changed {', '.join(changes)}."
        if changes
        else "Updated visit details."
    )
    await _append_visit_activity(db, visit_id, activity_text)
    await db.commit()

    return await _single_dashboard_visit_payload(db, visit_id)


@router.post("/visits")
async def create_visit(payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)

    site_name = (payload.get("site") or "").strip()
    study_name = (payload.get("study") or "").strip()
    cra_name = (payload.get("cra") or "Unassigned").strip() or "Unassigned"
    visit_type = (payload.get("type") or "On-Site Monitoring").strip() or "On-Site Monitoring"
    visit_date_iso_input = (payload.get("date") or "").strip()
    visit_time_input = (payload.get("time") or "").strip()
    priority = (payload.get("priority") or "Medium").strip() or "Medium"
    end_date_input = (payload.get("end_date") or "").strip()
    end_time_input = (payload.get("end_time") or "").strip()
    estimated_duration_days = _parse_optional_decimal(payload.get("estimated_duration_days"))
    status = "Scheduled"

    # Resolve selected site/study to canonical ids (prefer top-bar Postgres ids).
    site_id = site_name
    study_id = study_name
    resolved_site = await resolve_monitor_site_id(
        db,
        site_name=site_name,
        site_pg_id=str(payload.get("site_pg_id") or payload.get("siteId") or ""),
    )
    if resolved_site:
        site_id = resolved_site
    resolved_study = await resolve_monitor_study_id(
        db,
        study_name=study_name,
        study_pg_id=str(payload.get("study_pg_id") or payload.get("studyId") or ""),
    )
    if resolved_study:
        study_id = resolved_study

    now = datetime.now(timezone.utc)
    visit_id = f"MON-{now.strftime('%Y%m%d%H%M%S')}-{now.microsecond:06d}"

    visit_date, visit_date_iso = _build_visit_date_fields_from_date_and_time(
        visit_date_iso_input, visit_time_input or None
    )
    visit_end_date, visit_end_date_iso = _build_optional_visit_date_fields(
        end_date_input, end_time_input or None
    )

    bucket = _normalize_visit_site_bucket(str(site_id) if site_id is not None else None)
    await _monitor_pg_advisory_lock_site_bucket(db, bucket)
    site_visit_number = await _next_site_visit_sequence(db, bucket)

    await db.execute(
        text(
            """
            INSERT INTO monitoring_visits (
                id, site_id, study_id, cra_name, cra_email, status, visit_type, visit_date, visit_date_iso, duration, protocol, ind_number, sponsor, risk_level,
                priority, visit_end_date, visit_end_date_iso, estimated_duration_days,
                principal_investigator, pi_email, study_coordinator, coordinator_phone, site_address,
                irb_approval, sdv_verified_subjects, sdv_total_subjects, subjects_enrolled,
                crf_completion, query_rate, last_sdv_date, action_required_count, site_visit_number
            ) VALUES (
                :id, :site_id, :study_id, :cra_name, :cra_email, :status, :visit_type, :visit_date, :visit_date_iso, :duration, :protocol, :ind_number, :sponsor, :risk_level,
                :priority, :visit_end_date, :visit_end_date_iso, :estimated_duration_days,
                :principal_investigator, :pi_email, :study_coordinator, :coordinator_phone, :site_address,
                :irb_approval, :sdv_verified_subjects, :sdv_total_subjects, :subjects_enrolled,
                :crf_completion, :query_rate, :last_sdv_date, :action_required_count, :site_visit_number
            )
            """
        ),
        {
            "id": visit_id,
            "site_id": site_id or None,
            "study_id": study_id or None,
            "cra_name": cra_name,
            "cra_email": str(payload.get("cra_email") or "").strip(),
            "status": status,
            "visit_type": visit_type,
            "visit_date": visit_date,
            "visit_date_iso": visit_date_iso,
            "priority": priority,
            "visit_end_date": visit_end_date,
            "visit_end_date_iso": visit_end_date_iso,
            "estimated_duration_days": estimated_duration_days,
            "duration": payload.get("duration", "Full Day (8 hours)") or "Full Day (8 hours)",
            "protocol": study_name or "N/A",
            "ind_number": "N/A",
            "sponsor": "N/A",
            "risk_level": "Medium",
            "principal_investigator": "N/A",
            "pi_email": "",
            "study_coordinator": "N/A",
            "coordinator_phone": "",
            "site_address": site_name or "N/A",
            "irb_approval": "N/A",
            "sdv_verified_subjects": 0,
            "sdv_total_subjects": 0,
            "subjects_enrolled": "0 / 0",
            "crf_completion": "0%",
            "query_rate": "0%",
            "last_sdv_date": "",
            "action_required_count": 0,
            "site_visit_number": site_visit_number,
        },
    )
    await _sync_visit_objectives(db, visit_id)
    await _sync_pre_visit_checklist(db, visit_id, visit_type)
    await db.commit()

    # Kafka: publish the visit-creation milestone (SITE_QUALIFICATION_VISIT_SCHEDULED
    # / SIV_SCHEDULED / MONITORING_VISIT_PLANNED depending on visit_type) to the
    # Data Platform. Best-effort & self-guarded — never breaks the committed visit.
    if site_id:
        try:
            from app.integrations.milestones_kafka import publish_visit_milestone

            await publish_visit_milestone(
                site_id=str(site_id), visit_type=visit_type, phase="scheduled"
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "create_visit: milestone Kafka hook failed for visit %s", visit_id
            )

    # Post a Public Notice Board entry for the scheduled visit. Best-effort —
    # we already committed the visit, and a notice failure here must not
    # surface as a 500 to the caller.
    if site_id:
        try:
            from app.utils.system_notices import post_site_event_notice

            when = visit_date_iso or visit_date or "TBD"
            msg = (
                f"{visit_type} visit scheduled for {when} — "
                f"CRA {cra_name}, priority {priority}"
            )
            await post_site_event_notice(
                db,
                site_ref=site_id,
                study_ref=study_id,
                event_type="monitoring_visit_created",
                message=msg,
                metadata={
                    "visit_id": visit_id,
                    "visit_type": visit_type,
                    "visit_date_iso": visit_date_iso,
                    "priority": priority,
                    "cra_name": cra_name,
                    "site_visit_number": site_visit_number,
                },
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "create_visit: notice-board hook failed for visit %s", visit_id
            )

    return {
        "id": visit_id,
        "site_id": site_id,
        "site_name": site_name or "Unknown Site",
        "study_id": study_id,
        "study_name": study_name or "Unknown Study",
        "date": visit_date,
        "date_iso": visit_date_iso,
        "end_date": visit_end_date,
        "end_date_iso": visit_end_date_iso,
        "priority": priority,
        "estimated_duration_days": float(estimated_duration_days) if estimated_duration_days is not None else None,
        "cra_name": cra_name,
        "type": visit_type,
        "status": status,
        "open_findings": 0,
        "site_visit_number": site_visit_number,
    }


@router.get("/visits/{visit_id}/overview")
async def get_visit_overview(visit_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    now = datetime.now(timezone.utc)

    visit_row = await db.execute(
        text("SELECT * FROM monitoring_visits WHERE id = :visit_id"),
        {"visit_id": visit_id},
    )
    visit = visit_row.mappings().first()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")

    objectives_count_row = await db.execute(
        text("SELECT COUNT(*) AS c FROM monitoring_visit_objectives WHERE visit_id = :visit_id"),
        {"visit_id": visit_id},
    )
    existing_objectives = int((objectives_count_row.mappings().first() or {}).get("c") or 0)
    if existing_objectives != len(PROTOCOL_VISIT_OBJECTIVES):
        # One-time normalization for visits with legacy objective templates.
        await _sync_visit_objectives(db, visit_id)
        await db.commit()

    objectives_rows = await db.execute(
        text(
            """
            SELECT id, objective_text, done, tag_type
            FROM monitoring_visit_objectives
            WHERE visit_id = :visit_id
            ORDER BY display_order ASC, id ASC
            """
        ),
        {"visit_id": visit_id},
    )
    objectives = [
        {
            "id": row.id,
            "text": row.objective_text,
            "done": row.done,
            "tagType": row.tag_type,
        }
        for row in objectives_rows.fetchall()
    ]

    activity_rows = await db.execute(
        text(
            """
            SELECT initials, color, activity_text, activity_time, created_at
            FROM monitoring_visit_activity
            WHERE visit_id = :visit_id
            ORDER BY id DESC
            """
        ),
        {"visit_id": visit_id},
    )
    svn_for_label = visit.get("site_visit_number")
    recent_activity = [
        {
            "initials": row.initials,
            "color": row.color,
            "text": _rewrite_visit_id_in_text(row.activity_text, visit_id, svn_for_label),
            "time": relative_time_label(getattr(row, "created_at", None), now=now),
        }
        for row in activity_rows.fetchall()
    ]

    percent = 0
    if visit["sdv_total_subjects"] > 0:
        percent = round((visit["sdv_verified_subjects"] / visit["sdv_total_subjects"]) * 100)

    # Pull site contact data from Site Profile tab source when available.
    site_profile_row = None
    if visit.get("site_id"):
        profile_res = await db.execute(
            text(
                f"""
                SELECT
                    s.name AS site_name,
                    sp.pi_name,
                    sp.pi_designation,
                    sp.pi_department,
                    sp.pi_email,
                    sp.site_coordinator_name,
                    sp.site_coordinator_email,
                    sp.site_coordinator_phone,
                    sp.address_line_1,
                    sp.city,
                    sp.state,
                    sp.country,
                    sp.postal_code
                FROM sites s
                {site_profile_join_sql()}
                WHERE (s.site_id = :site_id OR CAST(s.id AS TEXT) = :site_id)
                LIMIT 1
                """
            ),
            {"site_id": visit["site_id"]},
        )
        site_profile_row = profile_res.mappings().first()

    def _pick(*values: Any, default: str = "N/A") -> str:
        for value in values:
            if value is None:
                continue
            text_value = str(value).strip()
            if text_value:
                return text_value
        return default

    address_parts = []
    line1 = ""
    city_line = ""
    country_only = ""
    if site_profile_row:
        for key in ("address_line_1", "city", "state", "postal_code", "country"):
            val = site_profile_row.get(key)
            if val and str(val).strip():
                address_parts.append(str(val).strip())
        line1 = str(site_profile_row.get("address_line_1") or "").strip()
        city = str(site_profile_row.get("city") or "").strip()
        state = str(site_profile_row.get("state") or "").strip()
        postal = str(site_profile_row.get("postal_code") or "").strip()
        city_line = ", ".join([p for p in [city, state, postal] if p])
        country_only = str(site_profile_row.get("country") or "").strip()
    profile_address = ", ".join(address_parts)

    svn_val = visit.get("site_visit_number")
    try:
        site_visit_number = int(svn_val) if svn_val is not None else None
    except (TypeError, ValueError):
        site_visit_number = None

    schedule = _effective_visit_schedule_from_row(dict(visit))

    return {
        "visitDetails": {
            "status": effective_visit_status(visit.get("status"), visit.get("closed_at")),
            "visitType": visit["visit_type"],
            "visitDate": schedule["visitDate"],
            "visitDateIso": schedule["visitDateIso"],
            "endDate": schedule["endDate"],
            "endDateIso": schedule["endDateIso"],
            "duration": visit["duration"],
            "estimatedDurationDays": (
                float(visit["estimated_duration_days"])
                if visit.get("estimated_duration_days") is not None
                else None
            ),
            "protocol": visit["protocol"],
            "indNumber": visit["ind_number"],
            "sponsor": visit["sponsor"],
            "riskLevel": visit["risk_level"],
            "priority": visit.get("priority") or "Medium",
            "craName": str(visit.get("cra_name") or "").strip() or "Clinical Research Associate",
            "siteId": _pick(visit.get("site_id"), default="TBD"),
            "siteVisitNumber": site_visit_number,
            "craEmail": str(visit.get("cra_email") or "").strip(),
        },
        "siteContact": {
            "institutionName": _pick(
                site_profile_row.get("site_name") if site_profile_row else None,
                visit.get("site_id"),
            ),
            "principalInvestigator": _pick(
                site_profile_row.get("pi_name") if site_profile_row else None,
                visit.get("principal_investigator"),
            ),
            "piDesignation": _pick(
                site_profile_row.get("pi_designation") if site_profile_row else None,
                default="",
            ),
            "piDepartment": _pick(
                site_profile_row.get("pi_department") if site_profile_row else None,
                default="TBD",
            ),
            "addressLine1": _pick(line1 or None, default="TBD"),
            "addressCityRegionPostal": _pick(city_line or None, default="TBD"),
            "addressCountry": _pick(country_only or None, default="TBD"),
            "piEmail": _pick(
                site_profile_row.get("pi_email") if site_profile_row else None,
                visit.get("pi_email"),
                default="",
            ),
            "studyCoordinator": _pick(
                site_profile_row.get("site_coordinator_name") if site_profile_row else None,
                visit.get("study_coordinator"),
            ),
            "coordinatorEmail": _pick(
                site_profile_row.get("site_coordinator_email") if site_profile_row else None,
                default="",
            ),
            "coordinatorPhone": _pick(
                site_profile_row.get("site_coordinator_phone") if site_profile_row else None,
                visit.get("coordinator_phone"),
                default="",
            ),
            "siteAddress": _pick(profile_address, visit.get("site_address")),
            "irbApproval": visit["irb_approval"],
        },
        "sdvProgress": {
            "verifiedSubjects": visit["sdv_verified_subjects"],
            "totalSubjects": visit["sdv_total_subjects"],
            "percent": percent,
            "subjectsEnrolled": visit["subjects_enrolled"],
            "crfCompletion": visit["crf_completion"],
            "queryRate": visit["query_rate"],
            "lastSdvDate": visit["last_sdv_date"],
        },
        "lastModified": visit["updated_at"].isoformat() if visit.get("updated_at") else None,
        "closedAt": visit["closed_at"].isoformat() if visit.get("closed_at") else None,
        "actionRequiredCount": visit["action_required_count"],
        "objectives": objectives,
        "recentActivity": recent_activity,
    }


@router.patch("/visits/{visit_id}/objectives/{objective_id}")
async def toggle_objective(
    visit_id: str,
    objective_id: int,
    payload: Optional[Dict[str, Any]] = None,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_monitor_tables(db)
    requested_done = None
    if payload is not None and "done" in payload:
        requested_done = bool(payload.get("done"))

    if requested_done is None:
        result = await db.execute(
            text(
                """
                UPDATE monitoring_visit_objectives
                SET done = NOT done, updated_at = CURRENT_TIMESTAMP
                WHERE id = :objective_id
                  AND visit_id = :visit_id
                RETURNING id, objective_text, done, tag_type;
                """
            ),
            {"objective_id": objective_id, "visit_id": visit_id},
        )
    else:
        result = await db.execute(
            text(
                """
                UPDATE monitoring_visit_objectives
                SET done = :done, updated_at = CURRENT_TIMESTAMP
                WHERE id = :objective_id
                  AND visit_id = :visit_id
                RETURNING id, objective_text, done, tag_type;
                """
            ),
            {"objective_id": objective_id, "visit_id": visit_id, "done": requested_done},
        )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Objective not found for visit")
    await _append_visit_activity(
        db,
        visit_id,
        f"Objective updated: {row['objective_text']}",
    )
    await db.commit()

    return {
        "id": row["id"],
        "text": row["objective_text"],
        "done": row["done"],
        "tagType": row["tag_type"],
    }


