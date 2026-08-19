"""REST API: close_ack cluster (Phase 2.2 extract).

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
from app.utils.log_sanitize import sfmt

logger = logging.getLogger(__name__)
router = APIRouter(tags=["monitor"])

# Pull legacy helpers + body schemas from the parent router.
from app.modules.monitoring.aggregator import (  # noqa: E402
    _ensure_monitor_tables,
    _require_monitoring_visit,
    _append_visit_activity,
)


@router.post("/visits/{visit_id}/close")
async def close_visit(visit_id: str, db: AsyncSession = Depends(get_db)):
    """
    Lock a monitoring visit. Sets status to 'Closed' and stamps closed_at.
    Once closed the record becomes read-only.
    """
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)

    row = await db.execute(
        text("SELECT status, closed_at FROM monitoring_visits WHERE id = :id"),
        {"id": visit_id},
    )
    visit = row.mappings().first()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    if visit.get("closed_at") is not None:
        if str(visit.get("status", "")).strip().lower() != "closed":
            await db.execute(
                text(
                    """
                    UPDATE monitoring_visits
                    SET status = 'Closed'
                    WHERE id = :id
                    """
                ),
                {"id": visit_id},
            )
            await db.commit()
        return {"status": "closed", "visit_id": visit_id}

    if str(visit.get("status", "")).strip().lower() == "closed":
        raise HTTPException(status_code=400, detail="Visit is already closed.")

    await db.execute(
        text(
            """
            UPDATE monitoring_visits
            SET status = 'Closed',
                closed_at = (NOW() AT TIME ZONE 'UTC')
            WHERE id = :id
            """
        ),
        {"id": visit_id},
    )
    await _append_visit_activity(db, visit_id, "Visit closed and locked by CRA")
    await db.commit()

    # Public Notice Board: pair with the visit-created notice so the lifecycle
    # shows end-to-end. Best-effort — board failure must not roll back the
    # already-committed close. Visit row was just updated, so re-read it for
    # the (site_id, study_id, visit_type, site_visit_number) tuple.
    try:
        from app.utils.system_notices import post_site_event_notice
        info = (
            await db.execute(
                text(
                    "SELECT site_id, study_id, visit_type, site_visit_number, cra_name "
                    "FROM monitoring_visits WHERE id = :id"
                ),
                {"id": visit_id},
            )
        ).mappings().first()
        if info and info.get("site_id"):
            label = info.get("visit_type") or "Monitoring"
            num = info.get("site_visit_number")
            tail = f" (visit #{num})" if num else ""
            await post_site_event_notice(
                db,
                site_ref=info["site_id"],
                study_ref=info.get("study_id"),
                event_type="monitoring_visit_closed",
                message=f"{label} visit{tail} was closed and locked by {info.get('cra_name') or 'CRA'}.",
                metadata={
                    "visit_id": visit_id,
                    "visit_type": info.get("visit_type"),
                    "site_visit_number": info.get("site_visit_number"),
                    "cra_name": info.get("cra_name"),
                },
            )
    except Exception:
        logger.exception("close_visit: notice-board hook failed for visit %s", sfmt(visit_id))

    # Kafka: closing a generic interim / on-site monitoring visit publishes
    # IMV_CLOSED to the Data Platform (qualification/initiation/close-out visits
    # are reported on their own phases). Best-effort & self-guarded.
    try:
        from app.integrations.milestones_kafka import publish_visit_milestone

        minfo = (
            await db.execute(
                text("SELECT site_id, visit_type FROM monitoring_visits WHERE id = :id"),
                {"id": visit_id},
            )
        ).mappings().first()
        if minfo and minfo.get("site_id"):
            await publish_visit_milestone(
                site_id=str(minfo["site_id"]),
                visit_type=minfo.get("visit_type"),
                phase="closed",
            )
    except Exception:
        logger.exception("close_visit: milestone Kafka hook failed for visit %s", sfmt(visit_id))

    return {"status": "closed", "visit_id": visit_id}


# ── PI Acknowledgment (public — no auth required) ─────────────────────────────

class AcknowledgeBody(BaseModel):
    token: str = Field(..., min_length=1)


@router.post("/acknowledge")
async def acknowledge_follow_up_letter(
    body: AcknowledgeBody,
    db: AsyncSession = Depends(get_db),
):
    """
    Public endpoint — no authentication required.
    The PI clicks the magic link, which calls this endpoint with the one-time token.
    Sets ack_status to 'acknowledged' and stamps acknowledged_at.
    """
    token = body.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token is required.")

    row = await db.execute(
        text(
            """
            SELECT visit_id, ack_status, acknowledged_at
            FROM monitoring_follow_up_letters
            WHERE ack_token = :token
            """
        ),
        {"token": token},
    )
    record = row.mappings().first()

    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired acknowledgment link.")

    if record["ack_status"] == "acknowledged":
        raise HTTPException(status_code=400, detail="This link has already been used.")

    visit_id = record["visit_id"]

    await db.execute(
        text(
            """
            UPDATE monitoring_follow_up_letters
            SET ack_status      = 'acknowledged',
                acknowledged_at = (NOW() AT TIME ZONE 'UTC'),
                ack_token       = NULL
            WHERE visit_id = :visit_id
            """
        ),
        {"visit_id": visit_id},
    )
    await _append_visit_activity(db, visit_id, "Follow-up letter acknowledged by PI")
    await db.commit()

    return {
        "status": "acknowledged",
        "visit_id": visit_id,
        "message": "Thank you. Your acknowledgment has been recorded.",
    }


