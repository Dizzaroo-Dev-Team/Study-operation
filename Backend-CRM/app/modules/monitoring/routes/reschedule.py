"""REST API: reschedule cluster (Phase 2.2 extract).

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

logger = logging.getLogger(__name__)
router = APIRouter(tags=["monitor"])

# Pull legacy helpers + body schemas from the parent router.
from app.modules.monitoring.aggregator import (  # noqa: E402
    _append_visit_activity,
    _build_visit_date_fields_from_date_and_time,
    _build_visit_confirmation_token,
    _decode_visit_confirmation_token,
    _ensure_monitor_tables,
    _format_utc_label_from_iso,
    _parse_proposed_datetime_iso,
    _require_monitoring_visit,
    _rewrite_visit_id_in_text,
    _visit_label_from_site_number,
    VisitRescheduleDecisionSubmit,
    VisitRescheduleSubmit,
)


def _slot_to_response(slot: Dict[str, str], index: int) -> Dict[str, Any]:
    return {
        "index": index,
        "proposed_datetime_iso": slot["proposed_datetime_iso"],
        "proposed_end_datetime_iso": slot.get("proposed_end_datetime_iso") or None,
    }


def _normalise_reschedule_slots(body: VisitRescheduleSubmit) -> Tuple[List[Dict[str, str]], str, str, datetime, Optional[datetime]]:
    raw_slots = body.proposed_slots or [
        {
            "proposed_datetime_iso": body.proposed_datetime_iso,
            "proposed_end_datetime_iso": body.proposed_end_datetime_iso or "",
        }
    ]
    if not isinstance(raw_slots, list):
        raise HTTPException(status_code=400, detail="proposed_slots must be a list")
    slots: List[Dict[str, str]] = []
    for idx, raw in enumerate(raw_slots[:10], start=1):
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail=f"Proposed slot {idx} is invalid")
        start_raw = str(raw.get("proposed_datetime_iso") or "").strip()
        end_raw = str(raw.get("proposed_end_datetime_iso") or "").strip()
        if not start_raw:
            raise HTTPException(status_code=400, detail=f"Proposed slot {idx} is missing a start date")
        try:
            start_stored = _parse_proposed_datetime_iso(start_raw)
            end_stored = _parse_proposed_datetime_iso(end_raw) if end_raw else ""
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Proposed slot {idx} has an invalid date format")
        start_dt = datetime.fromisoformat(start_stored.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_stored.replace("Z", "+00:00")) if end_stored else None
        if end_dt is not None and end_dt < start_dt:
            raise HTTPException(status_code=400, detail=f"Proposed slot {idx} end must be on or after its start")
        slots.append({
            "proposed_datetime_iso": start_stored,
            "proposed_end_datetime_iso": end_stored,
        })
    if len(slots) < 2:
        raise HTTPException(status_code=400, detail="Please propose at least 2 visit options")
    primary = slots[0]
    primary_start = primary["proposed_datetime_iso"]
    primary_end = primary.get("proposed_end_datetime_iso") or ""
    primary_start_dt = datetime.fromisoformat(primary_start.replace("Z", "+00:00"))
    primary_end_dt = datetime.fromisoformat(primary_end.replace("Z", "+00:00")) if primary_end else None
    return slots, primary_start, primary_end, primary_start_dt, primary_end_dt


def _slots_from_request(req: Any) -> List[Dict[str, str]]:
    raw = req.get("proposed_slots") if hasattr(req, "get") else None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = []
    if isinstance(raw, list):
        slots = []
        for idx, item in enumerate(raw[:3], start=1):
            if not isinstance(item, dict):
                continue
            start = str(item.get("proposed_datetime_iso") or "").strip()
            end = str(item.get("proposed_end_datetime_iso") or "").strip()
            if start:
                slots.append(_slot_to_response({
                    "proposed_datetime_iso": start,
                    "proposed_end_datetime_iso": end,
                }, idx))
        if slots:
            return slots
    proposed = req.get("proposed_date") if hasattr(req, "get") else None
    proposed_end = req.get("proposed_end_date") if hasattr(req, "get") else None
    if proposed is None:
        return []
    if hasattr(proposed, "astimezone"):
        start_iso = proposed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    else:
        start_iso = str(proposed)
    if proposed_end is not None and hasattr(proposed_end, "astimezone"):
        end_iso = proposed_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    else:
        end_iso = str(proposed_end or "")
    return [_slot_to_response({"proposed_datetime_iso": start_iso, "proposed_end_datetime_iso": end_iso}, 1)]


def _build_confirmation_letter_pdf(letter_text: str, pdf_path: Path) -> None:
    """Build a simple official PDF copy of the rendered confirmation letter."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ConfirmationTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        spaceAfter=14,
    )
    body_style = ParagraphStyle(
        "ConfirmationBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        spaceAfter=7,
    )
    header_style = ParagraphStyle(
        "ConfirmationHeader",
        parent=body_style,
        fontName="Helvetica-Bold",
        textColor="#1f2937",
    )
    section_style = ParagraphStyle(
        "ConfirmationSection",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        spaceBefore=8,
        spaceAfter=8,
    )

    def esc(value: str) -> str:
        return html.escape(value or "", quote=False)

    pdf_title = "Monitoring Visit Confirmation Letter"
    story: List[Any] = [Paragraph(pdf_title, title_style)]
    for raw_line in (letter_text or "").replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 0.08 * inch))
            continue
        if re.match(r"^\d+\)\s+", line) or line.lower() == "acknowledgment":
            story.append(Paragraph(esc(line), section_style))
        elif ":" in line and len(line.split(":", 1)[0]) <= 40:
            label, value = line.split(":", 1)
            story.append(Paragraph(f"<b>{esc(label)}:</b>{esc(value)}", header_style))
        elif line.startswith(("•", "-")):
            story.append(Paragraph(f"&bull; {esc(line.lstrip('•- ').strip())}", body_style))
        else:
            story.append(Paragraph(esc(line), body_style))

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=LETTER,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=pdf_title,
    )
    doc.build(story)


def _strip_acknowledgment_section_from_letter(letter_text: str) -> str:
    """Remove action-oriented acknowledgment copy from the informational reschedule attachment."""
    lines = (letter_text or "").replace("\r\n", "\n").split("\n")
    out: List[str] = []
    skipping_ack = False
    for line in lines:
        trimmed = line.strip()
        if re.match(r"^Acknowledgment\s*$", trimmed, re.I):
            skipping_ack = True
            continue
        if skipping_ack and re.match(r"^Sincerely,?\s*$", trimmed, re.I):
            skipping_ack = False
            if out and out[-1].strip():
                out.append("")
            out.append(line)
            continue
        if skipping_ack:
            continue
        out.append(line)
    return "\n".join(out).strip()


def _send_reschedule_acceptance_emails_with_attachment(
    *,
    recipients: List[Dict[str, str]],
    subject: str,
    pdf_path: Path,
) -> None:
    """Send accepted-reschedule emails while the temporary PDF still exists, then clean up."""
    try:
        if not pdf_path.is_file():
            logger.error("Updated confirmation letter PDF missing before send: %s", pdf_path)
            return
        from_email = settings.smtp_user or "noreply@dizzaroo.com"
        for recipient in recipients:
            body_html = recipient.get("body_html") or ""
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
                    "Reschedule acceptance email with attachment to %s failed: %s",
                    recipient.get("email"),
                    result.get("error"),
                )
    finally:
        try:
            pdf_path.unlink(missing_ok=True)
        except OSError as cleanup_err:
            logger.warning("Failed to remove reschedule confirmation PDF %s: %s", pdf_path, cleanup_err)
        try:
            pdf_path.parent.rmdir()
        except OSError as cleanup_err:
            logger.warning("Failed to rmdir %s: %s", pdf_path.parent, cleanup_err)


async def _build_updated_confirmation_letter_pdf_for_visit(
    db: AsyncSession,
    visit_id: str,
    pdf_path: Path,
) -> None:
    """Render the confirmation letter from current visit data and write an official PDF copy."""
    from app.modules.monitoring.routes.confirmation_letter import (
        _DEFAULT_CONFIRMATION_LETTER_TEMPLATE,
        _build_letter_values,
        _render_letter_template,
    )

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
            LIMIT 1
            """
        ),
        {"visit_id": visit_id},
    )
    visit = visit_res.mappings().first()
    if not visit:
        raise RuntimeError("Visit not found while building updated confirmation letter")

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

    stored_letter_res = await db.execute(
        text("SELECT content, cc_emails FROM monitoring_confirmation_letters WHERE visit_id = :visit_id"),
        {"visit_id": visit_id},
    )
    stored_letter = stored_letter_res.mappings().first()
    stored_raw = str(stored_letter.get("content", "") if stored_letter else "").strip()
    template_to_render = (
        stored_raw
        if stored_raw and re.search(r"\$\{[^}]+\}", stored_raw)
        else _DEFAULT_CONFIRMATION_LETTER_TEMPLATE
    )

    today_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    content = _render_letter_template(
        template_to_render,
        _build_letter_values(visit, profile_row, today_str),
    )
    cleaned_lines: List[str] = []
    for line in content.splitlines():
        compact = line.strip().lower().replace("*", "").replace("-", "")
        if compact in {"draft", "watermarkdraft", "draftwatermark"}:
            continue
        cleaned_lines.append(line)
    sanitized_content = re.sub(r"\bDRAFT\b", "", "\n".join(cleaned_lines), flags=re.IGNORECASE).strip()
    sanitized_content = _strip_acknowledgment_section_from_letter(sanitized_content)
    rendered_for_pdf = _rewrite_visit_id_in_text(
        sanitized_content,
        str(visit.get("id") or visit_id),
        visit.get("site_visit_number"),
    )

    if stored_letter:
        await db.execute(
            text(
                """
                UPDATE monitoring_confirmation_letters
                SET content = :content, updated_at = CURRENT_TIMESTAMP
                WHERE visit_id = :visit_id
                """
            ),
            {"visit_id": visit_id, "content": sanitized_content},
        )
    else:
        await db.execute(
            text(
                """
                INSERT INTO monitoring_confirmation_letters
                    (visit_id, content, cc_emails, last_sent, delivery_status, updated_at)
                VALUES
                    (:visit_id, :content, '', '', 'Updated', CURRENT_TIMESTAMP)
                """
            ),
            {"visit_id": visit_id, "content": sanitized_content},
        )

    await asyncio.to_thread(_build_confirmation_letter_pdf, rendered_for_pdf, pdf_path)


@router.get("/visits/{visit_id}/reschedule")
async def get_visit_reschedule_context(
    visit_id: str,
    token: str = "",
    db: AsyncSession = Depends(get_db),
):
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    token_data = _decode_visit_confirmation_token(token, visit_id) if token else None
    if not token_data:
        raise HTTPException(status_code=400, detail="Invalid or expired link")
    visit_res = await db.execute(
        text(
            """
            SELECT id, visit_date, visit_date_iso, visit_end_date, visit_end_date_iso,
                   site_address, status, visit_type, site_visit_number
            FROM monitoring_visits
            WHERE id = :visit_id
            """
        ),
        {"visit_id": visit_id},
    )
    visit = visit_res.mappings().first()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")

    # ── State-machine guard (on page load) ────────────────────────────────────
    # If the visit has already been confirmed or cancelled, this reschedule link
    # is consumed.  Return 409 immediately so the frontend never shows the form.
    status_now_get = str(visit.get("status") or "").strip().lower()
    if status_now_get in {"site confirmed", "confirmed"}:
        raise HTTPException(
            status_code=409,
            detail=(
                "This visit has already been confirmed by the site. "
                "The reschedule link from this email is no longer valid. "
                "If you still need to change the date, please contact your assigned monitor directly."
            ),
        )
    if status_now_get == "cancelled":
        raise HTTPException(
            status_code=409,
            detail="This visit has been cancelled and cannot be rescheduled.",
        )

    actor_role = str(token_data.get("actor_role") or "pi")
    actor_label = "Principal Investigator" if actor_role == "pi" else "Study Coordinator"
    svn_raw = visit.get("site_visit_number")
    site_visit_number: Optional[int]
    try:
        site_visit_number = int(svn_raw) if svn_raw is not None else None
    except (TypeError, ValueError):
        site_visit_number = None
    return {
        "visit": {
            "id": visit["id"],
            "visit_date": str(visit.get("visit_date") or ""),
            "visit_date_iso": str(visit.get("visit_date_iso") or ""),
            "visit_end_date": str(visit.get("visit_end_date") or ""),
            "visit_end_date_iso": str(visit.get("visit_end_date_iso") or ""),
            "location": str(visit.get("site_address") or ""),
            "visit_type": str(visit.get("visit_type") or ""),
            "status": str(visit.get("status") or ""),
            "site_visit_number": site_visit_number,
        },
        "actor_role": actor_role,
        "actor_label": actor_label,
    }


@router.get("/visits/{visit_id}/confirmation-letter/pdf")
async def download_updated_confirmation_letter_pdf(
    visit_id: str,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    tmp_dir = Path(tempfile.mkdtemp(prefix="confirmation_download_"))
    tmp_pdf = tmp_dir / "UpdatedConfirmationLetter.pdf"
    try:
        await _build_updated_confirmation_letter_pdf_for_visit(db, visit_id, tmp_pdf)
        await db.commit()
        pdf_bytes = await asyncio.to_thread(tmp_pdf.read_bytes)
    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to build confirmation letter PDF for visit %s", sfmt(visit_id))
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {type(exc).__name__}")
    finally:
        try:
            tmp_pdf.unlink(missing_ok=True)
        except OSError as cleanup_err:
            logger.warning("Failed to remove confirmation download PDF %s: %s", tmp_pdf, cleanup_err)
        try:
            tmp_dir.rmdir()
        except OSError as cleanup_err:
            logger.warning("Failed to rmdir %s: %s", tmp_dir, cleanup_err)

    filename = f"{visit_id}-confirmation-letter.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/visits/{visit_id}/reschedule")
async def submit_visit_reschedule(
    visit_id: str,
    body: VisitRescheduleSubmit,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    token_data = _decode_visit_confirmation_token(body.token.strip(), visit_id)
    if not token_data:
        raise HTTPException(status_code=400, detail="Invalid or expired link")
    reason = body.reason.strip()
    if len(reason) < 2:
        raise HTTPException(status_code=400, detail="Reason for rescheduling is too short")
    slots, proposed_stored, proposed_end_stored, proposed_dt, proposed_end_dt = _normalise_reschedule_slots(body)

    actor_role = str(token_data.get("actor_role") or "pi")
    visit_res = await db.execute(
        text(
            """
            SELECT id, cra_name, cra_email, visit_date, visit_date_iso, site_address, status, site_visit_number
            FROM monitoring_visits
            WHERE id = :visit_id
            """
        ),
        {"visit_id": visit_id},
    )
    visit = visit_res.mappings().first()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    visit_label = _visit_label_from_site_number(visit.get("site_visit_number"), str(visit.get("id") or visit_id))
    status_now = str(visit.get("status") or "").lower()

    # ── State-machine guard ────────────────────────────────────────────────────
    # Once the site has confirmed, the reschedule link from that same email is
    # consumed.  Return 409 so the frontend renders a clear "link expired" screen.
    if status_now in {"site confirmed", "confirmed"}:
        raise HTTPException(
            status_code=409,
            detail=(
                "This visit has already been confirmed by the site. "
                "The reschedule link from this email is no longer valid. "
                "If you still need to change the date, please contact your assigned monitor directly."
            ),
        )
    if status_now == "cancelled":
        raise HTTPException(status_code=409, detail="This visit has been cancelled and cannot be rescheduled.")

    request_id = str(uuid4())
    try:
        await db.execute(
            text(
                """
                INSERT INTO visit_reschedule_requests (id, visit_id, proposed_date, proposed_end_date, proposed_slots, reason, status, created_at, updated_at)
                VALUES (CAST(:id AS UUID), :visit_id, :proposed_date, :proposed_end_date, CAST(:proposed_slots AS JSONB), :reason, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                "id": request_id,
                "visit_id": visit_id,
                "proposed_date": proposed_dt,
                "proposed_end_date": proposed_end_dt,
                "proposed_slots": json.dumps(slots),
                "reason": reason,
            },
        )
        await db.execute(
            text(
                """
                UPDATE monitoring_visits
                SET
                    status = 'Reschedule Requested',
                    reschedule_proposed_datetime_iso = :proposed,
                    reschedule_proposed_end_datetime_iso = :proposed_end,
                    reschedule_reason = :reason,
                    reschedule_requested_at = CURRENT_TIMESTAMP,
                    reschedule_requested_by_role = :actor_role,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :visit_id
                """
            ),
            {
                "visit_id": visit_id,
                "proposed": proposed_stored,
                "proposed_end": proposed_end_stored,
                "reason": reason,
                "actor_role": actor_role,
            },
        )
        actor_short = "Principal Investigator" if actor_role == "pi" else "Study Coordinator"
        proposed_label = _format_utc_label_from_iso(proposed_stored)
        proposed_end_label = (
            _format_utc_label_from_iso(proposed_end_stored) if proposed_end_stored else None
        )
        activity_msg = f"Reschedule requested by {actor_short}. Proposed start (UTC): {proposed_label}."
        if proposed_end_label:
            activity_msg += f" Proposed end (UTC): {proposed_end_label}."
        if len(slots) > 1:
            activity_msg += " Three proposed slots were submitted for CRA selection."
        await _append_visit_activity(
            db,
            visit_id,
            activity_msg,
            initials="RS",
            color="orange",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save reschedule request: {str(e)}")

    cra_email = str(visit.get("cra_email") or "").strip()
    cra_name = str(visit.get("cra_name") or "").strip() or "Clinical Research Associate"
    site_loc = html.escape(str(visit.get("site_address") or ""))
    visit_date_raw = str(visit.get("visit_date") or "")
    iso_cur = str(visit.get("visit_date_iso") or "").strip()
    if visit_date_raw and iso_cur:
        current_slot_display = f"{visit_date_raw} ({iso_cur})"
    elif visit_date_raw:
        current_slot_display = visit_date_raw
    else:
        current_slot_display = iso_cur or "(not set)"
    current_slot = html.escape(current_slot_display)
    subject_cra = f"Reschedule request — {visit_label}"
    html_cra = f"""
<div style="font-family:Arial,sans-serif;line-height:1.5;color:#111">
  <p>Hi {html.escape(cra_name)},</p>
  <p>The site has submitted a <strong>reschedule request</strong> for monitoring visit <strong>{html.escape(visit_label)}</strong>.</p>
  <p><strong>Current schedule:</strong><br/>{current_slot}<br/>{site_loc}</p>
  <p><strong>Proposed start (UTC):</strong><br/>{html.escape(proposed_stored)}</p>
  {f'<p><strong>Proposed end (UTC):</strong><br/>{html.escape(proposed_end_stored)}</p>' if proposed_end_stored else ''}
  <p><strong>All proposed slots (UTC):</strong></p>
  <ol>
    {''.join(f"<li>{html.escape(slot['proposed_datetime_iso'])}{' â€“ ' + html.escape(slot['proposed_end_datetime_iso']) if slot.get('proposed_end_datetime_iso') else ''}</li>" for slot in slots)}
  </ol>
  <p><strong>Reason:</strong></p>
  <p style="white-space:pre-wrap;border-left:3px solid #0f62fe;padding-left:12px">{html.escape(reason)}</p>
  <p style="font-size:12px;color:#666">Requested via email link by {html.escape(actor_short)}.</p>
</div>
""".strip()
    # Email is enqueued for asynchronous delivery; we report "notified"
    # optimistically because the route no longer waits on SMTP. The Celery
    # worker retries on transient errors and logs the final outcome.
    cra_notified = False
    if cra_email and "@" in cra_email:
        enqueue_email(
            to=cra_email,
            subject=subject_cra,
            body=html_cra,
            from_email=settings.smtp_user or "noreply@dizzaroo.com",
            from_name="Dizzaroo CRM Monitoring",
            html=True,
        )
        cra_notified = True

    await db.commit()

    # Public Notice Board: a reschedule is a real schedule change someone
    # else on the (study, site) needs to know about. Best-effort — the
    # reschedule itself is already committed.
    try:
        from app.utils.system_notices import post_site_event_notice
        info = (
            await db.execute(
                text(
                    "SELECT site_id, study_id, visit_type, site_visit_number "
                    "FROM monitoring_visits WHERE id = :id"
                ),
                {"id": visit_id},
            )
        ).mappings().first()
        if info and info.get("site_id"):
            actor_short = "Principal Investigator" if actor_role == "pi" else "Study Coordinator"
            label = info.get("visit_type") or "Monitoring"
            num = info.get("site_visit_number")
            tail = f" #{num}" if num else ""
            await post_site_event_notice(
                db,
                site_ref=info["site_id"],
                study_ref=info.get("study_id"),
                event_type="monitoring_visit_rescheduled",
                message=(
                    f"{label} visit{tail} reschedule requested by {actor_short} — "
                    f"proposed: {proposed_stored}. Reason: {reason}"
                ),
                metadata={
                    "visit_id": visit_id,
                    "reschedule_request_id": request_id,
                    "actor_role": actor_role,
                    "proposed_datetime_iso": proposed_stored,
                    "proposed_slots": slots,
                    "reason": reason,
                },
            )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "submit_visit_reschedule: notice-board hook failed for visit %s", sfmt(visit_id)
        )

    return {
        "status": "ok",
        "request_id": request_id,
        "visit_id": visit_id,
        "proposed_datetime_iso": proposed_stored,
        "proposed_end_datetime_iso": proposed_end_stored or None,
        "proposed_slots": slots,
        "cra_notified": cra_notified,
    }


@router.get("/visits/{visit_id}/reschedule-requests/pending")
async def get_pending_reschedule_request(visit_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    row = await db.execute(
        text(
            """
            SELECT id, visit_id, proposed_date, proposed_end_date, proposed_slots, reason, decision_reason, status, created_at
            FROM visit_reschedule_requests
            WHERE visit_id = :visit_id AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"visit_id": visit_id},
    )
    req = row.mappings().first()
    if not req:
        return {"request": None}
    req_dict = dict(req)
    # Convert DB datetimes to ISO strings for the frontend.
    if req_dict.get("proposed_date") is not None and hasattr(req_dict["proposed_date"], "isoformat"):
        req_dict["proposed_date"] = req_dict["proposed_date"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if req_dict.get("proposed_end_date") is not None and hasattr(req_dict["proposed_end_date"], "isoformat"):
        req_dict["proposed_end_date"] = req_dict["proposed_end_date"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if req_dict.get("created_at") is not None and hasattr(req_dict["created_at"], "isoformat"):
        req_dict["created_at"] = req_dict["created_at"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    req_dict["proposed_slots"] = _slots_from_request(req)
    return {"request": req_dict}


@router.post("/visits/{visit_id}/reschedule-requests/{request_id}/decision")
async def decide_reschedule_request(
    visit_id: str,
    request_id: str,
    body: VisitRescheduleDecisionSubmit,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    decision = str(body.decision or "").strip().lower()
    decision_reason = str(body.reason or "").strip()
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="decision must be approved or rejected")
    if decision == "rejected" and len(decision_reason) < 3:
        raise HTTPException(status_code=400, detail="Please provide a reason for declining")

    req_row = await db.execute(
        text(
            """
            SELECT id, visit_id, proposed_date, proposed_end_date, proposed_slots, reason, status
            FROM visit_reschedule_requests
            WHERE id = CAST(:request_id AS UUID) AND visit_id = :visit_id
            LIMIT 1
            """
        ),
        {"request_id": request_id, "visit_id": visit_id},
    )
    req = req_row.mappings().first()
    if not req:
        raise HTTPException(status_code=404, detail="Reschedule request not found")
    if str(req.get("status") or "") != "pending":
        return {"status": "ok", "request_status": str(req.get("status") or "")}

    await db.execute(
        text(
            """
            UPDATE visit_reschedule_requests
            SET status = :status, decision_reason = :decision_reason, updated_at = CURRENT_TIMESTAMP, decided_at = CURRENT_TIMESTAMP
            WHERE id = CAST(:request_id AS UUID)
            """
        ),
        {"request_id": request_id, "status": decision, "decision_reason": decision_reason},
    )

    visit_ctx_res = await db.execute(
        text(
            """
            SELECT v.id, v.visit_date, v.visit_date_iso, v.site_id, v.site_visit_number
            FROM monitoring_visits v
            WHERE v.id = :visit_id
            LIMIT 1
            """
        ),
        {"visit_id": visit_id},
    )
    visit_ctx = visit_ctx_res.mappings().first() or {}
    visit_label_decision = _visit_label_from_site_number(
        visit_ctx.get("site_visit_number"), str(visit_ctx.get("id") or visit_id)
    )

    contact_res = await db.execute(
        text(
            """
            SELECT
                COALESCE(sp.pi_name, v.principal_investigator, 'Principal Investigator') AS pi_name,
                COALESCE(NULLIF(sp.pi_email, ''), NULLIF(v.pi_email, '')) AS pi_email,
                COALESCE(sp.site_coordinator_name, v.study_coordinator, 'Study Coordinator') AS coordinator_name,
                COALESCE(NULLIF(sp.site_coordinator_email, ''), '') AS coordinator_email
            FROM monitoring_visits v
            LEFT JOIN sites s ON (
                v.site_id IS NOT NULL AND
                (v.site_id = s.site_id OR v.site_id = CAST(s.id AS TEXT))
            )
            LEFT JOIN site_profiles sp ON sp.site_id = s.id
            WHERE v.id = :visit_id
            LIMIT 1
            """
        ),
        {"visit_id": visit_id},
    )
    contact = contact_res.mappings().first() or {}
    site_recipients: List[Dict[str, str]] = []
    pi_email = str(contact.get("pi_email") or "").strip()
    if "@" in pi_email:
        site_recipients.append(
            {"name": str(contact.get("pi_name") or "Principal Investigator"), "email": pi_email, "role": "pi"}
        )
    coord_email = str(contact.get("coordinator_email") or "").strip()
    if "@" in coord_email:
        site_recipients.append(
            {
                "name": str(contact.get("coordinator_name") or "Study Coordinator"),
                "email": coord_email,
                "role": "coordinator",
            }
        )
    cc_res = await db.execute(
        text(
            """
            SELECT COALESCE(cc_emails, '') AS cc_emails
            FROM monitoring_confirmation_letters
            WHERE visit_id = :visit_id
            LIMIT 1
            """
        ),
        {"visit_id": visit_id},
    )
    cc_row = cc_res.mappings().first() or {}
    cc_raw = str(cc_row.get("cc_emails") or "").strip()
    if cc_raw:
        existing_emails = {str(recipient["email"]).strip().lower() for recipient in site_recipients}
        for cc_email in [item.strip() for item in re.split(r"[;,]", cc_raw) if item.strip()]:
            cc_email_norm = cc_email.lower()
            if "@" not in cc_email or cc_email_norm in existing_emails:
                continue
            site_recipients.append(
                {
                    "name": cc_email,
                    "email": cc_email,
                    "role": "cc",
                }
            )
            existing_emails.add(cc_email_norm)

    if decision == "approved":
        proposed_slots = _slots_from_request(req)
        selected_slot_index = body.selected_slot_index if body.selected_slot_index is not None else 1
        try:
            selected_slot_index_int = int(selected_slot_index)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="selected_slot_index must be 1, 2, or 3")
        selected_slot = next((s for s in proposed_slots if int(s.get("index") or 0) == selected_slot_index_int), None)
        if selected_slot is None:
            raise HTTPException(status_code=400, detail="Selected proposed slot was not found")
        proposed_dt = datetime.fromisoformat(
            str(selected_slot["proposed_datetime_iso"]).replace("Z", "+00:00")
        )
        start_ymd = proposed_dt.strftime("%Y-%m-%d")
        start_time = f"{proposed_dt.hour:02d}:{proposed_dt.minute:02d}"
        display_date, visit_date_iso = _build_visit_date_fields_from_date_and_time(start_ymd, start_time)

        proposed_end_raw = selected_slot.get("proposed_end_datetime_iso")
        if proposed_end_raw:
            proposed_end_dt = datetime.fromisoformat(str(proposed_end_raw).replace("Z", "+00:00"))
        else:
            proposed_end_dt = proposed_dt
        end_ymd = proposed_end_dt.strftime("%Y-%m-%d")
        end_time = f"{proposed_end_dt.hour:02d}:{proposed_end_dt.minute:02d}"
        visit_end_date, visit_end_date_iso = _build_visit_date_fields_from_date_and_time(end_ymd, end_time)

        await db.execute(
            text(
                """
                UPDATE monitoring_visits
                SET
                    visit_date = :visit_date,
                    visit_date_iso = :visit_date_iso,
                    visit_end_date = :visit_end_date,
                    visit_end_date_iso = :visit_end_date_iso,
                    status = 'Visit Confirmed',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :visit_id
                """
            ),
            {
                "visit_id": visit_id,
                "visit_date": display_date,
                "visit_date_iso": visit_date_iso,
                "visit_end_date": visit_end_date,
                "visit_end_date_iso": visit_end_date_iso,
            },
        )
        end_iso = visit_end_date_iso or visit_date_iso
        slot_label = _format_utc_label_from_iso(visit_date_iso)
        if end_iso != visit_date_iso:
            slot_label += f" – {_format_utc_label_from_iso(end_iso)}"
        await _append_visit_activity(
            db,
            visit_id,
            f"Sponsor accepted reschedule request for {visit_label_decision}. Selected option {selected_slot_index_int}. New visit slot: {slot_label}.",
            initials="SP",
            color="green",
        )
        if site_recipients:
            approved_slot_label = display_date
            if visit_end_date and visit_end_date != display_date:
                approved_slot_label = f"{display_date} to {visit_end_date}"
            email_jobs: List[Dict[str, str]] = []
            subject = f"Reschedule request accepted — {visit_label_decision}"
            for recipient in site_recipients:
                body_html = f"""
<div style="font-family:Arial,sans-serif;line-height:1.5;color:#111">
  <p>Hi {html.escape(recipient['name'])},</p>
  <p>
    The Sponsor has accepted your request to reschedule
    <strong>{html.escape(visit_label_decision)}</strong>.
  </p>
  <p>
    The new visit slot is confirmed for <strong>{html.escape(approved_slot_label)}</strong>.
  </p>
  <p>
    Please find attached the updated Confirmation Letter for your records.
  </p>
</div>
                """.strip()
                email_jobs.append(
                    {
                        "name": recipient["name"],
                        "email": recipient["email"],
                        "role": recipient.get("role", ""),
                        "body_html": body_html,
                    }
                )
            tmp_dir = Path(tempfile.mkdtemp(prefix="reschedule_confirmation_"))
            tmp_pdf = tmp_dir / "UpdatedConfirmationLetter.pdf"
            try:
                await _build_updated_confirmation_letter_pdf_for_visit(db, visit_id, tmp_pdf)
                background_tasks.add_task(
                    _send_reschedule_acceptance_emails_with_attachment,
                    recipients=email_jobs,
                    subject=subject,
                    pdf_path=tmp_pdf,
                )
            except Exception:
                logger.exception(
                    "Failed to build updated confirmation letter attachment for visit %s; sending acceptance email without attachment",
                    sfmt(visit_id),
                )
                try:
                    tmp_pdf.unlink(missing_ok=True)
                    tmp_dir.rmdir()
                except OSError:
                    pass
                for job in email_jobs:
                    background_tasks.add_task(
                        enqueue_email,
                        to=job["email"],
                        subject=subject,
                        body=job["body_html"],
                        from_email=settings.smtp_user or "noreply@dizzaroo.com",
                        from_name="Dizzaroo CRM Monitoring",
                        html=True,
                    )
    else:
        await db.execute(
            text(
                """
                UPDATE monitoring_visits
                SET status = 'Scheduled', updated_at = CURRENT_TIMESTAMP
                WHERE id = :visit_id
                """
            ),
            {"visit_id": visit_id},
        )
        await _append_visit_activity(
            db,
            visit_id,
            f"Sponsor declined reschedule request for {visit_label_decision}. Reason: {decision_reason}",
            initials="SP",
            color="red",
        )
        if site_recipients:
            subject = f"Reschedule request declined — {visit_label_decision}"
            original_visit_date = str(visit_ctx.get("visit_date") or "the original schedule")
            for recipient in site_recipients:
                body_html = f"""
<div style="font-family:Arial,sans-serif;line-height:1.5;color:#111">
  <p>Hi {html.escape(recipient['name'])},</p>
  <p>
    The Sponsor has declined the reschedule request for
    <strong>{html.escape(visit_label_decision)}</strong>.
  </p>
  <p>
    The original date remains: <strong>{html.escape(original_visit_date)}</strong>.
  </p>
  <p>
    <strong>Reason:</strong> {html.escape(decision_reason)}
  </p>
</div>
                """.strip()
                # Celery handles async delivery + retries; no need for
                # FastAPI BackgroundTasks here (which would still run inside
                # the FastAPI process and block this worker).
                background_tasks.add_task(
                    enqueue_email,
                    to=recipient["email"],
                    subject=subject,
                    body=body_html,
                    from_email=settings.smtp_user or "noreply@dizzaroo.com",
                    from_name="Dizzaroo CRM Monitoring",
                    html=True,
                )

    await db.commit()
    return {"status": "ok", "request_status": decision, "decision_reason": decision_reason}

