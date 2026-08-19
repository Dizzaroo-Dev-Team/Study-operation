"""REST API: follow_up_letter cluster (Phase 2.2 extract).

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
    FOLLOW_UP_LETTER_DEFAULT_CONTENT,
)


async def _ensure_follow_up_delivery_columns(db: AsyncSession) -> None:
    await db.execute(
        text(
            "ALTER TABLE monitoring_follow_up_letters "
            "ADD COLUMN IF NOT EXISTS last_sent VARCHAR(100) NOT NULL DEFAULT '';"
        )
    )
    await db.execute(
        text(
            "ALTER TABLE monitoring_follow_up_letters "
            "ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(50) NOT NULL DEFAULT 'Draft';"
        )
    )


@router.get("/visits/{visit_id}/follow-up-letter")
async def get_follow_up_letter(visit_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    await _ensure_follow_up_delivery_columns(db)
    await _require_monitoring_visit(db, visit_id)
    row = await db.execute(
        text(
            """
            SELECT content, updated_at, ack_status, acknowledged_at, last_sent, delivery_status
            FROM monitoring_follow_up_letters
            WHERE visit_id = :visit_id
            """
        ),
        {"visit_id": visit_id},
    )
    letter = row.mappings().first()
    if letter:
        return dict(letter)

    await db.execute(
        text(
            """
            INSERT INTO monitoring_follow_up_letters (visit_id, content, updated_at)
            VALUES (:visit_id, :content, CURRENT_TIMESTAMP)
            ON CONFLICT (visit_id)
            DO NOTHING;
            """
        ),
        {"visit_id": visit_id, "content": FOLLOW_UP_LETTER_DEFAULT_CONTENT},
    )
    await db.commit()
    return {
        "content": FOLLOW_UP_LETTER_DEFAULT_CONTENT,
        "updated_at": None,
        "ack_status": "pending",
        "acknowledged_at": None,
        "last_sent": None,
        "delivery_status": "Draft",
    }


@router.put("/visits/{visit_id}/follow-up-letter")
async def save_follow_up_letter(visit_id: str, payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    await _ensure_follow_up_delivery_columns(db)
    await _require_monitoring_visit(db, visit_id)
    content = str(payload.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    # Once the site has acknowledged the follow-up letter, lock further edits.
    existing = await db.execute(
        text("SELECT ack_status FROM monitoring_follow_up_letters WHERE visit_id = :visit_id"),
        {"visit_id": visit_id},
    )
    existing_row = existing.mappings().first()
    if existing_row and str(existing_row.get("ack_status") or "").lower() == "acknowledged":
        raise HTTPException(
            status_code=409,
            detail="Follow-up letter has been acknowledged by the site and is locked.",
        )

    await db.execute(
        text(
            """
            INSERT INTO monitoring_follow_up_letters (visit_id, content, updated_at)
            VALUES (:visit_id, :content, CURRENT_TIMESTAMP)
            ON CONFLICT (visit_id)
            DO UPDATE SET
                content = EXCLUDED.content,
                updated_at = CURRENT_TIMESTAMP;
            """
        ),
        {"visit_id": visit_id, "content": content},
    )
    await _append_visit_activity(db, visit_id, "Updated follow-up letter")
    await db.commit()
    return {"status": "saved"}


async def _load_follow_up_summary_findings_from_visit_tab(db: AsyncSession, visit_id: str) -> List[Dict[str, str]]:
    """
    Rows for PDF/DOCX §3 — sourced from monitoring_findings (Findings tab), not from
    ad-hoc rows typed only in the follow-up letter draft UI.
    """
    await _ensure_monitor_tables(db)
    rows = await db.execute(
        text(
            """
            SELECT id, category, description, severity,
                   COALESCE(subject_id, '') AS subject_id,
                   COALESCE(reference, '') AS reference,
                   COALESCE(due_date, '') AS due_date,
                   COALESCE(resolution, '') AS resolution,
                   assignee_initials, assignee_name, assignee_color
            FROM monitoring_findings
            WHERE visit_id = :visit_id
              AND LOWER(TRIM(COALESCE(status, ''))) <> 'archived'
            ORDER BY id ASC
            """
        ),
        {"visit_id": visit_id},
    )
    raw_rows = rows.mappings().all()
    finding_ids = [str(r["id"]) for r in raw_rows]
    action_map: Dict[str, list] = {}
    if finding_ids:
        ai_rows = await db.execute(
            text(
                """
                SELECT finding_id, assignee_initials, assignee_name, assignee_color,
                       due_date, resolution
                FROM monitoring_finding_action_items
                WHERE finding_id = ANY(:finding_ids)
                ORDER BY finding_id ASC, display_order ASC, id ASC
                """
            ),
            {"finding_ids": finding_ids},
        )
        for ai in ai_rows.mappings().all():
            fid = str(ai["finding_id"])
            action_map.setdefault(fid, []).append(
                {
                    "assignee": {
                        "initials": ai["assignee_initials"],
                        "name": ai["assignee_name"],
                        "color": ai["assignee_color"],
                    },
                    "dueDate": ai["due_date"],
                    "resolution": ai.get("resolution") or "",
                }
            )

    out: List[Dict[str, str]] = []
    for r in raw_rows:
        due_raw = str(r.get("due_date") or "").strip()
        if due_raw.upper() == "TBD":
            due_raw = ""
        fid = str(r["id"])
        action_items = action_map.get(fid)
        if not action_items:
            action_items = [
                {
                    "assignee": {
                        "initials": r["assignee_initials"],
                        "name": r["assignee_name"],
                        "color": r["assignee_color"],
                    },
                    "dueDate": r.get("due_date") or "",
                    "resolution": str(r.get("resolution") or "").strip(),
                }
            ]
        out.append(
            {
                "subject": str(r.get("subject_id") or "").strip(),
                "description": str(r.get("description") or ""),
                "category": str(r.get("category") or ""),
                "severity": str(r.get("severity") or ""),
                "reference": str(r.get("reference") or "").strip(),
                "dueDate": due_raw,
                "resolution": str(r.get("resolution") or "").strip(),
                "actionItems": action_items,
            }
        )
    return out


def _findings_to_action_items(findings: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """§4 Action Items table — one row per action item on the Visit Findings tab."""
    items: List[Dict[str, str]] = []
    for f in findings:
        cat = str(f.get("category") or "").strip()
        desc = str(f.get("description") or "").strip()
        base_title = " — ".join(p for p in (cat, desc) if p) or "—"
        nested = f.get("actionItems") or f.get("action_items")
        action_rows: List[Dict[str, str]] = []
        if isinstance(nested, list) and nested:
            for ai in nested:
                if not isinstance(ai, dict):
                    continue
                assignee = ai.get("assignee") if isinstance(ai.get("assignee"), dict) else {}
                due = str(ai.get("dueDate") or ai.get("due_date") or "").strip()
                if due.upper() == "TBD":
                    due = ""
                resolution = str(ai.get("resolution") or "").strip()
                who = str(ai.get("assigneeName") or assignee.get("name") or "").strip()
                action_rows.append(
                    {
                        "title": base_title,
                        "action": resolution or "Address per protocol and monitor guidance.",
                        "dueDate": due,
                        "assignTo": who or "—",
                        "priority": str(f.get("severity") or "Major"),
                    }
                )
        if not action_rows:
            due = str(f.get("dueDate") or f.get("due_date") or "").strip()
            if due.upper() == "TBD":
                due = ""
            resolution = str(f.get("resolution") or "").strip()
            action_rows.append(
                {
                    "title": base_title,
                    "action": resolution or "Address per protocol and monitor guidance.",
                    "dueDate": due,
                    "assignTo": "—",
                    "priority": str(f.get("severity") or "Major"),
                }
            )
        items.extend(action_rows)
    return items


def _action_items_or_placeholder(findings: List[Dict[str, str]]) -> List[Dict[str, str]]:
    items = _findings_to_action_items(findings)
    if items:
        return items
    return [
        {
            "title": "No action items — no findings recorded on the Visit Findings tab for this visit.",
            "action": "",
            "dueDate": "",
            "assignTo": "",
            "priority": "",
        }
    ]


def _build_follow_up_letter_pdf(payload: Dict[str, Any], pdf_path: Path) -> None:
    """
    Build the Site Follow-Up Letter PDF directly with reportlab.

    Replaces the previous DOCX→LibreOffice→PDF pipeline (which had a
    5–15 s cold start). Pure-Python PDF generation typically completes
    in 50–200 ms.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    form = payload.get("form", {}) or {}
    areas = payload.get("areas", []) or []
    findings = payload.get("findings", []) or []
    action_items = _action_items_or_placeholder(findings)

    def g(key: str) -> str:
        v = form.get(key, "")
        return "" if v is None else str(v)

    blue = colors.HexColor("#2E5496")
    blue_alt = colors.HexColor("#D9E1F2")
    blue_light = colors.HexColor("#EBF1F8")
    grey_text = colors.HexColor("#595959")
    crit_red = colors.HexColor("#C00000")
    major_orange = colors.HexColor("#CC6600")
    minor_green = colors.HexColor("#007000")

    base = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=base["Title"], fontName="Helvetica-Bold",
        fontSize=18, leading=22, textColor=blue, alignment=TA_CENTER, spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "Sub", parent=base["Normal"], fontName="Helvetica-Oblique",
        fontSize=10, leading=12, textColor=grey_text, alignment=TA_CENTER, spaceAfter=14,
    )
    section_style = ParagraphStyle(
        "Section", parent=base["Heading2"], fontName="Helvetica-Bold",
        fontSize=12, leading=15, textColor=blue, spaceBefore=14, spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body", parent=base["Normal"], fontName="Helvetica",
        fontSize=10, leading=14, textColor=colors.black, alignment=TA_LEFT, spaceAfter=4,
    )
    end_style = ParagraphStyle(
        "End", parent=base["Normal"], fontName="Helvetica-Oblique",
        fontSize=9, leading=11, textColor=colors.HexColor("#808080"), alignment=TA_CENTER,
        spaceBefore=14,
    )

    def cell(text: str) -> Paragraph:
        return Paragraph(text or "&nbsp;", body_style)

    def label_cell(text: str) -> Paragraph:
        return Paragraph(f"<b>{text}</b>", body_style)

    def severity_paragraph(level: str) -> Paragraph:
        color = {
            "Critical": "#C00000",
            "Major": "#CC6600",
            "Minor": "#007000",
        }.get(level, "#000000")
        return Paragraph(
            f'<font color="{color}"><b>{level or "&nbsp;"}</b></font>',
            body_style,
        )

    def make_doc():
        return SimpleDocTemplate(
            str(pdf_path),
            pagesize=LETTER,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            title="Site Follow-Up Letter",
        )

    elements: List[Any] = []
    elements.append(Paragraph("SITE FOLLOW-UP LETTER", title_style))
    elements.append(Paragraph("Monitoring Visit — Post-Visit Communication", subtitle_style))

    # ── Header info table (4 columns) ──────────────────────────────────
    header_data = [
        [label_cell("Date:"), cell(g("letterDate")), label_cell("Visit Date:"), cell(g("visitDate"))],
        [label_cell("Study Title:"), cell(g("studyTitle")), label_cell("Protocol Number:"), cell(g("protocolNumber"))],
        [label_cell("Site:"), cell(g("siteName")), label_cell("Principal Investigator:"), cell(g("piName"))],
        [label_cell("Monitor Name:"), cell(g("monitorName")), label_cell("Sponsor:"), cell(g("sponsorName"))],
    ]
    col_w = (LETTER[0] - 1.5 * inch) / 4
    header_table = Table(header_data, colWidths=[col_w] * 4)
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), blue_alt),
        ("BACKGROUND", (2, 0), (2, -1), blue_alt),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#AAAAAA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(header_table)

    # ── 1. INTRODUCTION ────────────────────────────────────────────────
    elements.append(Paragraph("1. INTRODUCTION", section_style))
    elements.append(Paragraph(f"Dear <b>{g('piName')}</b>,", body_style))
    elements.append(Paragraph(
        f"This letter is issued as a formal follow-up to the monitoring visit conducted at "
        f"<b>{g('siteName')}</b> on <b>{g('visitDate')}</b>, as part of the "
        f"<b>{g('studyTitle')}</b> (Protocol Number: <b>{g('protocolNumber')}</b>) sponsored by "
        f"<b>{g('sponsorName')}</b>.",
        body_style,
    ))
    elements.append(Paragraph(
        f"The purpose of this correspondence is to document the findings, observations, and "
        f"action items identified during the visit. During the visit, a total of "
        f"<b>{g('totalSubjects')}</b> subjects were reviewed, with <b>{g('ongoingSubjects')}</b> "
        f"currently ongoing in the study.",
        body_style,
    ))
    elements.append(Paragraph(
        "We appreciate the cooperation and assistance provided by you and your study team during "
        "the visit.",
        body_style,
    ))

    # ── 2. AREAS REVIEWED ──────────────────────────────────────────────
    elements.append(Paragraph("2. AREAS REVIEWED", section_style))
    elements.append(Paragraph("The following areas were reviewed during the monitoring visit:", body_style))
    areas_header = [label_cell("#"), label_cell("Area Reviewed"), label_cell("Status")]
    areas_rows = [areas_header] + [
        [cell(str(i + 1)), cell(str(a.get("name", "") or "")), cell(str(a.get("status", "") or ""))]
        for i, a in enumerate(areas)
    ]
    areas_table = Table(areas_rows, colWidths=[0.4 * inch, 4.0 * inch, 2.5 * inch])
    areas_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), blue),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#AAAAAA")),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, blue_light]),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    elements.append(areas_table)

    # ── 3. SUMMARY OF FINDINGS ────────────────────────────────────────
    elements.append(Paragraph("3. SUMMARY OF FINDINGS", section_style))
    elements.append(Paragraph(
        "The following findings were identified during the monitoring visit. Each finding is "
        "assigned a severity level in accordance with GCP guidelines.",
        body_style,
    ))
    f_header = [label_cell(h) for h in ["#", "Subject", "Description", "Category", "Severity", "Reference"]]
    f_rows = [f_header] + [
        [
            cell(str(i + 1)),
            cell(str(f.get("subject", "") or "")),
            cell(str(f.get("description", "") or "")),
            cell(str(f.get("category", "") or "")),
            severity_paragraph(str(f.get("severity", "") or "")),
            cell(str(f.get("reference", "") or "")),
        ]
        for i, f in enumerate(findings)
    ]
    f_table = Table(
        f_rows,
        colWidths=[0.3 * inch, 0.85 * inch, 2.4 * inch, 1.3 * inch, 0.75 * inch, 1.3 * inch],
    )
    f_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), blue),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#AAAAAA")),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, blue_light]),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    elements.append(f_table)

    # ── 4. ACTION ITEMS (from Visit Findings tab) ─────────────────────
    elements.append(Paragraph("4. ACTION ITEMS", section_style))
    elements.append(Paragraph(
        "The table below summarizes all required actions arising from this monitoring visit.",
        body_style,
    ))
    a_header = [label_cell(h) for h in ["#", "Action Item / Finding", "Required Action", "Due Date", "Assign To", "Priority"]]
    a_rows = [a_header] + [
        [
            cell(str(i + 1)),
            cell(str(a.get("title", "") or "")),
            cell(str(a.get("action", "") or "")),
            cell(str(a.get("dueDate", "") or "")),
            cell(str(a.get("assignTo", "") or "")),
            severity_paragraph(str(a.get("priority", "") or "")),
        ]
        for i, a in enumerate(action_items)
    ]
    a_table = Table(
        a_rows,
        colWidths=[0.3 * inch, 1.4 * inch, 2.1 * inch, 0.85 * inch, 1.0 * inch, 1.15 * inch],
    )
    a_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), blue),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#AAAAAA")),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, blue_light]),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    elements.append(a_table)

    # ── 5. RESOLUTION TIMELINES ───────────────────────────────────────
    elements.append(Paragraph("5. RESOLUTION TIMELINES", section_style))
    res_header = [label_cell("Severity"), label_cell("Required Response Timeline"), label_cell("Escalation Timeline")]
    res_rows = [
        res_header,
        [cell("Critical"), cell(g("criticalTimeline")), cell(g("criticalEscalation"))],
        [cell("Major"),    cell(g("majorTimeline")),    cell(g("majorEscalation"))],
        [cell("Minor"),    cell(g("minorTimeline")),    cell(g("minorEscalation"))],
    ]
    res_table = Table(res_rows, colWidths=[1.2 * inch, 2.85 * inch, 2.85 * inch])
    res_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), blue),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#AAAAAA")),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, blue_light]),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    elements.append(res_table)

    # ── 6. CLOSING REMARKS ────────────────────────────────────────────
    elements.append(Paragraph("6. CLOSING REMARKS", section_style))
    elements.append(Paragraph(
        "Please confirm receipt of this letter and provide your written response addressing each "
        "action item. Your response should be directed to "
        f"<b>{g('monitorEmail')}</b> with a copy to <b>{g('sponsorContact')}</b>.",
        body_style,
    ))
    elements.append(Paragraph(
        "Should you require clarification on any of the items raised in this letter, please do not "
        "hesitate to contact me directly. We look forward to your timely response and continued "
        "collaboration on this study.",
        body_style,
    ))
    elements.append(Paragraph("Thank you for your continued support.", body_style))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph("Sincerely,", body_style))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("<b>AUTHORIZATION</b>", body_style))

    auth_rows = [
        [label_cell("Monitor Name"), cell(g("monitorName"))],
        [label_cell("Monitor Signature"), cell("")],
        [label_cell("Date"), cell(g("letterDate"))],
        [label_cell("Sponsor / CRO Contact"), cell(g("sponsorContact"))],
    ]
    auth_table = Table(auth_rows, colWidths=[2.0 * inch, 4.9 * inch])
    auth_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), blue_alt),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#AAAAAA")),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    elements.append(auth_table)
    elements.append(Paragraph("— END OF DOCUMENT —", end_style))

    doc = make_doc()
    doc.build(elements)


def _send_follow_up_letter_email_blocking(
    pi_email: str,
    greeting_name: str,
    sender_name: str,
    pdf_path: Path,
    magic_link: str,
) -> None:
    """
    Background-task body: sends the email, then deletes the temp PDF.

    Runs after the API request returns, so the user gets a near-instant
    "Sent" toast while delivery completes asynchronously.
    """
    try:
        from_email = getattr(settings, "smtp_user", None) or "noreply@dizzaroo.com"

        html_body = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
        <tr>
          <td style="background:linear-gradient(135deg,#2E5496 0%,#0F6E56 100%);padding:28px 32px;text-align:center;">
            <span style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.02em;">Dizzaroo CRM</span>
          </td>
        </tr>
        <tr>
          <td style="padding:36px 32px;">
            <p style="font-size:16px;color:#1e293b;margin:0 0 12px;">Dear {greeting_name},</p>
            <p style="font-size:15px;color:#475569;line-height:1.7;margin:0 0 20px;">
              Please find attached the <strong>Follow-Up Letter</strong> relating to the recent
              monitoring visit. Kindly review the attached PDF at your earliest convenience.
            </p>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">
            <p style="font-size:15px;color:#1e293b;font-weight:600;margin:0 0 8px;">
              Acknowledge Receipt
            </p>
            <p style="font-size:14px;color:#475569;line-height:1.6;margin:0 0 24px;">
              To confirm receipt of this letter for our audit trail, please click the button below.
              No login is required — one click is all it takes.
            </p>
            <table cellpadding="0" cellspacing="0" style="margin:0 auto 24px;">
              <tr>
                <td align="center" style="border-radius:8px;background:linear-gradient(135deg,#2E5496 0%,#1a6e8a 100%);">
                  <a href="{magic_link}" target="_blank"
                     style="display:inline-block;padding:14px 36px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;letter-spacing:0.01em;">
                    Acknowledge Receipt
                  </a>
                </td>
              </tr>
            </table>
            <p style="font-size:12px;color:#94a3b8;text-align:center;margin:0 0 24px;">
              This link is for single use only. If you have already acknowledged, no further action is needed.
            </p>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin:0 0 20px;">
            <p style="font-size:14px;color:#475569;line-height:1.6;margin:0;">
              If you have any questions, please contact the assigned monitor directly.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#f8fafc;padding:20px 32px;text-align:center;border-top:1px solid #e2e8f0;">
            <p style="font-size:13px;font-weight:600;color:#1e293b;margin:0 0 4px;">{sender_name}</p>
            <p style="font-size:12px;color:#94a3b8;margin:0;">
              Dizzaroo CRM &middot; Secure Clinical Research Management
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

        # Send synchronously while the temp PDF still exists. enqueue_email +
        # Celery would delete this file in `finally` before the worker reads it,
        # so the HTML email would arrive without the PDF attachment.
        if not pdf_path.is_file():
            logger.error("Follow-up PDF missing before send: %s", pdf_path)
            return

        result = smtp_service.send_email(
            to=pi_email,
            subject="Action Required: Acknowledge Follow-Up Letter – Post-Monitoring Visit",
            body=html_body,
            from_email=from_email,
            from_name=sender_name,
            html=True,
            attachments=[str(pdf_path)],
        )
        if not result.get("success"):
            logger.error(
                "Follow-up letter email to %s failed: %s",
                pi_email,
                result.get("error"),
            )
        else:
            logger.info("Follow-up letter email with PDF sent to %s", pi_email)
    finally:
        try:
            pdf_path.unlink(missing_ok=True)
        except OSError as cleanup_err:
            logger.warning("Failed to remove follow-up PDF %s: %s", pdf_path, cleanup_err)
        try:
            pdf_path.parent.rmdir()
        except OSError as cleanup_err:
            logger.warning("Failed to rmdir %s: %s", pdf_path.parent, cleanup_err)


class FollowUpLetterSendBody(BaseModel):
    pi_email: str = Field(..., min_length=1)
    pi_name: str = ""
    cra_name: str = ""
    form: Dict[str, Any] = Field(default_factory=dict)
    areas: List[Dict[str, Any]] = Field(default_factory=list)
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(default_factory=list)


@router.post("/visits/{visit_id}/send-follow-up-letter")
async def send_follow_up_letter(
    visit_id: str,
    body: FollowUpLetterSendBody,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Build the follow-up letter PDF in-memory with reportlab (~100 ms), persist
    the acknowledgment token, then dispatch the email in a background task so
    the API returns immediately. Replaces the old DOCX→LibreOffice→PDF flow,
    which had a 5–15 s cold start per request.
    """
    import secrets
    import tempfile
    from pathlib import Path

    await _ensure_monitor_tables(db)
    await _ensure_follow_up_delivery_columns(db)
    await _require_monitoring_visit(db, visit_id)

    pi_email = (body.pi_email or "").strip()
    if not pi_email or "@" not in pi_email:
        raise HTTPException(status_code=400, detail="A valid pi_email is required")

    # Reject if the site already received or acknowledged a previously sent letter.
    existing_ack = await db.execute(
        text("SELECT ack_status, last_sent, delivery_status FROM monitoring_follow_up_letters WHERE visit_id = :visit_id"),
        {"visit_id": visit_id},
    )
    existing_ack_row = existing_ack.mappings().first()
    if existing_ack_row and str(existing_ack_row.get("ack_status") or "").lower() == "acknowledged":
        raise HTTPException(
            status_code=409,
            detail="Follow-up letter has been acknowledged by the site and is locked.",
        )
    if existing_ack_row:
        delivery_status = str(existing_ack_row.get("delivery_status") or "").strip().lower()
        last_sent = str(existing_ack_row.get("last_sent") or "").strip()
        if last_sent or delivery_status in {"queued", "sent", "delivered"}:
            raise HTTPException(
                status_code=409,
                detail="Follow-up letter has already been sent to the site.",
            )

    greeting_name = (body.pi_name or "").strip() or "Principal Investigator"
    sender_name   = (body.cra_name or "").strip() or "The Monitoring Team"

    # ── 1. Build PDF directly with reportlab (fast, no subprocess) ──────────
    tmp_dir = Path(tempfile.mkdtemp(prefix="followup_"))
    tmp_pdf = tmp_dir / "FollowUpLetter.pdf"
    try:
        summary_findings = await _load_follow_up_summary_findings_from_visit_tab(db, visit_id)
        if not summary_findings:
            summary_findings = [
                {
                    "subject": "",
                    "description": "No findings recorded on the Visit Findings tab for this visit.",
                    "category": "",
                    "severity": "",
                    "reference": "",
                }
            ]
        await asyncio.to_thread(
            _build_follow_up_letter_pdf,
            {
                "form": body.form or {},
                "areas": body.areas or [],
                "findings": summary_findings,
            },
            tmp_pdf,
        )
    except Exception as build_err:
        logger.error("Follow-up PDF generation failed for visit %s: %s", sfmt(visit_id), build_err, exc_info=True)
        # Cleanup on failure so we don't leak temp files.
        try:
            tmp_pdf.unlink(missing_ok=True)
        except OSError as cleanup_err:
            logger.warning("Failed to remove temp PDF %s: %s", tmp_pdf, cleanup_err)
        try:
            tmp_dir.rmdir()
        except OSError as cleanup_err:
            logger.warning("Failed to rmdir %s: %s", tmp_dir, cleanup_err)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {type(build_err).__name__}: {build_err}")

    if not tmp_pdf.exists():
        try:
            tmp_dir.rmdir()
        except OSError as cleanup_err:
            logger.warning("Failed to rmdir %s: %s", tmp_dir, cleanup_err)
        raise HTTPException(status_code=500, detail="PDF file was not produced")

    # ── 2. Generate magic-link acknowledgment token + persist (sync) ────────
    ack_token = secrets.token_urlsafe(32)
    frontend_base = (
        getattr(settings, "frontend_base_url", None) or "http://localhost:3000"
    ).strip().rstrip("/")
    magic_link = f"{frontend_base}/acknowledge?token={ack_token}"

    sent_at = datetime.now(timezone.utc).strftime("%b %d, %Y %I:%M %p UTC")
    await db.execute(
        text(
            """
            INSERT INTO monitoring_follow_up_letters (visit_id, content, ack_token, ack_status, last_sent, delivery_status, updated_at)
            VALUES (:visit_id, '', :token, 'pending', :last_sent, 'Queued', CURRENT_TIMESTAMP)
            ON CONFLICT (visit_id)
            DO UPDATE SET
                ack_token  = EXCLUDED.ack_token,
                ack_status = 'pending',
                last_sent = EXCLUDED.last_sent,
                delivery_status = EXCLUDED.delivery_status,
                acknowledged_at = NULL,
                updated_at = CURRENT_TIMESTAMP;
            """
        ),
        {"visit_id": visit_id, "token": ack_token, "last_sent": sent_at},
    )
    await _append_visit_activity(db, visit_id, f"Follow-up letter queued for delivery to {pi_email}")
    await db.commit()

    # ── 3. Dispatch email in background; API returns immediately ────────────
    background_tasks.add_task(
        _send_follow_up_letter_email_blocking,
        pi_email,
        greeting_name,
        sender_name,
        tmp_pdf,
        magic_link,
    )

    return {"status": "queued", "recipient": pi_email, "last_sent": sent_at, "delivery_status": "Queued"}


# ── Visit Closure ─────────────────────────────────────────────────────────────

