"""REST API: visit report review workflow (submit-for-review, approve/reject, comments)."""
from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.integrations.smtp_service import enqueue_email, smtp_service
from app.utils.log_sanitize import sfmt

logger = logging.getLogger(__name__)
router = APIRouter(tags=["monitor"])


# Legacy helpers + Pydantic body schemas still defined in app.modules.monitoring.aggregator.
# Top-level imports work because router.py defines all of these BEFORE its
# bottom-of-file include_router(...) lines. By the time this module is being
# loaded, those names already exist on the partially-initialized parent.
from app.modules.monitoring.aggregator import (  # noqa: E402
    _ensure_monitor_tables,
    _require_monitoring_visit,
    _append_visit_activity,
    _get_valid_token,
    _get_report_payload,
    _get_review_comments,
    SubmitForReviewBody,
    SaveAnnotationBody,
    UpdateAnnotationBody,
    AuthorReplyBody,
    ApproveRejectBody,
)
from app.modules.monitoring.routes.mvr_templates import (  # noqa: E402
    _fetch_mvr_template_row_by_id,
    _mvr_template_public,
)

REVISION_BASELINE_KEY = "revisionBaseline"
PAYLOAD_SYSTEM_KEYS = {
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
    REVISION_BASELINE_KEY,
}


def _normalize_review_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Keep legacy top-level answers available to the reviewer UI.

    Some reports were saved with field values at the payload root instead of
    inside submissionData. Some newer rows also archive legacy answers under
    archivedData after template sync. The review page renders from submissionData
    for dynamic templates, so we merge any such values into submissionData while
    preserving the original payload shape.
    """
    normalized = dict(payload)
    submission = normalized.get("submissionData")
    merged_submission: Dict[str, Any] = {}
    if isinstance(submission, dict):
        merged_submission = dict(submission)

    archived = normalized.get("archivedData")
    if isinstance(archived, dict):
        for key, value in archived.items():
            merged_submission.setdefault(key, value)

    for key, value in payload.items():
        if key in PAYLOAD_SYSTEM_KEYS:
            continue
        merged_submission.setdefault(key, value)

    if merged_submission:
        normalized["submissionData"] = merged_submission
    return normalized


def _revision_baseline_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Snapshot the report content the reviewer rejected, for later change review."""
    snapshot = {
        k: v
        for k, v in payload.items()
        if k not in {"reportStatus", "rejectionReason", REVISION_BASELINE_KEY}
    }
    raw_submission = payload.get("submissionData")
    submission_data = raw_submission if isinstance(raw_submission, dict) else {}
    return {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "payload": snapshot,
        "submissionData": submission_data,
    }


@router.post("/visits/{visit_id}/visit-report/submit-for-review")
async def submit_report_for_review(
    visit_id: str,
    body: SubmitForReviewBody,
    db: AsyncSession = Depends(get_db),
):
    """Authenticated: CRA submits report for reviewer. Creates token, updates status, sends email."""
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)

    payload = _normalize_review_payload(await _get_report_payload(db, visit_id))
    payload["reportStatus"] = "In Review"

    # Freeze the exact template used for this report so later edits to the live
    # template never mutate an already-submitted / approved report. An existing
    # snapshot wins: on resubmit after rejection the author revised against that
    # snapshot, so re-freezing from the live row could show the reviewer a
    # template the author never saw.
    snap = payload.get("templateSnapshot")
    if not (isinstance(snap, dict) and isinstance(snap.get("schema"), dict)):
        tid = str(payload.get("templateId") or "").strip()
        trow = await _fetch_mvr_template_row_by_id(db, tid) if tid else None
        if trow:
            payload["templateSnapshot"] = _mvr_template_public(trow)
        else:
            # No template id (legacy report) or the template row was deleted:
            # never freeze the live org template wholesale — derive a frozen
            # template filtered to the fields actually present in the report.
            from app.modules.monitoring.routes.post_visit_and_report import (  # noqa: E402
                _resolve_frozen_report_template,
            )

            frozen = await _resolve_frozen_report_template(db, payload)
            if isinstance(frozen, dict):
                payload["templateSnapshot"] = frozen

    payload_json = json.dumps(payload)

    await db.execute(
        text(
            """
            INSERT INTO monitoring_visit_reports (visit_id, payload, updated_at)
            VALUES (:visit_id, CAST(:payload AS jsonb), CURRENT_TIMESTAMP)
            ON CONFLICT (visit_id)
            DO UPDATE SET payload = CAST(EXCLUDED.payload AS jsonb), updated_at = CURRENT_TIMESTAMP
            """
        ),
        {"visit_id": visit_id, "payload": payload_json},
    )

    # Invalidate any existing active tokens for this visit
    await db.execute(
        text(
            "UPDATE monitoring_visit_review_tokens SET is_valid = FALSE WHERE visit_id = :visit_id"
        ),
        {"visit_id": visit_id},
    )

    token_id = str(uuid4())
    token_value = str(uuid4())
    reviewer_email = body.reviewer_email.strip()
    author_email = (body.author_email or "").strip()
    message = (body.message or "").strip()

    await db.execute(
        text(
            """
            INSERT INTO monitoring_visit_review_tokens
                (id, visit_id, token, reviewer_email, author_email, message)
            VALUES (:id, :visit_id, :token, :reviewer_email, :author_email, :message)
            """
        ),
        {
            "id": token_id,
            "visit_id": visit_id,
            "token": token_value,
            "reviewer_email": reviewer_email,
            "author_email": author_email,
            "message": message,
        },
    )

    await _append_visit_activity(
        db, visit_id, f"Visit report submitted for review to {reviewer_email}"
    )
    await db.commit()

    frontend_base = getattr(settings, "frontend_base_url", "http://localhost:3000")
    review_url = f"{frontend_base}/monitoring/visits/{visit_id}/review?token={token_value}"

    from_email = settings.smtp_user or "noreply@dizzaroo.com"
    msg_section = (
        f"<p><strong>Message from the monitor:</strong></p>"
        f"<blockquote style='border-left:3px solid #1a56db;padding-left:12px;"
        f"margin:8px 0;color:#374151;font-style:italic'>{html.escape(message)}</blockquote>"
        if message
        else ""
    )
    email_html = f"""
<div style="font-family:Arial,sans-serif;line-height:1.6;color:#111827;max-width:600px">
  <div style="background:#1a56db;padding:24px 28px;border-radius:8px 8px 0 0">
    <h2 style="color:#fff;margin:0;font-size:20px">Monitoring Visit Report — Review Request</h2>
  </div>
  <div style="background:#f9fafb;padding:24px 28px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px">
    <p>You have been asked to review a <strong>Monitoring Visit Report</strong>.</p>
    {msg_section}
    <p>Click the button below to open the report, add inline comments by highlighting text, then approve or reject it.</p>
    <p style="text-align:center;margin:24px 0">
      <a href="{review_url}" style="background:#1a56db;color:#fff;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:700;font-size:14px">
        Open Report for Review ›
      </a>
    </p>
    <p style="font-size:12px;color:#6b7280">Or copy this link:<br/>
      <a href="{review_url}" style="color:#1a56db;word-break:break-all">{review_url}</a>
    </p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0"/>
    <p style="font-size:11px;color:#9ca3af">This is an automated message from Dizzaroo CRM Monitoring.</p>
  </div>
</div>
""".strip()

    try:
        enqueue_email(
            to=reviewer_email,
            subject="Review Request: Monitoring Visit Report",
            body=email_html,
            from_email=from_email,
            from_name="Dizzaroo CRM Monitoring",
            html=True,
        )
    except Exception:
        logger.exception(
            "submit-for-review: report saved but reviewer email failed for visit %s",
            sfmt(visit_id),
        )

    return {"status": "submitted", "review_url": review_url, "reviewer_email": reviewer_email}


@router.get("/visits/{visit_id}/visit-report/review")
async def get_report_for_review(visit_id: str, token: str, db: AsyncSession = Depends(get_db)):
    """Public (no auth): returns report payload + comments for the reviewer."""
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    tok = await _get_valid_token(db, token, visit_id)
    payload = _normalize_review_payload(await _get_report_payload(db, visit_id))
    comments = await _get_review_comments(db, visit_id)
    seq_row = await db.execute(
        text("SELECT site_visit_number FROM monitoring_visits WHERE id = :visit_id LIMIT 1"),
        {"visit_id": visit_id},
    )
    seq_m = seq_row.mappings().first()
    site_visit_number = None
    if seq_m and seq_m.get("site_visit_number") is not None:
        try:
            site_visit_number = int(seq_m["site_visit_number"])
        except (TypeError, ValueError):
            site_visit_number = None
    template_public = None
    if isinstance(payload, dict):
        # Prefer the frozen snapshot captured at submit time so the reviewer sees
        # the report exactly as submitted, even if the live template changed since.
        # Falls back to the saved templateId row, then to a frozen derivation
        # filtered to the report's own fields — never the raw live org template.
        from app.modules.monitoring.routes.post_visit_and_report import (  # noqa: E402
            _resolve_frozen_report_template,
        )

        template_public = await _resolve_frozen_report_template(db, payload)
    return {
        "payload": payload,
        "comments": comments,
        "reviewer_email": tok.get("reviewer_email"),
        "message": tok.get("message"),
        "template": template_public,
        "site_visit_number": site_visit_number,
    }


@router.get("/visits/{visit_id}/visit-report/comments")
async def get_report_comments_for_author(visit_id: str, db: AsyncSession = Depends(get_db)):
    """Authenticated: returns inline review comments so the author can see annotations."""
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    comments = await _get_review_comments(db, visit_id)
    return {"comments": comments}


@router.patch("/visits/{visit_id}/visit-report/comments/{comment_id}/reply")
async def save_author_reply_to_comment(
    visit_id: str,
    comment_id: str,
    body: AuthorReplyBody,
    db: AsyncSession = Depends(get_db),
):
    """Authenticated: sponsor/author replies to a reviewer inline comment (rejected reports only)."""
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)

    payload = await _get_report_payload(db, visit_id)
    if str(payload.get("reportStatus") or "") != "Rejected":
        raise HTTPException(
            status_code=400,
            detail="Author replies are only allowed while the report is rejected for revision",
        )

    reply_text = body.author_reply.strip()
    if not reply_text:
        raise HTTPException(status_code=400, detail="Reply text is required")

    result = await db.execute(
        text(
            """
            UPDATE monitoring_visit_review_comments
            SET author_reply = :author_reply,
                author_reply_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :comment_id AND visit_id = :visit_id
            RETURNING id, highlighted_text, dom_path, start_offset, end_offset,
                      comment_text, author_reply, author_reply_at, created_at, updated_at
            """
        ),
        {
            "comment_id": comment_id,
            "visit_id": visit_id,
            "author_reply": reply_text,
        },
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")

    await _append_visit_activity(db, visit_id, "Author replied to a visit report review comment")
    await db.commit()

    cmt = dict(row)
    if cmt.get("id"):
        cmt["id"] = str(cmt["id"])
    for key in ("created_at", "updated_at", "author_reply_at"):
        if cmt.get(key) and hasattr(cmt[key], "isoformat"):
            cmt[key] = cmt[key].isoformat()
    return {"status": "saved", "comment": cmt}


@router.post("/visits/{visit_id}/visit-report/review/comments")
async def save_review_comment(
    visit_id: str,
    body: SaveAnnotationBody,
    db: AsyncSession = Depends(get_db),
):
    """Public (no auth): reviewer saves an inline annotation comment."""
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    tok = await _get_valid_token(db, body.token, visit_id)
    token_id = tok["id"]

    comment_id = str(uuid4())
    await db.execute(
        text(
            """
            INSERT INTO monitoring_visit_review_comments
                (id, visit_id, token_id, highlighted_text, dom_path,
                 start_offset, end_offset, comment_text)
            VALUES (:id, :visit_id, :token_id, :highlighted_text, :dom_path,
                    :start_offset, :end_offset, :comment_text)
            """
        ),
        {
            "id": comment_id,
            "visit_id": visit_id,
            "token_id": token_id,
            "highlighted_text": body.highlighted_text,
            "dom_path": body.dom_path,
            "start_offset": body.start_offset,
            "end_offset": body.end_offset,
            "comment_text": body.comment_text,
        },
    )
    await db.commit()
    return {"status": "saved", "id": comment_id}


@router.patch("/visits/{visit_id}/visit-report/review/comments/{comment_id}")
async def update_review_comment(
    visit_id: str,
    comment_id: str,
    body: UpdateAnnotationBody,
    db: AsyncSession = Depends(get_db),
):
    """Public (no auth): reviewer edits their own annotation."""
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    await _get_valid_token(db, body.token, visit_id)

    result = await db.execute(
        text(
            """
            UPDATE monitoring_visit_review_comments
            SET comment_text = :comment_text, updated_at = CURRENT_TIMESTAMP
            WHERE id = :comment_id AND visit_id = :visit_id
            """
        ),
        {
            "comment_id": comment_id,
            "visit_id": visit_id,
            "comment_text": body.comment_text,
        },
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Comment not found")
    await db.commit()
    return {"status": "updated"}


@router.delete("/visits/{visit_id}/visit-report/review/comments/{comment_id}")
async def delete_review_comment(
    visit_id: str,
    comment_id: str,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Public (no auth): reviewer deletes their own annotation (token as query param)."""
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    await _get_valid_token(db, token, visit_id)

    result = await db.execute(
        text(
            "DELETE FROM monitoring_visit_review_comments WHERE id = :comment_id AND visit_id = :visit_id"
        ),
        {"comment_id": comment_id, "visit_id": visit_id},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Comment not found")
    await db.commit()
    return {"status": "deleted"}


@router.post("/visits/{visit_id}/visit-report/review/approve")
async def approve_report(
    visit_id: str,
    body: ApproveRejectBody,
    db: AsyncSession = Depends(get_db),
):
    """Public (no auth): reviewer approves the report."""
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    tok = await _get_valid_token(db, body.token, visit_id)

    # Update report status to Approved
    payload = await _get_report_payload(db, visit_id)
    payload["reportStatus"] = "Approved"

    # Preserve or capture the frozen template so later edits to the live template
    # never mutate this approved report.
    if not isinstance(payload.get("templateSnapshot"), dict):
        from app.modules.monitoring.routes.post_visit_and_report import (  # noqa: E402
            _resolve_frozen_report_template,
        )

        frozen = await _resolve_frozen_report_template(db, payload)
        if frozen:
            payload["templateSnapshot"] = frozen

    await db.execute(
        text(
            """
            UPDATE monitoring_visit_reports
            SET payload = CAST(:payload AS jsonb), updated_at = CURRENT_TIMESTAMP
            WHERE visit_id = :visit_id
            """
        ),
        {"visit_id": visit_id, "payload": json.dumps(payload)},
    )

    # Invalidate the token
    await db.execute(
        text(
            """
            UPDATE monitoring_visit_review_tokens
            SET is_valid = FALSE, used_at = CURRENT_TIMESTAMP
            WHERE token = :token
            """
        ),
        {"token": body.token},
    )

    await _append_visit_activity(db, visit_id, "Visit report approved by reviewer")
    await db.commit()

    # Public Notice Board: report approval is a milestone the team should see.
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
            label = info.get("visit_type") or "Monitoring"
            num = info.get("site_visit_number")
            tail = f" #{num}" if num else ""
            reviewer = tok.get("reviewer_email") or "reviewer"
            await post_site_event_notice(
                db,
                site_ref=info["site_id"],
                study_ref=info.get("study_id"),
                event_type="monitoring_visit_report_approved",
                message=f"{label} visit{tail} report was approved by {reviewer}.",
                metadata={
                    "visit_id": visit_id,
                    "reviewer_email": tok.get("reviewer_email"),
                    "author_email": tok.get("author_email"),
                },
            )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "approve_report: notice-board hook failed for visit %s", sfmt(visit_id)
        )

    # Email the author
    author_email = tok.get("author_email", "")
    reviewer_email = tok.get("reviewer_email", "")
    if author_email and "@" in author_email:
        frontend_base = getattr(settings, "frontend_base_url", "http://localhost:3000")
        from_email = settings.smtp_user or "noreply@dizzaroo.com"
        email_html = f"""
<div style="font-family:Arial,sans-serif;line-height:1.6;color:#111827;max-width:600px">
  <div style="background:#16a34a;padding:24px 28px;border-radius:8px 8px 0 0">
    <h2 style="color:#fff;margin:0;font-size:20px">✓ Visit Report Approved</h2>
  </div>
  <div style="background:#f0fdf4;padding:24px 28px;border:1px solid #bbf7d0;border-top:none;border-radius:0 0 8px 8px">
    <p>Great news! Your <strong>Monitoring Visit Report</strong> has been <strong>approved</strong> by the reviewer ({html.escape(reviewer_email)}).</p>
    <p>The document has been locked and no further edits are required.</p>
    <hr style="border:none;border-top:1px solid #bbf7d0;margin:16px 0"/>
    <p style="font-size:11px;color:#9ca3af">Dizzaroo CRM Monitoring — automated notification.</p>
  </div>
</div>""".strip()
        enqueue_email(
            to=author_email,
            subject="Your Monitoring Visit Report has been Approved",
            body=email_html,
            from_email=from_email,
            from_name="Dizzaroo CRM Monitoring",
            html=True,
        )

    return {"status": "approved"}


@router.post("/visits/{visit_id}/visit-report/review/reject")
async def reject_report(
    visit_id: str,
    body: ApproveRejectBody,
    db: AsyncSession = Depends(get_db),
):
    """Public (no auth): reviewer rejects the report with an overall reason."""
    await _ensure_monitor_tables(db)
    await _require_monitoring_visit(db, visit_id)
    tok = await _get_valid_token(db, body.token, visit_id)

    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=400, detail="A rejection reason is required")

    # Update report status to Rejected and store the reason in payload
    payload = await _get_report_payload(db, visit_id)
    payload[REVISION_BASELINE_KEY] = _revision_baseline_from_payload(payload)
    payload["reportStatus"] = "Rejected"
    payload["rejectionReason"] = body.reason.strip()
    await db.execute(
        text(
            """
            UPDATE monitoring_visit_reports
            SET payload = CAST(:payload AS jsonb), updated_at = CURRENT_TIMESTAMP
            WHERE visit_id = :visit_id
            """
        ),
        {"visit_id": visit_id, "payload": json.dumps(payload)},
    )

    # Invalidate the token
    await db.execute(
        text(
            """
            UPDATE monitoring_visit_review_tokens
            SET is_valid = FALSE, used_at = CURRENT_TIMESTAMP
            WHERE token = :token
            """
        ),
        {"token": body.token},
    )

    await _append_visit_activity(
        db, visit_id, f"Visit report rejected by reviewer: {body.reason.strip()[:80]}"
    )
    await db.commit()

    # Public Notice Board: report rejection is a milestone the team must see —
    # it implies follow-up work for the author.
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
            label = info.get("visit_type") or "Monitoring"
            num = info.get("site_visit_number")
            tail = f" #{num}" if num else ""
            reviewer = tok.get("reviewer_email") or "reviewer"
            reason_short = (body.reason.strip()[:120] + "…") if len(body.reason.strip()) > 120 else body.reason.strip()
            await post_site_event_notice(
                db,
                site_ref=info["site_id"],
                study_ref=info.get("study_id"),
                event_type="monitoring_visit_report_rejected",
                message=(
                    f"{label} visit{tail} report was rejected by {reviewer} — "
                    f"reason: {reason_short}"
                ),
                metadata={
                    "visit_id": visit_id,
                    "reviewer_email": tok.get("reviewer_email"),
                    "author_email": tok.get("author_email"),
                    "reason": body.reason.strip(),
                },
            )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "reject_report: notice-board hook failed for visit %s", sfmt(visit_id)
        )

    # Email the author
    author_email = tok.get("author_email", "")
    reviewer_email = tok.get("reviewer_email", "")
    if author_email and "@" in author_email:
        from_email = settings.smtp_user or "noreply@dizzaroo.com"
        email_html = f"""
<div style="font-family:Arial,sans-serif;line-height:1.6;color:#111827;max-width:600px">
  <div style="background:#dc2626;padding:24px 28px;border-radius:8px 8px 0 0">
    <h2 style="color:#fff;margin:0;font-size:20px">✗ Visit Report Requires Revision</h2>
  </div>
  <div style="background:#fef2f2;padding:24px 28px;border:1px solid #fecaca;border-top:none;border-radius:0 0 8px 8px">
    <p>Your <strong>Monitoring Visit Report</strong> has been <strong>rejected</strong> by the reviewer ({html.escape(reviewer_email)}) and requires revision.</p>
    <p><strong>Overall rejection reason:</strong></p>
    <blockquote style="border-left:3px solid #dc2626;padding-left:12px;margin:8px 0;color:#374151">
      {html.escape(body.reason.strip())}
    </blockquote>
    <p>Please open the report to review the inline comments left by the reviewer, address all feedback, and resubmit for review.</p>
    <hr style="border:none;border-top:1px solid #fecaca;margin:16px 0"/>
    <p style="font-size:11px;color:#9ca3af">Dizzaroo CRM Monitoring — automated notification.</p>
  </div>
</div>""".strip()
        enqueue_email(
            to=author_email,
            subject="Action Required: Monitoring Visit Report Rejected",
            body=email_html,
            from_email=from_email,
            from_name="Dizzaroo CRM Monitoring",
            html=True,
        )

    return {"status": "rejected"}
