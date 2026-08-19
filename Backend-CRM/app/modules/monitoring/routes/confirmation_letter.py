"""REST API: confirmation_letter cluster (Phase 2.2 extract).

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
import tempfile
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
from app.utils.log_sanitize import sfmt
from app.modules.monitoring.confirmation_letter_html import build_confirmation_letter_html

logger = logging.getLogger(__name__)
router = APIRouter(tags=["monitor"])

# Pull legacy helpers + body schemas from the parent router.
from app.modules.monitoring.aggregator import (  # noqa: E402
    _append_visit_activity,
    _build_visit_confirmation_token,
    _build_visit_date_fields_from_date_and_time,
    _decode_visit_confirmation_token,
    _effective_visit_schedule_from_row,
    _ensure_monitor_tables,
    _format_utc_label_from_iso,
    _visit_label_from_site_number,
    _rewrite_visit_id_in_text,
    _require_monitoring_visit,
    _rewrite_visit_id_in_text,
    _visit_label_from_site_number,
)


@router.get("/visits/{visit_id}/confirmation-letter")
async def get_confirmation_letter(visit_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    row = await db.execute(
        text(
            "SELECT content, last_sent, delivery_status, confirmed_at, confirmed_by_role, confirmed_by_name "
            "FROM monitoring_confirmation_letters WHERE visit_id = :visit_id"
        ),
        {"visit_id": visit_id},
    )
    letter = row.mappings().first()
    if not letter:
        # Avoid 404 noise when no draft exists yet — frontend expects JSON shape + default UI state.
        return {
            "content": "",
            "last_sent": None,
            "delivery_status": None,
            "confirmed_at": None,
            "confirmed_by_role": None,
            "confirmed_by_name": None,
        }
    out = dict(letter)
    ca = out.get("confirmed_at")
    if ca is not None and hasattr(ca, "isoformat"):
        out["confirmed_at"] = ca.isoformat()
    return out


@router.put("/visits/{visit_id}/confirmation-letter")
async def save_confirmation_letter(visit_id: str, payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    content = str(payload.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    await db.execute(
        text(
            """
            INSERT INTO monitoring_confirmation_letters (visit_id, content, last_sent, delivery_status, updated_at)
            VALUES (:visit_id, :content, :last_sent, 'Draft', CURRENT_TIMESTAMP)
            ON CONFLICT (visit_id)
            DO UPDATE SET content = EXCLUDED.content, updated_at = CURRENT_TIMESTAMP;
            """
        ),
        {"visit_id": visit_id, "content": content, "last_sent": datetime.now(timezone.utc).strftime("%b %d, %Y")},
    )
    await db.commit()
    return {"status": "saved"}


_DEFAULT_CONFIRMATION_LETTER_TEMPLATE = "\n".join([
    "Date: ${System.CurrentDate}",
    "",
    "To: Principal Investigator: ${Site.PI_Title} ${Site.PI_FirstName} ${Site.PI_LastName}",
    "Site Number: ${Site.SiteId}",
    "Institution/Site Name: ${Site.siteName}",
    "Address: ${Site.Address}",
    "CC: ${Site.CRC_FullName}, ${Site.CRC_Title}",
    "",
    "Protocol Number: ${Study.ProtocolID}",
    "Protocol Title: ${Study.ProtocolTitle}",
    "",
    "Dear Dr. ${Site.PI_LastName} and Study Team,",
    "",
    "The purpose of this letter is to formally confirm the upcoming ${Visit.Type} for the above-referenced protocol. The visit will be conducted ${Visit.Method} by your assigned Clinical Research Associate (CRA), ${CRA.FullName}.",
    "",
    "1) Visit Logistics",
    "• Date(s) of Visit: ${Visit.StartDate} to ${Visit.EndDate}",
    "• Expected Arrival Time: ${Visit.ExpectedArrival}",
    "• Expected Departure Time: ${Visit.ExpectedDeparture}",
    "• Facility Access Required: ${Visit.FacilityAccessRequired}",
    "",
    "2) Personnel Availability",
    "To ensure a productive visit and timely resolution of queries, please ensure the following staff are available:",
    "• Study Coordinator (CRC): Available throughout the visit to assist with data queries and document retrieval.",
    "• Principal Investigator (PI): A brief meeting is requested on ${Visit.PIMeetingDate} at ${Visit.PIMeetingTime} to discuss overall site performance.",
    "{% if Visit.RequiresPharmacyReview == true %}",
    "• Pharmacist / Unblinded Personnel: A brief meeting is requested on ${Visit.PharmacyMeetingDate} at ${Visit.PharmacyMeetingTime} for Investigational Product (IP) accountability.",
    "{% endif %}",
    "",
    "3) Visit Agenda and Objectives",
    "During this visit, the CRA will review the following critical study components in accordance with the Clinical Monitoring Plan (CMP):",
    "• Informed Consent Forms (ICFs): Verification of 100% of newly signed ICFs for subjects enrolled since the last visit.",
    "• Source Data Verification/Review (SDV/SDR): Review of source documents against EDC entries for the following subjects:",
    "• Safety & Pharmacovigilance: Review of all new and ongoing Adverse Events (AEs) and Serious Adverse Events (SAEs).",
    "{% if Visit.RequiresPharmacyReview == true %}",
    "• Investigational Product (IP): Physical inventory check, review of temperature logs, and reconciliation of dispensation/return records.",
    "{% endif %}",
    "• Investigator Site File (ISF): Review of the regulatory binder, including the DOA log and updated CVs/Licenses.",
    "• Action Items: Follow-up on ${ActionItems.OpenCount} outstanding issues and ${EDC.OpenQueriesCount} open EDC queries from previous visits.",
    "",
    "4) Pre-Visit Preparation",
    "To maximize efficiency, please ensure the following are completed prior to the CRA's arrival:",
    "• All subject data up to the cut-off date of ${Visit.DataCutOffDate} is entered into the EDC.",
    "• All outstanding EDC queries are addressed.",
    "• Source documents are organized and accessible.",
    "",
    "Acknowledgment",
    "Please log into the Investigator Portal to acknowledge and confirm the proposed dates, times, and agenda.",
    "",
    "Sincerely,",
    "",
    "${CRA.FullName}",
    "${CRA.Title}",
    "${Sponsor_Name}",
    "${CRA.Email} | ${CRA.Phone}",
])


def _parse_letter_visit_datetime(raw: str):
    """Parse visit date string like 'May 02, 2026 · 1:20 PM' into a datetime object."""
    s = (raw or "").strip()
    if not s or s.upper() == "TBD":
        return None
    normalized = re.sub(r"\s+", " ", s.replace("·", " ")).strip()
    for fmt in (
        "%b %d, %Y %I:%M %p",
        "%B %d, %Y %I:%M %p",
        "%b %d, %Y %I:%M%p",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def _parse_letter_duration_hours(raw: str) -> float:
    s = (raw or "").lower().strip()
    if not s:
        return 8.0
    range_m = re.search(r"(\d++(?:\.\d++)?)\s*+-\s*+(\d++(?:\.\d++)?)\s*+hours?", s)
    if range_m:
        return (float(range_m.group(1)) + float(range_m.group(2))) / 2.0
    one_m = re.search(r"(\d++(?:\.\d++)?)\s*+hours?", s)
    if one_m:
        return float(one_m.group(1))
    if "half day" in s:
        return 4.0
    if "full day" in s:
        return 8.0
    return 8.0


def _date_only_from_display(raw: str) -> str:
    s = str(raw or "").strip()
    if not s or s.upper() == "TBD":
        return s or "TBD"
    if "·" in s:
        return s.split("·", 1)[0].strip()
    return s


def _build_letter_values(visit: Any, profile_row: Any, today_str: str) -> dict:
    """Build the token → value map for rendering the confirmation letter template."""
    from datetime import timedelta

    def _p(*vals: Any, default: str = "N/A") -> str:
        for v in vals:
            sv = str(v or "").strip()
            if sv and sv.lower() not in ("none", "null"):
                return sv
        return default

    visit_type = _p(visit.get("visit_type"), default="Monitoring Visit")
    schedule = _effective_visit_schedule_from_row(dict(visit))
    visit_date_raw = _p(schedule.get("visitDate"), visit.get("visit_date"), default="TBD")
    visit_date_iso = _p(schedule.get("visitDateIso"), visit.get("visit_date_iso"), default="")
    visit_end_date_raw = _p(schedule.get("endDate"), visit.get("visit_end_date"), default="")
    visit_end_date_iso = _p(schedule.get("endDateIso"), visit.get("visit_end_date_iso"), default="")
    duration_raw = _p(visit.get("duration"), default="")
    visit_method = "remotely" if re.search(r"remote", visit_type, re.IGNORECASE) else "on-site"
    requires_pharmacy = bool(re.search(r"on-?site", visit_type, re.IGNORECASE))

    start_dt = None
    if visit_date_iso:
        try:
            start_dt = datetime.fromisoformat(visit_date_iso.replace("Z", "+00:00"))
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            start_dt = None
    if start_dt is None:
        start_dt = _parse_letter_visit_datetime(visit_date_raw)
    duration_hours = _parse_letter_duration_hours(duration_raw)
    explicit_end_dt = None
    if visit_end_date_iso:
        try:
            explicit_end_dt = datetime.fromisoformat(visit_end_date_iso.replace("Z", "+00:00"))
        except ValueError:
            explicit_end_dt = None
    if explicit_end_dt is None and visit_end_date_raw:
        explicit_end_dt = _parse_letter_visit_datetime(visit_end_date_raw)

    if start_dt:
        # Prefer explicit end date/time from the visit form. If missing, fall back to duration.
        depart_dt = explicit_end_dt or (start_dt + timedelta(hours=duration_hours))
        start_stamp = start_dt.strftime("%b %d, %Y")
        end_stamp = depart_dt.strftime("%b %d, %Y")
        arrival_time = start_dt.strftime("%I:%M %p")
        departure_time = depart_dt.strftime("%I:%M %p")
    else:
        start_stamp = _date_only_from_display(visit_date_raw)
        end_stamp = _date_only_from_display(visit_end_date_raw or visit_date_raw)
        arrival_time = "TBD"
        departure_time = explicit_end_dt.strftime("%I:%M %p") if explicit_end_dt else "TBD"

    pi_full = _p(
        profile_row.get("pi_name") if profile_row else None,
        visit.get("principal_investigator"),
    )
    pi_parts = pi_full.split() if pi_full and pi_full != "N/A" else []
    pi_first = pi_parts[0] if pi_parts else "N/A"
    pi_last = pi_parts[-1] if len(pi_parts) > 1 else (pi_parts[0] if pi_parts else "N/A")

    crc_full = _p(
        profile_row.get("site_coordinator_name") if profile_row else None,
        visit.get("study_coordinator"),
    )

    address_parts: list = []
    if profile_row:
        for key in ("address_line_1", "city", "state", "postal_code", "country"):
            val = profile_row.get(key)
            if val and str(val).strip():
                address_parts.append(str(val).strip())
    profile_address = ", ".join(address_parts) if address_parts else _p(visit.get("site_address"))

    institution = _p(
        profile_row.get("site_name") if profile_row else None,
        visit.get("site_id"),
    )
    # Use the human-readable site_id from the sites table JOIN, fall back to FK
    site_id_display = _p(
        visit.get("human_site_id"),
        visit.get("site_id"),
    )

    cra_full = _p(visit.get("cra_name"), default="N/A")
    cra_email = _p(visit.get("cra_email"), default="N/A")
    sponsor = _p(visit.get("sponsor"))
    protocol = _p(visit.get("protocol"))
    action_count = str(visit.get("action_required_count") or 0)

    return {
        "_requires_pharmacy": requires_pharmacy,
        "System.CurrentDate": today_str,
        "Site.PI_Title": "Dr.",
        "Site.PI_FirstName": pi_first,
        "Site.PI_LastName": pi_last,
        "Site.SiteId": site_id_display,
        "Site.SiteNumber": site_id_display,
        "Site.siteName": institution,
        "Site.InstitutionName": institution,
        "Site.Address": profile_address,
        "Site.CRC_FullName": crc_full,
        "Site.CRC_Title": "Study Coordinator",
        "Study.ProtocolID": protocol,
        "Study.ProtocolTitle": protocol,
        "Visit.Type": visit_type,
        "Visit.Method": visit_method,
        "Visit.StartDate": start_stamp,
        "Visit.EndDate": end_stamp,
        "Visit.ExpectedArrival": arrival_time,
        "Visit.ExpectedDeparture": departure_time,
        "Visit.FacilityAccessRequired": "Yes",
        "Visit.PIMeetingDate": start_dt.strftime("%B %d, %Y") if start_dt else "TBD",
        "Visit.PIMeetingTime": "4:30 PM",
        "Visit.PharmacyMeetingDate": start_dt.strftime("%B %d, %Y") if start_dt else "TBD",
        "Visit.PharmacyMeetingTime": "2:30 PM",
        "Visit.DataCutOffDate": start_dt.strftime("%B %d, %Y") if start_dt else "TBD",
        "TargetedSubjects.List": "N/A",
        "ActionItems.OpenCount": action_count,
        "EDC.OpenQueriesCount": "N/A",
        "CRA.FullName": cra_full,
        "CRA.Title": "Clinical Research Associate",
        "CRA.SignatureImage": "[Signature]",
        "Sponsor_Name": sponsor,
        "CRA.Email": cra_email,
        "CRA.Phone": "N/A",
    }


def _render_letter_template(template: str, values: dict) -> str:
    """Render ${...} tokens and {% if %}...{% endif %} blocks in the letter template."""
    requires_pharmacy = bool(values.get("_requires_pharmacy", False))

    def _handle_if(m: re.Match) -> str:
        return m.group(1) if requires_pharmacy else ""

    out = re.sub(
        r"\{%\s*if\s+Visit\.RequiresPharmacyReview\s*==\s*true\s*%\}([\s\S]*?)\{%\s*endif\s*%\}",
        _handle_if,
        template,
    )
    targeted_subjects = str(values.get("TargetedSubjects.List") or "").strip()
    if not targeted_subjects or targeted_subjects.upper() == "N/A":
        out = "\n".join(
            line for line in out.splitlines() if "${TargetedSubjects.List}" not in line
        )

    def _replace_token(m: re.Match) -> str:
        key = m.group(1).strip()
        return values.get(key, f"${{{key}}}")

    return re.sub(r"\$\{([^}]+)\}", _replace_token, out)


def _send_confirmation_copy_emails_with_attachment(
    *,
    recipients: List[Dict[str, str]],
    subject: str,
    pdf_path: Path,
) -> None:
    """Send the official confirmation copy while the temporary PDF still exists."""
    try:
        if not pdf_path.is_file():
            logger.error("Site-confirmed confirmation letter PDF missing before send: %s", pdf_path)
            return
        from_email = settings.smtp_user or "noreply@dizzaroo.com"
        for recipient in recipients:
            body_html = f"""
<div style="font-family:Arial,sans-serif;line-height:1.5;color:#111">
  <p>Hi {html.escape(recipient['name'])},</p>
  <p>
    The monitoring visit details are now confirmed.
  </p>
  <p>
    Please find attached the Monitoring Visit Confirmation Letter for your records.
  </p>
</div>
            """.strip()
            result = smtp_service.send_email(
                to=recipient["email"],
                subject=subject,
                body=body_html,
                from_email=from_email,
                from_name="Dizzaroo CRM Monitoring",
                html=True,
                attachments=[str(pdf_path)],
            )
            if not result.get("success"):
                logger.error(
                    "Site confirmation copy email with attachment to %s failed: %s",
                    recipient.get("email"),
                    result.get("error"),
                )
    finally:
        try:
            pdf_path.unlink(missing_ok=True)
        except OSError as cleanup_err:
            logger.warning("Failed to remove site confirmation PDF %s: %s", pdf_path, cleanup_err)
        try:
            pdf_path.parent.rmdir()
        except OSError as cleanup_err:
            logger.warning("Failed to rmdir %s: %s", pdf_path.parent, cleanup_err)


@router.post("/visits/{visit_id}/confirmation-letter/send")
async def send_confirmation_letter(
    visit_id: str, payload: Dict[str, Any], db: AsyncSession = Depends(get_db)
):
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)

    visit_res = await db.execute(
        text(
            """
            SELECT
                v.id, v.site_id, v.study_id,
                v.principal_investigator, v.pi_email,
                v.study_coordinator, v.coordinator_phone,
                v.cra_name, v.cra_email,
                v.visit_type, v.visit_date, v.visit_date_iso,
                v.visit_end_date, v.visit_end_date_iso, v.duration,
                v.protocol, v.sponsor, v.site_address,
                v.action_required_count, v.site_visit_number,
                s.site_id AS human_site_id,
                s.name    AS human_site_name
            FROM monitoring_visits v
            LEFT JOIN sites s
                   ON (s.site_id = v.site_id OR CAST(s.id AS TEXT) = v.site_id)
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
                SELECT
                    s.name AS site_name,
                    sp.pi_name, sp.pi_email,
                    sp.site_coordinator_name, sp.site_coordinator_email,
                    sp.site_coordinator_phone,
                    sp.address_line_1, sp.city, sp.state, sp.postal_code, sp.country
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
        default="PI",
    )
    pi_email = _pick(
        profile_row.get("pi_email") if profile_row else None,
        visit.get("pi_email"),
        default="",
    )
    coordinator_name = _pick(
        profile_row.get("site_coordinator_name") if profile_row else None,
        visit.get("study_coordinator"),
        default="Study Coordinator",
    )
    coordinator_email = _pick(
        profile_row.get("site_coordinator_email") if profile_row else None,
        default="",
    )
    if not pi_email or "@" not in pi_email:
        raise HTTPException(status_code=400, detail="PI email is missing for this site")

    # ------------------------------------------------------------------
    # Build the letter body server-side from real DB data so the email
    # always contains fully-resolved values, regardless of what the
    # frontend sent (which may have rendered N/A when overview data
    # hadn't loaded yet on the client).
    # ------------------------------------------------------------------
    today_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    letter_values = _build_letter_values(visit, profile_row, today_str)

    # Prefer the stored raw template (still has ${...} tokens) so user
    # edits are respected; fall back to the canonical default template.
    stored_letter_res = await db.execute(
        text("SELECT content FROM monitoring_confirmation_letters WHERE visit_id = :visit_id"),
        {"visit_id": visit_id},
    )
    stored_letter = stored_letter_res.mappings().first()
    stored_raw = str(stored_letter.get("content", "") if stored_letter else "").strip()

    # If the stored content still contains ${...} tokens use it as the
    # template so custom edits are preserved.  Otherwise fall back to the
    # default template and render fresh from DB values (this handles the
    # case where the letter was "saved" with N/A values from the UI).
    if stored_raw and re.search(r"\$\{[^}]+\}", stored_raw):
        template_to_render = stored_raw
    else:
        template_to_render = _DEFAULT_CONFIRMATION_LETTER_TEMPLATE

    content = _render_letter_template(template_to_render, letter_values)
    if not content.strip():
        raise HTTPException(status_code=400, detail="Confirmation letter content is empty")

    # Strip any leftover DRAFT watermark lines from the server-rendered content.
    cleaned_lines: List[str] = []
    for line in content.splitlines():
        compact = line.strip().lower().replace("*", "").replace("-", "")
        if compact in {"draft", "watermarkdraft", "draftwatermark"}:
            continue
        cleaned_lines.append(line)
    sanitized_content = re.sub(r"\bDRAFT\b", "", "\n".join(cleaned_lines), flags=re.IGNORECASE).strip()
    if not sanitized_content:
        raise HTTPException(status_code=400, detail="Confirmation letter content is empty after cleanup")

    visit_label = _visit_label_from_site_number(visit.get("site_visit_number"), str(visit.get("id") or visit_id))
    email_letter_body = _rewrite_visit_id_in_text(
        sanitized_content, str(visit.get("id") or visit_id), visit.get("site_visit_number")
    )

    pi_confirm_token = _build_visit_confirmation_token(visit_id, actor_role="pi")
    coordinator_confirm_token = _build_visit_confirmation_token(visit_id, actor_role="coordinator")
    public_base = (settings.backend_public_url or "").strip().rstrip("/")
    internal_base = (settings.backend_internal_url or "").strip().rstrip("/")
    # Never send Docker-internal hostnames (e.g. http://backend:8000) in user-facing emails.
    if public_base:
        backend_base_url = public_base
    elif internal_base and "://backend" not in internal_base:
        backend_base_url = internal_base
    else:
        backend_base_url = "http://localhost:8000"
    pi_confirm_link = (
        f"{backend_base_url}/api/monitor/visits/{visit_id}/confirmation-letter/confirm"
        f"?token={pi_confirm_token}"
    )
    coordinator_confirm_link = (
        f"{backend_base_url}/api/monitor/visits/{visit_id}/confirmation-letter/confirm"
        f"?token={coordinator_confirm_token}"
    )
    frontend_base = (settings.frontend_base_url or "http://localhost:3000").strip().rstrip("/")
    pi_reschedule_link = f"{frontend_base}/monitoring/visits/{visit_id}/reschedule?token={quote(pi_confirm_token, safe='')}"
    coordinator_reschedule_link = (
        f"{frontend_base}/monitoring/visits/{visit_id}/reschedule?token={quote(coordinator_confirm_token, safe='')}"
    )

    def _build_html_body(confirm_link: str, reschedule_link: str) -> str:
        letter_html = build_confirmation_letter_html(email_letter_body, compact=True)
        return f"""
<div style="font-family:Arial,Helvetica,sans-serif;line-height:1.5;color:#111827;background:#ffffff;">
  {letter_html}
  <div style="margin-top:28px;margin-bottom:12px;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
      <td style="padding-right:10px;vertical-align:middle">
        <a href="{confirm_link}"
           style="display:inline-block;padding:12px 18px;background:#0f62fe;color:#ffffff;text-decoration:none;border-radius:6px;font-weight:600">
          Confirm Visit Details
        </a>
      </td>
      <td style="vertical-align:middle">
        <a href="{reschedule_link}"
           style="display:inline-block;padding:12px 18px;background:#ffffff;color:#0f62fe;text-decoration:none;border-radius:6px;font-weight:600;border:2px solid #0f62fe">
          Request Reschedule
        </a>
      </td>
    </tr></table>
  </div>
  <p style="font-size:12px;color:#64748b;margin-top:16px;">If the buttons do not work, use these links:<br/>
  <strong>Confirm:</strong><br/>{confirm_link}<br/><br/>
  <strong>Request reschedule:</strong><br/>{reschedule_link}</p>
</div>
        """.strip()

    subject = f"Monitoring Visit Confirmation — {visit_label}"
    from_email = settings.smtp_user or "noreply@dizzaroo.com"
    recipients: List[Dict[str, str]] = [
        {
            "role": "pi",
            "name": pi_name,
            "email": pi_email,
            "link": pi_confirm_link,
            "reschedule": pi_reschedule_link,
        },
    ]
    if coordinator_email and "@" in coordinator_email:
        recipients.append(
            {
                "role": "coordinator",
                "name": coordinator_name,
                "email": coordinator_email,
                "link": coordinator_confirm_link,
                "reschedule": coordinator_reschedule_link,
            }
        )
    raw_cc_emails = str(payload.get("cc_emails", "") or "").strip()
    cc_emails_for_storage: List[str] = []
    if raw_cc_emails:
        cc_candidates = [item.strip() for item in re.split(r"[;,]", raw_cc_emails) if item.strip()]
        existing_emails = {str(recipient["email"]).strip().lower() for recipient in recipients}
        for cc_email in cc_candidates:
            email_norm = cc_email.lower()
            if "@" not in cc_email or email_norm in existing_emails:
                continue
            recipients.append(
                {
                    "role": "cc",
                    "name": cc_email,
                    "email": cc_email,
                    "link": pi_confirm_link,
                    "reschedule": pi_reschedule_link,
                }
            )
            existing_emails.add(email_norm)
            cc_emails_for_storage.append(cc_email)

    # Behavior change: emails are now enqueued to Celery rather than sent
    # inline. The old path blocked this route for N×(1-5s) per recipient and
    # returned a 502 on the first SMTP error. Now the route returns instantly
    # and the worker retries each email independently (autoretry_for +
    # exponential backoff in send_email_task). If you need user-visible
    # delivery status, observe the Celery results in the worker logs or
    # expose a per-task /status endpoint.
    for r in recipients:
        enqueue_email(
            to=r["email"],
            subject=subject,
            body=_build_html_body(r["link"], r["reschedule"]),
            from_email=from_email,
            from_name="Dizzaroo CRM Monitoring",
            html=True,
        )

    last_sent = datetime.now(timezone.utc).strftime("%b %d, %Y %I:%M %p UTC")
    await db.execute(
        text(
            """
            INSERT INTO monitoring_confirmation_letters
                (visit_id, content, cc_emails, last_sent, delivery_status, updated_at)
            VALUES
                (:visit_id, :content, :cc_emails, :last_sent, 'Delivered', CURRENT_TIMESTAMP)
            ON CONFLICT (visit_id)
            DO UPDATE SET
                content = EXCLUDED.content,
                cc_emails = EXCLUDED.cc_emails,
                last_sent = EXCLUDED.last_sent,
                delivery_status = EXCLUDED.delivery_status,
                -- Reset confirmation state so both PI and coordinator can confirm fresh
                confirmed_by_role = '',
                confirmed_by_name = '',
                confirmed_by_email = '',
                confirmed_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "visit_id": visit_id,
            "content": sanitized_content,
            "cc_emails": ", ".join(cc_emails_for_storage),
            "last_sent": last_sent,
        },
    )
    recipient_roles = {"pi": "PI", "coordinator": "Study Coordinator", "cc": "CC recipients"}
    role_counts: Dict[str, int] = {}
    for recipient in recipients:
        role = str(recipient.get("role") or "")
        role_counts[role] = role_counts.get(role, 0) + 1
    role_labels = []
    for key in ("pi", "coordinator", "cc"):
        if role_counts.get(key, 0):
            label = recipient_roles.get(key, key)
            count = role_counts[key]
            role_labels.append(f"{label}{f' ({count})' if key == 'cc' else ''}")
    await _append_visit_activity(
        db,
        visit_id,
        f"Confirmation Letter for {visit_label} dispatched to {', '.join(role_labels)}.",
    )
    await db.commit()

    return {
        "status": "sent",
        "recipient_name": pi_name,
        "recipient_email": pi_email,
        "recipients": [{"role": r["role"], "name": r["name"], "email": r["email"]} for r in recipients],
        "last_sent": last_sent,
        "delivery_status": "Delivered",
    }


class ConfirmationCalendarEvent(BaseModel):
    title: str
    start_utc: str
    end_utc: str
    location: str
    description: str


class VisitConfirmationDataResponse(BaseModel):
    status: str  # "confirmed" | "already_confirmed"
    actor_role: str
    actor_label: str
    confirmed_by_name: str
    visit_label: str
    event: ConfirmationCalendarEvent


@router.get("/visits/{visit_id}/confirmation-letter/confirm-data", response_model=VisitConfirmationDataResponse)
async def get_visit_confirmation_data(
    visit_id: str,
    background_tasks: BackgroundTasks,
    token: str = "",
    db: AsyncSession = Depends(get_db),
):
    """
    Called by the React confirmation page.
    1) Validates the token.
    2) Marks the visit confirmed in the DB (idempotent — duplicate clicks return 'already_confirmed').
    3) Returns calendar-ready event data so the UI can offer 'Add to Google Calendar' / Download .ics.
    """
    await _ensure_monitor_tables(db)

    token_data = _decode_visit_confirmation_token(token, visit_id) if token else None
    if not token_data:
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation link")

    actor_role = str(token_data.get("actor_role") or "pi")
    actor_label = "Principal Investigator" if actor_role == "pi" else "Study Coordinator"

    # Fetch full visit + site profile in one JOIN for calendar event data
    visit_res = await db.execute(
        text(
            """
            SELECT
                v.id, v.visit_type, v.visit_date, v.visit_date_iso,
                v.visit_end_date, v.visit_end_date_iso,
                v.duration, v.protocol, v.sponsor, v.cra_name,
                v.principal_investigator, v.study_coordinator,
                v.pi_email, v.site_address, v.action_required_count,
                v.status, v.site_visit_number,
                s.site_id   AS human_site_id,
                s.name      AS site_name,
                sp.pi_name, sp.pi_email  AS sp_pi_email,
                sp.site_coordinator_name, sp.site_coordinator_email,
                sp.address_line_1, sp.city, sp.state, sp.postal_code, sp.country
            FROM monitoring_visits v
            LEFT JOIN sites s
                   ON (s.site_id = v.site_id OR CAST(s.id AS TEXT) = v.site_id)
            LEFT JOIN site_profiles sp ON sp.site_id = s.id
            WHERE v.id = :visit_id
            """
        ),
        {"visit_id": visit_id},
    )
    visit = visit_res.mappings().first()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")

    def _p(*vals: Any, default: str = "") -> str:
        for v in vals:
            sv = str(v or "").strip()
            if sv and sv.lower() not in ("none", "null"):
                return sv
        return default

    visit_status_now = str(visit.get("status") or "").strip().lower()

    # ── State-machine guard ────────────────────────────────────────────────────
    # Once the site has requested a reschedule, the confirm link from that same
    # email is considered consumed.  Return 409 so the frontend can show a
    # user-friendly "link no longer valid" screen instead of silently overwriting
    # the reschedule state.
    if visit_status_now in {"reschedule requested", "rescheduled"}:
        raise HTTPException(
            status_code=409,
            detail=(
                "This visit already has a pending reschedule request. "
                "The confirmation link from this email is no longer valid. "
                "If you still wish to confirm, please contact your assigned monitor."
            ),
        )
    if visit_status_now == "cancelled":
        raise HTTPException(
            status_code=409,
            detail="This visit has been cancelled and can no longer be confirmed.",
        )

    # Check if the same role already confirmed (idempotent — duplicate click)
    letter_res = await db.execute(
        text(
            """
            SELECT confirmed_by_role, COALESCE(cc_emails, '') AS cc_emails
            FROM monitoring_confirmation_letters
            WHERE visit_id = :visit_id
            """
        ),
        {"visit_id": visit_id},
    )
    letter_row = letter_res.mappings().first()
    existing_role = (letter_row.get("confirmed_by_role") if letter_row else "") or ""
    already_confirmed = existing_role == actor_role

    pi_name = _p(visit.get("pi_name"), visit.get("principal_investigator"), default="Principal Investigator")
    coordinator_name = _p(visit.get("site_coordinator_name"), visit.get("study_coordinator"), default="Study Coordinator")
    confirmed_by_name = pi_name if actor_role == "pi" else coordinator_name
    confirmed_by_email = (
        _p(visit.get("sp_pi_email"), visit.get("pi_email"))
        if actor_role == "pi"
        else _p(visit.get("site_coordinator_email"))
    )

    if not already_confirmed:
        await db.execute(
            text(
                "UPDATE monitoring_visits SET status = 'site confirmed', updated_at = CURRENT_TIMESTAMP "
                "WHERE id = :visit_id"
            ),
            {"visit_id": visit_id},
        )
        await db.execute(
            text(
                """
                INSERT INTO monitoring_confirmation_letters
                    (visit_id, content, delivery_status, confirmed_by_role, confirmed_by_name,
                     confirmed_by_email, confirmed_at, updated_at)
                VALUES
                    (:visit_id, '', 'Delivered', :confirmed_by_role, :confirmed_by_name,
                     :confirmed_by_email, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (visit_id) DO UPDATE SET
                    confirmed_by_role  = EXCLUDED.confirmed_by_role,
                    confirmed_by_name  = EXCLUDED.confirmed_by_name,
                    confirmed_by_email = EXCLUDED.confirmed_by_email,
                    confirmed_at       = EXCLUDED.confirmed_at,
                    updated_at         = CURRENT_TIMESTAMP
                """
            ),
            {
                "visit_id": visit_id,
                "confirmed_by_role": actor_role,
                "confirmed_by_name": confirmed_by_name,
                "confirmed_by_email": confirmed_by_email,
            },
        )
        actor_short = "Principal Investigator" if actor_role == "pi" else "Coordinator"
        await _append_visit_activity(db, visit_id, f"Visit confirmed by {actor_short}.", initials="PI", color="green")
        site_recipients: List[Dict[str, str]] = []
        existing_emails: set[str] = set()

        def _add_site_recipient(name: str, email: str, role: str) -> None:
            email_clean = str(email or "").strip()
            email_key = email_clean.lower()
            if "@" not in email_clean or email_key in existing_emails:
                return
            site_recipients.append(
                {
                    "name": str(name or email_clean).strip() or email_clean,
                    "email": email_clean,
                    "role": role,
                }
            )
            existing_emails.add(email_key)

        _add_site_recipient(pi_name, _p(visit.get("sp_pi_email"), visit.get("pi_email")), "pi")
        _add_site_recipient(coordinator_name, _p(visit.get("site_coordinator_email")), "coordinator")

        cc_raw = str(letter_row.get("cc_emails") if letter_row else "").strip()
        for cc_email in [item.strip() for item in re.split(r"[;,]", cc_raw) if item.strip()]:
            _add_site_recipient(cc_email, cc_email, "cc")

        if site_recipients and background_tasks is not None:
            tmp_dir: Optional[Path] = None
            tmp_pdf: Optional[Path] = None
            try:
                from app.modules.monitoring.routes.reschedule import _build_updated_confirmation_letter_pdf_for_visit

                tmp_dir = Path(tempfile.mkdtemp(prefix="site_confirmation_"))
                tmp_pdf = tmp_dir / "MonitoringVisitConfirmationLetter.pdf"
                await _build_updated_confirmation_letter_pdf_for_visit(db, visit_id, tmp_pdf)
                visit_label_for_subject = _visit_label_from_site_number(
                    visit.get("site_visit_number"),
                    str(visit.get("id") or visit_id),
                )
                background_tasks.add_task(
                    _send_confirmation_copy_emails_with_attachment,
                    recipients=site_recipients,
                    subject=f"Monitoring Visit Confirmation Letter - {visit_label_for_subject}",
                    pdf_path=tmp_pdf,
                )
            except Exception:
                logger.exception("Failed to build site confirmation attachment for visit %s", sfmt(visit_id))
                try:
                    if tmp_pdf is not None:
                        tmp_pdf.unlink(missing_ok=True)
                    if tmp_dir is not None:
                        tmp_dir.rmdir()
                except Exception:
                    pass
        await db.commit()

        # Kafka: a confirmed visit counts as conducted — publish SIV_CONDUCTED /
        # COV_CONDUCTED / SITE_QUALIFICATION_APPROVED depending on visit_type.
        # Best-effort & self-guarded — never breaks the committed confirmation.
        try:
            from app.integrations.milestones_kafka import publish_visit_milestone

            if visit.get("site_id"):
                await publish_visit_milestone(
                    site_id=str(visit.get("site_id")),
                    visit_type=visit.get("visit_type"),
                    phase="conducted",
                )
        except Exception:
            logger.exception(
                "confirm visit: milestone Kafka hook failed for visit %s", sfmt(visit_id)
            )

    # ── Build calendar event data ──────────────────────────────────────────────
    svn = visit.get("site_visit_number")
    visit_label = _visit_label_from_site_number(svn, str(visit.get("id") or visit_id))

    visit_type = _p(visit.get("visit_type"), default="Monitoring Visit")
    protocol = _p(visit.get("protocol"), default="N/A")
    cra_name = _p(visit.get("cra_name"), default="N/A")
    sponsor = _p(visit.get("sponsor"), default="N/A")

    # Location: prefer structured address from site_profiles, fall back to visit field
    address_parts: list = []
    institution = _p(visit.get("site_name"), visit.get("human_site_id"), default="")
    if institution:
        address_parts.append(institution)
    for key in ("address_line_1", "city", "state", "postal_code", "country"):
        val = visit.get(key)
        if val and str(val).strip():
            address_parts.append(str(val).strip())
    location = ", ".join(address_parts) if address_parts else _p(visit.get("site_address"), default="TBD")

    # Parse start time from visit_date_iso (preferred) or display visit_date string
    visit_date_iso = _p(visit.get("visit_date_iso"), default="")
    visit_date_display = _p(visit.get("visit_date"), default="TBD")
    visit_end_date_iso_raw = _p(visit.get("visit_end_date_iso"), default="")
    visit_end_date_display = _p(visit.get("visit_end_date"), default="")
    duration_raw = _p(visit.get("duration"), default="")
    duration_hours = _parse_letter_duration_hours(duration_raw)

    # Try to build proper UTC datetimes for calendar
    from datetime import timedelta
    start_dt = None
    if visit_date_iso:
        try:
            start_dt = datetime.fromisoformat(visit_date_iso.replace("Z", "+00:00"))
        except ValueError:
            pass
    if start_dt is None:
        start_dt = _parse_letter_visit_datetime(visit_date_display)

    # Resolve explicit end datetime from saved fields; fall back to duration-based estimate
    end_dt = None
    if visit_end_date_iso_raw:
        try:
            end_dt = datetime.fromisoformat(visit_end_date_iso_raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    if end_dt is None and visit_end_date_display:
        end_dt = _parse_letter_visit_datetime(visit_end_date_display)

    if start_dt:
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt is None:
            end_dt = start_dt + timedelta(hours=duration_hours)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        start_utc = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_utc = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        # Fallback: placeholder times (today 09:00–17:00 UTC)
        today = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
        start_utc = today.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_utc = (today + timedelta(hours=duration_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

    event_title = f"{visit_type} — Protocol {protocol}"
    event_description = (
        f"Clinical Research Associate: {cra_name}. "
        f"Sponsor: {sponsor}. "
        f"Confirmed by: {confirmed_by_name}. "
        "Please log into the Investigator Portal for the full visit agenda."
    )

    return VisitConfirmationDataResponse(
        status="already_confirmed" if already_confirmed else "confirmed",
        actor_role=actor_role,
        actor_label=actor_label,
        confirmed_by_name=confirmed_by_name,
        visit_label=visit_label,
        event=ConfirmationCalendarEvent(
            title=event_title,
            start_utc=start_utc,
            end_utc=end_utc,
            location=location,
            description=event_description,
        ),
    )


@router.get("/visits/{visit_id}/confirmation-letter/confirm")
async def confirm_visit_from_email(visit_id: str, token: str = ""):
    """
    Legacy email link handler — redirects to the React confirmation page.
    The React page calls /confirm-data to perform the actual DB update and
    receive calendar event data. This keeps the email links backward-compatible.
    """
    frontend_base = (settings.frontend_base_url or "http://localhost:3000").strip().rstrip("/")
    encoded_token = quote(token, safe="")
    redirect_url = f"{frontend_base}/monitoring/visits/{visit_id}/confirm?token={encoded_token}"
    return RedirectResponse(url=redirect_url, status_code=302)


