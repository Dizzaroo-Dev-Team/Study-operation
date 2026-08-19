"""REST API: post_visit_and_report cluster (Phase 2.2 extract).

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

# Pull legacy helpers + body schemas from the parent router.
from app.modules.monitoring.aggregator import (  # noqa: E402
    _ensure_monitor_tables,
    _require_monitoring_visit,
    _append_visit_activity,
)
# MVR helpers live in their own sub-router module; import directly to avoid
# the import-order cycle (monitor.router's re-export of these names runs
# AFTER this sub-router is loaded).
from app.modules.monitoring.routes.mvr_templates import (  # noqa: E402
    _fetch_active_mvr_template_row,
    _mvr_template_public,
)


@router.get("/visits/{visit_id}/post-visit")
async def get_post_visit(visit_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    row = await db.execute(text("SELECT * FROM monitoring_post_visit WHERE visit_id = :visit_id"), {"visit_id": visit_id})
    post_visit = row.mappings().first()
    return dict(post_visit) if post_visit else {}


@router.put("/visits/{visit_id}/post-visit")
async def save_post_visit(visit_id: str, payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    await db.execute(
        text(
            """
            INSERT INTO monitoring_post_visit (
                visit_id, summary, critical_issues, rating, follow_up, next_date, action_plan, recommendations, cra_name, updated_at
            ) VALUES (
                :visit_id, :summary, :critical_issues, :rating, :follow_up, :next_date, :action_plan, :recommendations, :cra_name, CURRENT_TIMESTAMP
            )
            ON CONFLICT (visit_id)
            DO UPDATE SET
                summary = EXCLUDED.summary,
                critical_issues = EXCLUDED.critical_issues,
                rating = EXCLUDED.rating,
                follow_up = EXCLUDED.follow_up,
                next_date = EXCLUDED.next_date,
                action_plan = EXCLUDED.action_plan,
                recommendations = EXCLUDED.recommendations,
                cra_name = EXCLUDED.cra_name,
                updated_at = CURRENT_TIMESTAMP;
            """
        ),
        {
            "visit_id": visit_id,
            "summary": payload.get("summary", ""),
            "critical_issues": payload.get("criticalIssues", ""),
            "rating": payload.get("rating", "Satisfactory"),
            "follow_up": payload.get("followUp", "Yes — Within 30 days"),
            "next_date": payload.get("nextDate", ""),
            "action_plan": payload.get("actionPlan", ""),
            "recommendations": payload.get("recommendations", ""),
            "cra_name": payload.get("craName", ""),
        },
    )
    await db.commit()
    return {"status": "saved"}


def _report_payload_locked_for_template_sync(payload: Dict[str, Any]) -> bool:
    st = str(payload.get("reportStatus") or "Draft").strip().lower()
    # Rejected reports are editable again, but they are revised against reviewer
    # comments that anchor to the template they were submitted with — never
    # re-sync them to the live org template (that would swap templateId and
    # archive custom fields, breaking the revision cycle).
    return st in ("in review", "approved", "rejected")


def _report_data_field_ids(payload: Dict[str, Any]) -> set:
    """Field ids present in saved report data (submission, archive, or legacy keys)."""
    system = frozenset(
        {
            "reportStatus",
            "schemaVersion",
            "submissionData",
            "archivedData",
            "templateId",
            "templateVersion",
            "templateSnapshot",
            "templateName",
            "customTemplateFields",
            "rejectionReason",
            "revisionBaseline",
        }
    )
    ids: set = set()
    raw_sub = payload.get("submissionData")
    if isinstance(raw_sub, dict):
        ids.update(str(k) for k in raw_sub.keys() if k)
    raw_arch = payload.get("archivedData")
    if isinstance(raw_arch, dict):
        ids.update(str(k) for k in raw_arch.keys() if k)
    # Legacy-layout custom templates store their answers keyed by field id
    # under customTemplateFields — count those, or deriving a frozen template
    # would filter out every custom field.
    raw_custom = payload.get("customTemplateFields")
    if isinstance(raw_custom, dict):
        ids.update(str(k) for k in raw_custom.keys() if k)
    for k in payload.keys():
        if k not in system:
            ids.add(str(k))
    return ids


def _filter_template_schema_to_field_ids(schema: Dict[str, Any], field_ids: set) -> Dict[str, Any]:
    """Keep only template fields that exist in the saved report data (plus section headers)."""
    fields = schema.get("fields") or []
    if not isinstance(fields, list) or not field_ids:
        out = dict(schema) if isinstance(schema, dict) else {}
        out["fields"] = []
        return out

    kept: List[Dict[str, Any]] = []
    pending_section: Optional[Dict[str, Any]] = None
    for f in fields:
        if not isinstance(f, dict):
            continue
        ftype = str(f.get("type") or "").lower()
        if ftype == "section":
            pending_section = f
            continue
        fid = str(f.get("id") or "").strip()
        if fid and fid in field_ids:
            if pending_section is not None:
                kept.append(pending_section)
                pending_section = None
            kept.append(f)

    out = dict(schema) if isinstance(schema, dict) else {}
    out["fields"] = kept
    return out


async def _resolve_frozen_report_template(
    db: AsyncSession, payload: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Return the exact template schema a locked report should render — never the live org template."""
    from app.modules.monitoring.routes.mvr_templates import (  # noqa: E402
        _fetch_active_mvr_template_row,
        _fetch_mvr_template_row_by_id,
        _mvr_template_public,
    )

    snap = payload.get("templateSnapshot")
    if isinstance(snap, dict) and isinstance(snap.get("schema"), dict):
        return snap

    tid = str(payload.get("templateId") or "").strip()
    trow = await _fetch_mvr_template_row_by_id(db, tid) if tid else None
    if not trow:
        trow = await _fetch_active_mvr_template_row(db, "default")
    if not trow:
        return None

    tpl = _mvr_template_public(trow)
    field_ids = _report_data_field_ids(payload)
    if not field_ids:
        return tpl

    schema = tpl.get("schema") or {}
    tpl = dict(tpl)
    tpl["schema"] = _filter_template_schema_to_field_ids(schema, field_ids)
    return tpl


def _mvr_template_field_input_ids(schema: Dict[str, Any]) -> set:
    out = set()
    for f in schema.get("fields") or []:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id") or "").strip()
        t = str(f.get("type") or "").lower()
        if not fid or t == "section":
            continue
        out.add(fid)
    return out


def _sync_mvr_payload_with_template(
    payload: Dict[str, Any], template_row: Dict[str, Any]
) -> Tuple[Dict[str, Any], bool]:
    """Draft-only: align submissionData + template version; archive removed fields & legacy keys."""
    if _report_payload_locked_for_template_sync(payload):
        return payload, False
    schema = template_row.get("schema")
    if not isinstance(schema, dict):
        return payload, False
    tid = str(template_row.get("id") or "")
    tv = int(template_row.get("version") or 1)
    cur_tid = str(payload.get("templateId") or "")
    cur_tv = int(payload.get("templateVersion") or 0)
    if cur_tid == tid and cur_tv == tv:
        return payload, False
    if not cur_tid:
        # Report was never authored against the template system (legacy/free-form
        # report). Do NOT treat "no template" as "different template" — that would
        # archive every flat field the moment any org template is published/edited,
        # wiping the report's visible content on the next GET/save.
        return payload, False

    input_ids = _mvr_template_field_input_ids(schema)
    out = dict(payload)
    sub: Dict[str, Any] = {}
    raw_sub = payload.get("submissionData")
    if isinstance(raw_sub, dict):
        sub = dict(raw_sub)
    arch: Dict[str, Any] = {}
    raw_arch = payload.get("archivedData")
    if isinstance(raw_arch, dict):
        arch = dict(raw_arch)

    new_sub: Dict[str, Any] = {}
    for fid in input_ids:
        if fid in sub:
            new_sub[fid] = sub[fid]
    for fid, val in sub.items():
        if fid not in input_ids:
            arch[fid] = val

    out["submissionData"] = new_sub
    out["archivedData"] = arch
    out["templateId"] = tid
    out["templateVersion"] = tv
    return out, True




async def _persist_visit_report_payload(db: AsyncSession, visit_id: str, payload: Dict[str, Any]) -> None:
    merged = dict(payload)
    merged.setdefault("schemaVersion", 1)
    payload_json = json.dumps(merged)
    await db.execute(
        text(
            """
            INSERT INTO monitoring_visit_reports (visit_id, payload, updated_at)
            VALUES (:visit_id, CAST(:payload_json AS jsonb), CURRENT_TIMESTAMP)
            ON CONFLICT (visit_id)
            DO UPDATE SET
                payload = EXCLUDED.payload,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {"visit_id": visit_id, "payload_json": payload_json},
    )


@router.get("/visits/{visit_id}/visit-report")
async def get_visit_report(visit_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    template_row = await _fetch_active_mvr_template_row(db, "default")
    row_result = await db.execute(
        text(
            """
            SELECT payload, updated_at
            FROM monitoring_visit_reports
            WHERE visit_id = :visit_id
            """
        ),
        {"visit_id": visit_id},
    )
    row = row_result.mappings().first()
    if not row:
        payload_out: Dict[str, Any] = {}
        updated_iso = None
    else:
        raw_pl = row.get("payload")
        if raw_pl is None:
            payload_out = {}
        elif isinstance(raw_pl, dict):
            payload_out = dict(raw_pl)
        elif isinstance(raw_pl, str):
            try:
                parsed = json.loads(raw_pl)
                payload_out = parsed if isinstance(parsed, dict) else {}
            except Exception:
                payload_out = {}
        else:
            payload_out = {}
        ua = row.get("updated_at")
        updated_iso = None
        try:
            if ua is not None and hasattr(ua, "isoformat"):
                updated_iso = ua.isoformat()
        except Exception:
            updated_iso = None

    did_sync = False
    if template_row:
        payload_out, did_sync = _sync_mvr_payload_with_template(payload_out, template_row)

    tpl: Optional[Dict[str, Any]] = None
    if _report_payload_locked_for_template_sync(payload_out):
        frozen_tpl = await _resolve_frozen_report_template(db, payload_out)
        if frozen_tpl and not payload_out.get("templateSnapshot"):
            payload_out = dict(payload_out)
            payload_out["templateSnapshot"] = frozen_tpl
            await _persist_visit_report_payload(db, visit_id, payload_out)
            await db.commit()
        tpl = frozen_tpl
    elif template_row:
        tpl = _mvr_template_public(template_row)

    return {
        "payload": payload_out,
        "updated_at": updated_iso,
        "activeTemplate": tpl,
        "templateSynced": did_sync,
    }


@router.put("/visits/{visit_id}/visit-report")
async def save_visit_report(visit_id: str, body: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    raw_p = body.get("payload")
    if not isinstance(raw_p, dict):
        raw_p = {}
    merged: Dict[str, Any] = dict(raw_p)
    merged.setdefault("schemaVersion", 1)
    template_row = await _fetch_active_mvr_template_row(db, "default")
    if template_row:
        merged, _ = _sync_mvr_payload_with_template(merged, template_row)
    payload_json = json.dumps(merged)
    await db.execute(
        text(
            """
            INSERT INTO monitoring_visit_reports (visit_id, payload, updated_at)
            VALUES (:visit_id, CAST(:payload_json AS jsonb), CURRENT_TIMESTAMP)
            ON CONFLICT (visit_id)
            DO UPDATE SET
                payload = EXCLUDED.payload,
                updated_at = CURRENT_TIMESTAMP;
            """
        ),
        {"visit_id": visit_id, "payload_json": payload_json},
    )
    await db.commit()
    return {"status": "saved"}




