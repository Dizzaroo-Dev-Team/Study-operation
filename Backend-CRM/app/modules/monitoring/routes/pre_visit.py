"""REST API: pre_visit cluster (Phase 2.2 extract).

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
from app.integrations.smtp_service import enqueue_email, smtp_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["monitor"])

# Pull legacy helpers + body schemas from the parent router.
from app.modules.monitoring.utils import markdown_summary_to_html
from app.modules.monitoring.aggregator import (  # noqa: E402
    _append_visit_activity,
    _build_previsit_report_ack_token,
    _decode_previsit_report_ack_token,
    _ensure_monitor_tables,
    _effective_visit_schedule_from_row,
    _require_monitoring_visit,
    _sync_pre_visit_checklist,
    _visit_label_from_site_number,
    PreVisitAcknowledgeBody,
    PreVisitSummarySendBody,
)


def _is_open_finding_status(status: Any) -> bool:
    normalized = str(status or "").strip().lower()
    return normalized not in {"resolved", "archived", "closed"}


def _datetime_to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text_value = str(value).strip()
    return text_value or None


def _finding_sort_number(finding_id: str) -> int:
    match = re.search(r"__F-(\d+)$", str(finding_id))
    if match:
        return int(match.group(1))
    match = re.match(r"^F-(\d+)$", str(finding_id))
    if match:
        return int(match.group(1))
    return 0


def _serialize_action_item_row(row: Any) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "assignee": {
            "initials": str(row.get("assignee_initials") or "SC"),
            "name": str(row.get("assignee_name") or "Unassigned"),
            "color": str(row.get("assignee_color") or "blue"),
        },
        "dueDate": str(row.get("due_date") or "TBD"),
        "closedDate": str(row.get("closed_date") or ""),
        "resolution": str(row.get("resolution") or ""),
    }


def _legacy_action_items_from_finding_row(row: Any) -> List[Dict[str, Any]]:
    return [
        {
            "id": f"{row['id']}__AI-01",
            "assignee": {
                "initials": str(row.get("assignee_initials") or "SC"),
                "name": str(row.get("assignee_name") or "Unassigned"),
                "color": str(row.get("assignee_color") or "blue"),
            },
            "dueDate": str(row.get("due_date") or "TBD"),
            "closedDate": str(row.get("closed_date") or ""),
            "resolution": str(row.get("resolution") or ""),
        }
    ]


async def _load_action_items_map(db: AsyncSession, finding_ids: Iterable[str]) -> Dict[str, List[Dict[str, Any]]]:
    ids = [str(i) for i in finding_ids if str(i or "").strip()]
    if not ids:
        return {}
    rows = await db.execute(
        text(
            """
            SELECT id, finding_id, assignee_initials, assignee_name, assignee_color, due_date, closed_date, resolution
            FROM monitoring_finding_action_items
            WHERE finding_id = ANY(:finding_ids)
            ORDER BY finding_id ASC, display_order ASC, id ASC
            """
        ),
        {"finding_ids": ids},
    )
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows.mappings().all():
        out.setdefault(str(row["finding_id"]), []).append(_serialize_action_item_row(row))
    return out


def _serialize_finding(row: Any, action_items: List[Dict[str, Any]], visit_id: str) -> Dict[str, Any]:
    primary = action_items[0] if action_items else _legacy_action_items_from_finding_row(row)[0]
    return {
        "id": str(row["id"]),
        "visitId": visit_id,
        "category": str(row.get("category") or "Monitoring"),
        "description": str(row.get("description") or ""),
        "severity": str(row.get("severity") or "Major"),
        "status": str(row.get("status") or "Open"),
        "site": str(row.get("site") or ""),
        "assignee": primary["assignee"],
        "dueDate": primary["dueDate"],
        "dueColor": str(row.get("due_color") or ""),
        "resolution": primary.get("resolution") or "",
        "subjectId": str(row.get("subject_id") or "").strip(),
        "reference": str(row.get("reference") or "").strip(),
        "actionItems": action_items,
    }


async def _previous_visit_follow_up_payload(db: AsyncSession, visit_id: str) -> Optional[Dict[str, Any]]:
    current_res = await db.execute(
        text(
            """
            SELECT id, site_id, study_id, site_visit_number
            FROM monitoring_visits
            WHERE id = :visit_id
            LIMIT 1
            """
        ),
        {"visit_id": visit_id},
    )
    current = current_res.mappings().first()
    if not current:
        return None

    current_svn_raw = current.get("site_visit_number")
    try:
        current_svn = int(current_svn_raw) if current_svn_raw is not None else None
    except (TypeError, ValueError):
        current_svn = None

    params: Dict[str, Any] = {
        "visit_id": visit_id,
        "site_id": str(current.get("site_id") or ""),
    }
    study_clause = ""
    study_id = str(current.get("study_id") or "").strip()
    if study_id:
        study_clause = "AND COALESCE(study_id, '') = :study_id"
        params["study_id"] = study_id

    if current_svn is not None and current_svn > 1:
        sequence_clause = "AND site_visit_number IS NOT NULL AND site_visit_number < :site_visit_number"
        order_clause = "site_visit_number DESC, NULLIF(visit_date_iso, '') DESC NULLS LAST, id DESC"
        params["site_visit_number"] = current_svn
    else:
        sequence_clause = ""
        order_clause = "NULLIF(visit_date_iso, '') DESC NULLS LAST, id DESC"

    previous_res = await db.execute(
        text(
            f"""
            SELECT id, site_id, study_id, visit_type, visit_date, visit_date_iso,
                   visit_end_date, visit_end_date_iso, site_visit_number, status
            FROM monitoring_visits
            WHERE id <> :visit_id
              AND COALESCE(site_id, '') = :site_id
              {study_clause}
              {sequence_clause}
              AND LOWER(TRIM(COALESCE(status, ''))) <> 'archived'
            ORDER BY {order_clause}
            LIMIT 1
            """
        ),
        params,
    )
    previous = previous_res.mappings().first()
    if not previous:
        return None

    previous_id = str(previous["id"])
    finding_rows_res = await db.execute(
        text(
            """
            SELECT *
            FROM monitoring_findings
            WHERE visit_id = :previous_visit_id
              AND LOWER(TRIM(COALESCE(status, ''))) NOT IN ('resolved', 'archived', 'closed')
            """
        ),
        {"previous_visit_id": previous_id},
    )
    finding_rows = finding_rows_res.mappings().all()
    action_map = await _load_action_items_map(db, [str(row["id"]) for row in finding_rows])
    findings = [
        _serialize_finding(row, action_map.get(str(row["id"])) or _legacy_action_items_from_finding_row(row), previous_id)
        for row in finding_rows
        if _is_open_finding_status(row.get("status"))
    ]
    findings.sort(key=lambda item: _finding_sort_number(str(item["id"])))

    schedule = _effective_visit_schedule_from_row(dict(previous))
    return {
        "id": previous_id,
        "label": _visit_label_from_site_number(previous.get("site_visit_number"), previous_id),
        "siteVisitNumber": previous.get("site_visit_number"),
        "visitDate": schedule.get("visitDate") or "Not recorded",
        "visitDateIso": schedule.get("visitDateIso") or "",
        "visitType": str(previous.get("visit_type") or ""),
        "openFindings": findings,
        "openFindingCount": len(findings),
    }


@router.get("/visits/{visit_id}/pre-visit")
async def get_pre_visit(visit_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    visit_row = await db.execute(
        text("SELECT visit_type FROM monitoring_visits WHERE id = :visit_id"),
        {"visit_id": visit_id},
    )
    visit = visit_row.mappings().first()
    await _sync_pre_visit_checklist(
        db,
        visit_id,
        str((visit or {}).get("visit_type") or "On-Site Monitoring"),
    )
    await db.commit()
    row = await db.execute(
        text(
            "SELECT risk, agenda, visit_date, pending_actions, pre_visit_reviewed_at, "
            "COALESCE(NULLIF(TRIM(pre_visit_report_status), ''), 'DRAFT') AS pre_visit_report_status "
            "FROM monitoring_pre_visit WHERE visit_id = :visit_id"
        ),
        {"visit_id": visit_id},
    )
    plan = row.mappings().first()
    checklist_rows = await db.execute(
        text("SELECT id, item_text, done, tag_type FROM monitoring_pre_visit_checklist WHERE visit_id = :visit_id ORDER BY display_order, id"),
        {"visit_id": visit_id},
    )
    checklist = [{"id": r.id, "text": r.item_text, "done": r.done, "tagType": r.tag_type} for r in checklist_rows.fetchall()]
    report_status = "DRAFT"
    if plan and plan.get("pre_visit_report_status"):
        report_status = str(plan["pre_visit_report_status"]).strip().upper() or "DRAFT"
    reviewed_at = _datetime_to_iso(plan.get("pre_visit_reviewed_at")) if plan else None
    previous_visit = await _previous_visit_follow_up_payload(db, visit_id)
    return {
        "plan": dict(plan) if plan else {"risk": "high", "agenda": "", "visit_date": "", "pending_actions": []},
        "checklist": checklist,
        "preVisitReportStatus": report_status,
        "preVisitReviewedAt": reviewed_at,
        "previousVisit": previous_visit,
    }


@router.patch("/visits/{visit_id}/pre-visit/checklist/{checklist_id}")
async def toggle_pre_visit_checklist(visit_id: str, checklist_id: int, db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    row = await db.execute(
        text(
            """
            UPDATE monitoring_pre_visit_checklist
            SET done = NOT done
            WHERE id = :checklist_id AND visit_id = :visit_id
            RETURNING id, item_text, done, tag_type;
            """
        ),
        {"visit_id": visit_id, "checklist_id": checklist_id},
    )
    item = row.mappings().first()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    await db.commit()
    return {"id": item["id"], "text": item["item_text"], "done": item["done"], "tagType": item["tag_type"]}


@router.put("/visits/{visit_id}/pre-visit/plan")
async def save_pre_visit_plan(visit_id: str, payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    await db.execute(
        text(
            """
            INSERT INTO monitoring_pre_visit (visit_id, risk, agenda, visit_date, pending_actions, updated_at)
            VALUES (:visit_id, :risk, :agenda, :visit_date, CAST(:pending_actions AS jsonb), CURRENT_TIMESTAMP)
            ON CONFLICT (visit_id)
            DO UPDATE SET
                risk = EXCLUDED.risk,
                agenda = EXCLUDED.agenda,
                visit_date = EXCLUDED.visit_date,
                pending_actions = EXCLUDED.pending_actions,
                updated_at = CURRENT_TIMESTAMP;
            """
        ),
        {
            "visit_id": visit_id,
            "risk": payload.get("risk", "high"),
            "agenda": payload.get("agenda", ""),
            "visit_date": payload.get("visitDate", ""),
            "pending_actions": json.dumps(payload.get("pendingActions", [])),
        },
    )
    await db.commit()
    return {"status": "saved"}


@router.post("/visits/{visit_id}/pre-visit/reviewed")
async def mark_pre_visit_reviewed(visit_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    existing_row = await db.execute(
        text(
            """
            SELECT pre_visit_reviewed_at
            FROM monitoring_pre_visit
            WHERE visit_id = :visit_id
            """
        ),
        {"visit_id": visit_id},
    )
    existing = existing_row.mappings().first()
    if existing and existing.get("pre_visit_reviewed_at"):
        return {
            "status": "reviewed",
            "already": True,
            "preVisitReviewedAt": _datetime_to_iso(existing.get("pre_visit_reviewed_at")),
        }

    reviewed_row = await db.execute(
        text(
            """
            INSERT INTO monitoring_pre_visit (visit_id, pre_visit_reviewed_at, updated_at)
            VALUES (:visit_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (visit_id) DO UPDATE SET
                pre_visit_reviewed_at = COALESCE(monitoring_pre_visit.pre_visit_reviewed_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            RETURNING pre_visit_reviewed_at
            """
        ),
        {"visit_id": visit_id},
    )
    reviewed = reviewed_row.mappings().first()
    await _append_visit_activity(
        db,
        visit_id,
        "CRA acknowledged review of the pre-visit preparation.",
        initials="CRA",
        color="green",
    )
    await db.commit()
    return {
        "status": "reviewed",
        "preVisitReviewedAt": _datetime_to_iso((reviewed or {}).get("pre_visit_reviewed_at")),
    }


@router.post("/visits/{visit_id}/pre-visit/send-summary")
async def send_pre_visit_summary(
    visit_id: str,
    body: PreVisitSummarySendBody,
    db: AsyncSession = Depends(get_db),
):
    """Email the AI pre-visit summary (plain text) to the site PI; optional CC list."""
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)

    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Summary content is empty")

    visit_res = await db.execute(
        text(
            """
            SELECT v.id, v.site_id, v.site_visit_number, v.principal_investigator, v.pi_email
            FROM monitoring_visits v
            WHERE v.id = :visit_id
            """
        ),
        {"visit_id": visit_id},
    )
    visit = visit_res.mappings().first()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")

    profile_row = None
    if visit.get("site_id"):
        profile_res = await db.execute(
            text(
                """
                SELECT sp.pi_name, sp.pi_email
                FROM sites s
                LEFT JOIN site_profiles sp ON sp.site_id = s.id
                WHERE (s.site_id = :site_id OR CAST(s.id AS TEXT) = :site_id)
                LIMIT 1
                """
            ),
            {"site_id": visit["site_id"]},
        )
        profile_row = profile_res.mappings().first()

    def _pick(*values: Any, default: str = "") -> str:
        for value in values:
            if value is None:
                continue
            text_value = str(value).strip()
            if text_value:
                return text_value
        return default

    pi_name = _pick(
        profile_row.get("pi_name") if profile_row else None,
        visit.get("principal_investigator"),
        default="Principal Investigator",
    )
    pi_email = _pick(
        profile_row.get("pi_email") if profile_row else None,
        visit.get("pi_email"),
        default="",
    )
    if not pi_email or "@" not in pi_email:
        raise HTTPException(status_code=400, detail="PI email is missing for this site")

    cc_raw = str(body.cc_emails or "").strip()
    cc_list: List[str] = []
    if cc_raw:
        for part in re.split(r"[;,]", cc_raw):
            addr = part.strip()
            if addr and "@" in addr and addr.lower() != pi_email.lower():
                if addr.lower() not in {e.lower() for e in cc_list}:
                    cc_list.append(addr)

    visit_label = _visit_label_from_site_number(visit.get("site_visit_number"), str(visit.get("id") or visit_id))
    subject = f"Pre-Visit Summary — {visit_label}"
    from_email = settings.smtp_user or "noreply@dizzaroo.com"
    to_addrs: List[str] = [pi_email] + cc_list

    ack_token = _build_previsit_report_ack_token(visit_id)
    frontend_base = (settings.frontend_base_url or "http://localhost:3000").strip().rstrip("/")
    ack_url = f"{frontend_base}/monitoring/visits/{quote(visit_id, safe='')}/pre-visit-report/acknowledge?token={quote(ack_token, safe='')}"

    intro_plain = (
        f"Dear {pi_name},\n\n"
        f"Please find below the pre-visit summary prepared for {visit_label}.\n\n"
    )
    plain_body = intro_plain + content + (
        f"\n\n---\n"
        f"When you have reviewed this summary, please confirm receipt using this secure link (no login required):\n{ack_url}\n"
    )

    safe_name = html.escape(pi_name or "Principal Investigator")
    safe_label = html.escape(visit_label)
    summary_html = markdown_summary_to_html(content)
    html_body = f"""
<div style="font-family:Arial,sans-serif;line-height:1.55;color:#111;max-width:720px">
  <p>Dear {safe_name},</p>
  <p>Please find below the pre-visit summary prepared for <strong>{safe_label}</strong>.</p>
  <div style="margin:16px 0;padding:14px 16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;font-size:14px">
    {summary_html}
  </div>
  <p style="margin-top:20px">After you have reviewed this document, please click the button below to acknowledge receipt. This confirms your site has received the pre-visit summary.</p>
  <p style="margin-top:16px">
    <a href="{html.escape(ack_url, quote=True)}"
       style="display:inline-block;padding:12px 20px;background:#4f46e5;color:#fff;text-decoration:none;border-radius:8px;font-weight:600">
      Acknowledge pre-visit summary
    </a>
  </p>
  <p style="font-size:12px;color:#64748b;margin-top:20px">If the button does not work, copy and paste this URL into your browser:<br/>
  <span style="word-break:break-all">{html.escape(ack_url, quote=True)}</span></p>
</div>
""".strip()

    # Behavior change: pre-visit summary is now enqueued via Celery rather
    # than sent inline. The previous 502-on-SMTP-failure response is no
    # longer raised here; transient failures are retried by the worker.
    enqueue_email(
        to=to_addrs,
        subject=subject,
        body=html_body,
        from_email=from_email,
        from_name="Dizzaroo CRM Monitoring",
        html=True,
    )

    await db.execute(
        text(
            """
            INSERT INTO monitoring_pre_visit (visit_id, pre_visit_report_status, updated_at)
            VALUES (:visit_id, 'SENT', CURRENT_TIMESTAMP)
            ON CONFLICT (visit_id) DO UPDATE SET
                pre_visit_report_status = 'SENT',
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {"visit_id": visit_id},
    )

    cc_note = f" (CC: {', '.join(cc_list)})" if cc_list else ""
    await _append_visit_activity(
        db,
        visit_id,
        f"Pre-visit summary emailed to PI{cc_note}. Awaiting site acknowledgment.",
        initials="AI",
        color="blue",
    )
    await db.commit()
    return {"status": "sent", "recipients": to_addrs, "preVisitReportStatus": "SENT"}


@router.post("/visits/{visit_id}/pre-visit/acknowledge")
async def acknowledge_pre_visit_report(
    visit_id: str,
    body: PreVisitAcknowledgeBody,
    db: AsyncSession = Depends(get_db),
):
    """Site acknowledges receipt of the pre-visit summary (magic link from email; no login)."""
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    token_data = _decode_previsit_report_ack_token(body.token.strip(), visit_id)
    if not token_data:
        raise HTTPException(status_code=400, detail="Invalid or expired acknowledgment link")

    row = await db.execute(
        text(
            "SELECT COALESCE(NULLIF(TRIM(pre_visit_report_status), ''), 'DRAFT') AS st "
            "FROM monitoring_pre_visit WHERE visit_id = :visit_id"
        ),
        {"visit_id": visit_id},
    )
    r = row.mappings().first()
    st = str(r.get("st") or "DRAFT").strip().upper() if r else "DRAFT"
    if st == "ACKNOWLEDGED":
        return {"status": "acknowledged", "already": True}
    if st != "SENT":
        raise HTTPException(
            status_code=409,
            detail="The pre-visit report has not been sent yet, or cannot be acknowledged in its current state.",
        )

    await db.execute(
        text(
            """
            INSERT INTO monitoring_pre_visit (visit_id, pre_visit_report_status, updated_at)
            VALUES (:visit_id, 'ACKNOWLEDGED', CURRENT_TIMESTAMP)
            ON CONFLICT (visit_id) DO UPDATE SET
                pre_visit_report_status = 'ACKNOWLEDGED',
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {"visit_id": visit_id},
    )
    await _append_visit_activity(
        db,
        visit_id,
        "Site acknowledged the pre-visit summary report.",
        initials="SITE",
        color="green",
    )
    await db.commit()
    return {"status": "acknowledged", "preVisitReportStatus": "ACKNOWLEDGED"}






