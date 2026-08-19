"""REST API: agreement signing flow (send-for-signature/review, sync-zoho-status, signed-document download)."""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import secrets
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import schemas
from app.auth import get_current_user_optional
from app.config import settings
from app.db import get_db
from app.utils.log_sanitize import sfmt
from app.models import (
    Agreement,
    AgreementDocument,
    AgreementDocumentComment,
    AgreementReviewDocument,
    AgreementReviewToken,
    AgreementSignedDocument,
    AgreementSigningToken,
    AgreementStatus,
    AgreementStatus as AgreementStatusEnum,
    CommentStatus,
    Site,
    SiteProfile,
    Study,
    StudySite,
)
from app.modules.agreements.aggregator import _latest_agreement_document
from app.modules.agreements.routes.crud import create_agreement_system_comment
from app.modules.agreements.services.agreement_service import (
    change_agreement_status as change_agreement_status_service,
    create_agreement_notice,
    is_user_internal,
)
from app.modules.agreements.aggregator import (
    SIGNING_LINK_EXPIRY_DAYS,
    _latest_agreement_document,
)
from app.integrations.smtp_service import smtp_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Legal Documents"])

SIGNING_LINK_EXPIRY_DAYS = 30


def _make_named_tempfile(suffix: str, data: bytes | None = None):
    """Create a NamedTemporaryFile(delete=False) with ``suffix``, optionally
    write ``data`` into it, and return the (closed) tempfile object — callers
    rely on its full-path ``.name``. Sync on purpose — call via
    ``asyncio.to_thread`` from async code so the blocking file I/O stays off
    the event loop."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        if data is not None:
            tmp.write(data)
    finally:
        tmp.close()
    return tmp


def _legacy(name):
    import app.modules.agreements.aggregator as _ld
    return getattr(_ld, name)


@router.post("/agreements/{agreement_id}/send-for-signature")
async def send_agreement_for_signature(
    agreement_id: UUID,
    site_signer_email: Optional[str] = Form(None, description="Signer email (auto-filled from SiteProfile when available)"),
    message: Optional[str] = Form(None),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Send the agreement for final signature via secure email link.
    """
    from app.integrations.smtp_service import smtp_service
    from app.modules.agreements.routes.crud import create_agreement_system_comment

    user_id = current_user.get("user_id") if current_user else None
    is_internal = is_user_internal(user_id, db) if user_id else True
    if not is_internal:
        raise HTTPException(status_code=403, detail="Only internal users can send agreements for signature.")

    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement_id)
        .options(selectinload(Agreement.documents))
    )
    agreement = agreement_result.scalar_one_or_none()
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")

    # Cross-study guard: the caller must be entitled to the agreement's study
    # (owner or grant). A regulated action that dispatches a signing link must
    # never be triggerable across study lines. Internal-user + status/document
    # checks below are unchanged.
    from app.integrations.iam.membership import user_can_act_in_study
    from app.models import StudySite as _StudySite
    _study_ref = agreement.study_id
    if _study_ref is None and agreement.study_site_id:
        _ss = await db.execute(
            select(_StudySite.study_id).where(_StudySite.id == agreement.study_site_id)
        )
        _study_ref = _ss.scalar_one_or_none()
    if not (user_id and _study_ref and await user_can_act_in_study(user_id, str(_study_ref))):
        raise HTTPException(status_code=403, detail="You are not entitled to this study.")

    if agreement.status != AgreementStatus.READY_FOR_SIGNATURE:
        raise HTTPException(
            status_code=400,
            detail=f"Agreement must be in READY_FOR_SIGNATURE status. Current status: {agreement.status.value}",
        )

    if not agreement.documents:
        raise HTTPException(status_code=400, detail="Agreement has no document to sign.")

    site_result = await db.execute(select(Site).where(Site.id == agreement.site_id))
    site = site_result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    if not site_signer_email:
        profile_result = await db.execute(select(SiteProfile).where(SiteProfile.site_id == site.id))
        profile = profile_result.scalar_one_or_none()
        site_signer_email = getattr(profile, "authorized_signatory_email", None) if profile else None

    if not site_signer_email or not site_signer_email.strip():
        raise HTTPException(status_code=400, detail="Signer email is required.")

    token_value = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SIGNING_LINK_EXPIRY_DAYS)
    signing_token = AgreementSigningToken(
        agreement_id=agreement.id,
        token=token_value,
        role="site",
        recipient_email=site_signer_email.strip(),
        expires_at=expires_at,
        created_by=user_id,
        is_active='true',
    )
    db.add(signing_token)

    frontend_base_url = (settings.frontend_base_url or "").rstrip("/")
    sign_link = f"{frontend_base_url}/agreement/sign/{agreement_id}?token={token_value}"
    email_body = (
        f"Document ready for signature\n\n"
        f"You have been requested to sign '{agreement.title}'.\n\n"
        f"Secure link: {sign_link}\n\n"
        f"Instructions:\n"
        f"1. Open the secure link.\n"
        f"2. Review the document.\n"
        f"3. Click 'Sign Document' and complete OTP verification.\n\n"
        f"This link expires on {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}.\n"
    )
    if message and message.strip():
        email_body = f"{email_body}\nMessage:\n{message.strip()}\n"

    # Async send — preserves the transactional contract (rollback agreement
    # state on SMTP failure) while freeing the event loop during the SMTP
    # handshake. Sync `send_email` used to pin one worker per signing invite.
    result = await smtp_service.send_email_async(
        to=site_signer_email.strip(),
        subject="Document ready for signature",
        body=email_body,
        from_email=getattr(settings, "smtp_user", "noreply@crm.local"),
        from_name="Clinical Trials CRM",
    )
    if not result.get("success"):
        await db.rollback()
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to send signature email."))

    agreement.status = AgreementStatus.SENT_FOR_SIGNATURE

    # (Legacy CDA workflow send-for-signature bridge sync removed with the bridges.)

    await create_agreement_system_comment(
        db,
        agreement.id,
        None,
        f"Agreement sent for signature via secure email link to {site_signer_email.strip()}.",
    )
    await db.commit()
    logger.info("Agreement %s routed to internal email-link signing for %s", agreement_id, site_signer_email.strip())

    return {
        "status": "success",
        "message": "Signature link sent successfully.",
        "sign_link": sign_link,
        "expires_at": expires_at.isoformat(),
        "email": site_signer_email.strip(),
    }


@router.post("/agreements/{agreement_id}/sync-zoho-status")
async def sync_agreement_zoho_status(
    agreement_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """
    Phase 3: Zoho is no longer an active dependency (disabled).
    """
    logger.info("Rejected Zoho status sync (disabled) for agreement %s", agreement_id)
    raise HTTPException(status_code=410, detail="Zoho status sync is disabled (internal signing only).")


@router.get("/agreements/{agreement_id}/signed-document/{signed_document_id}")
async def download_signed_agreement_pdf(
    agreement_id: UUID,
    signed_document_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Download signed agreement PDF.
    
    Args:
        agreement_id: Agreement UUID
        signed_document_id: AgreementSignedDocument UUID
        
    Returns:
        PDF file response
    """
    # Get signed document
    signed_doc_result = await db.execute(
        select(AgreementSignedDocument)
        .where(AgreementSignedDocument.id == signed_document_id)
        .where(AgreementSignedDocument.agreement_id == agreement_id)
    )
    signed_doc = signed_doc_result.scalar_one_or_none()
    
    if not signed_doc:
        raise HTTPException(status_code=404, detail="Signed document not found")

    logger.info(
        "Serving legacy signed agreement PDF from storage: agreement_id=%s signed_document_id=%s path=%s",
        agreement_id,
        signed_document_id,
        signed_doc.file_path,
    )
    
    # Check if file exists
    pdf_path = Path(signed_doc.file_path)
    if pdf_path.exists():
        filename = pdf_path.name
        return FileResponse(
            path=str(pdf_path),
            filename=filename,
            media_type="application/pdf",
        )

    # Azure fallback: treat file_path as blob name
    from app.utils.azure_storage import get_document_storage
    storage = get_document_storage()
    if not storage:
        raise HTTPException(
            status_code=404,
            detail=f"Signed PDF file not found locally and Azure storage not configured: {signed_doc.file_path}",
        )

    blob_bytes = await storage.download_file(signed_doc.file_path)
    if not blob_bytes:
        raise HTTPException(
            status_code=404,
            detail=f"Signed PDF blob not found in Azure: {signed_doc.file_path}",
        )

    tmp = await asyncio.to_thread(_make_named_tempfile, ".pdf", blob_bytes)
    tmp_path = tmp.name

    filename = Path(signed_doc.file_path).name or "signed_agreement.pdf"
    return FileResponse(
        path=tmp_path,
        filename=filename,
        media_type="application/pdf",
    )


# ============================================================================
# AGREEMENT REVIEW / NEGOTIATION WORKFLOW ENDPOINTS
# ============================================================================

# ---------------------------------------------------------------------------
# Internal helper: force-save a review document via OO Command Service
# ---------------------------------------------------------------------------

async def _oo_forcesave_review_doc(
    review_document,
    db,
) -> bool:
    """
    Call the OnlyOffice Document Server Command Service to trigger a
    force-save of the review document that is currently open in the
    reviewer's browser.

    Problem this solves
    -------------------
    When permissions.edit=false (comment-only mode) OnlyOffice sometimes
    sends status=4 ("closed, no changes") instead of status=2/6.  Comments
    added in that session never reach our callback, so the DOCX on disk
    stays unchanged and _upsert_comments_from_docx finds nothing.

    Calling the Command Service with c=forcesave bypasses the permissions
    check and forces OO to write the current session — including all
    in-memory comments — to the DOCX and POST it to our callback endpoint.

    After the command is sent we poll the DB for up to 10 seconds waiting
    for our callback to update review_document.updated_at.  If it changes
    within that window, comments will have been saved to disk and to the DB
    already.  Whether or not the poll succeeds, the caller should still run
    _upsert_comments_from_docx as a safety net.

    Returns True if the callback updated the document within the timeout.
    """
    import asyncio
    import httpx
    from sqlalchemy import select as _sa_select

    # Reconstruct the exact key that get_onlyoffice_config generated for
    # this review session (must match onlyoffice-config).
    _updated_at = review_document.updated_at
    _ts_ms = int(_updated_at.timestamp() * 1000) if _updated_at else 0
    _rp = review_document.review_file_path or ""
    _rp_sig = int(hashlib.md5(_rp.encode(), usedforsecurity=False).hexdigest(), 16) % (10**9)
    doc_key = f"{review_document.id}_{_ts_ms}_{_rp_sig}_c"

    # OO Document Server Command Service endpoint (Docker-internal URL)
    oo_url = settings.onlyoffice_url.rstrip("/")
    cmd_url = f"{oo_url}/coauthoring/CommandService.ashx"

    payload: dict = {"c": "forcesave", "key": doc_key}

    # Sign the payload if JWT is enabled
    if settings.onlyoffice_jwt_enabled and settings.onlyoffice_jwt_secret:
        from app.utils.onlyoffice_utils import generate_jwt_token
        payload["token"] = generate_jwt_token(payload)

    initial_updated_at = review_document.updated_at

    # ── Call Command Service ──────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(cmd_url, json=payload)
            try:
                data = resp.json()
            except Exception:
                data = {}
            logger.info(
                "OO Command Service forcesave: key=%s http=%s response=%s",
                doc_key,
                resp.status_code,
                data,
            )
            err_code = data.get("error")
            if err_code not in (0, None):
                logger.warning(
                    "OO Command Service returned error=%s for key=%s "
                    "(session may have ended — reviewer may have already closed the tab)",
                    err_code,
                    doc_key,
                )
                # error=1 = key not found (session already ended).
                # OO may have already sent status=2/4 and the file may
                # already be up-to-date — don't abort, let the caller
                # proceed with whatever is on disk.
                return False
    except Exception as exc:
        logger.warning(
            "OO Command Service call failed (url=%s): %s — "
            "proceeding without forced save",
            cmd_url,
            exc,
        )
        return False

    # ── Poll DB until our callback updates the review document ───────────
    # The callback sets review_document.updated_at and commits; we use a
    # fresh SELECT (not db.refresh which can return stale session cache).
    for wait_sec in range(1, 11):          # up to 10 × 1s = 10 seconds
        await asyncio.sleep(1)
        fresh = await db.execute(
            _sa_select(AgreementReviewDocument.updated_at).where(
                AgreementReviewDocument.id == review_document.id
            )
        )
        fresh_ts = fresh.scalar_one_or_none()
        if fresh_ts is not None and fresh_ts != initial_updated_at:
            logger.info(
                "OO forcesave callback confirmed for review_document %s "
                "(waited %ds): updated_at %s → %s",
                review_document.id,
                wait_sec,
                initial_updated_at,
                fresh_ts,
            )
            # Refresh the ORM object so subsequent code sees new fields
            await db.refresh(review_document)
            return True

    logger.warning(
        "OO forcesave callback did NOT update review_document %s within "
        "10 s — comment extraction will run on whatever is currently on disk",
        review_document.id,
    )
    return False


# ---------------------------------------------------------------------------
# Internal helper: extract comments from a saved review DOCX and upsert them
# ---------------------------------------------------------------------------

def _is_substantive_comment_text(text: Optional[str]) -> bool:
    """Only non-whitespace comment bodies block OTP sign-off."""
    return bool((text or "").strip())


def count_substantive_comments_in_docx(docx_path: str) -> int:
    """Top-level, non-empty OnlyOffice comments in a review DOCX."""
    from app.utils.docx_comment_extractor import extract_comments_from_docx

    raw_comments = extract_comments_from_docx(docx_path)
    return sum(
        1
        for raw in raw_comments
        if not raw.get("parent_comment_id")
        and _is_substantive_comment_text(raw.get("text"))
    )


async def count_substantive_review_comments(
    db: AsyncSession,
    review_document_id: UUID,
) -> int:
    """Top-level site comments with non-empty text for this review round."""
    result = await db.execute(
        select(func.count(AgreementDocumentComment.id))
        .where(AgreementDocumentComment.review_document_id == review_document_id)
        .where(AgreementDocumentComment.parent_comment_id.is_(None))
        .where(AgreementDocumentComment.is_internal_reply == "false")
        .where(func.length(func.trim(AgreementDocumentComment.comment_text)) > 0)
    )
    return int(result.scalar_one() or 0)


async def _upsert_comments_from_docx(
    db,
    agreement_id,
    review_document,
    docx_path: str,
    *,
    commit: bool = True,
) -> int:
    """
    Extract OnlyOffice comments from a saved review DOCX and upsert them into
    the agreement_document_comments table.

    Uses PostgreSQL INSERT … ON CONFLICT DO UPDATE so the operation is atomic.
    This prevents UniqueViolationError when the OO callback and the submit-review
    endpoint both call this function around the same time (race condition).

    Rules applied on conflict (same comment_id + review_document_id):
      - comment_text and referenced_text are always refreshed from the DOCX.
      - status, parent_comment_id, and is_internal_reply are NEVER overwritten
        (set once on insert; internal users own status).

    Returns the number of comments processed.
    """
    import uuid as _uuid_mod
    from sqlalchemy.dialects.postgresql import insert as _pg_insert
    from app.utils.docx_comment_extractor import extract_comments_from_docx

    raw_comments = extract_comments_from_docx(docx_path)
    if not raw_comments:
        return 0

    now = datetime.now(timezone.utc)
    processed = 0

    for raw in raw_comments:
        if not _is_substantive_comment_text(raw.get("text")):
            continue

        oo_id = str(raw["comment_id"])

        # ── Resolve parent UUID (best-effort) ────────────────────────────
        # Only needed for the INSERT path.  If the parent hasn't been inserted
        # yet (e.g. concurrent write) parent_uuid stays None and will be
        # updated on the next callback save.
        parent_uuid = None
        if raw.get("parent_comment_id"):
            p_res = await db.execute(
                select(AgreementDocumentComment.id)
                .where(
                    AgreementDocumentComment.comment_id
                    == str(raw["parent_comment_id"])
                )
                .where(
                    AgreementDocumentComment.review_document_id
                    == review_document.id
                )
                .where(AgreementDocumentComment.is_internal_reply == "false")
            )
            parent_uuid = p_res.scalar_one_or_none()

        # ── Atomic upsert ────────────────────────────────────────────────
        # INSERT … ON CONFLICT DO UPDATE avoids the SELECT→INSERT race where
        # a concurrent session (callback or submit-review) inserts the row
        # between our SELECT and our INSERT, causing a UniqueViolationError.
        stmt = _pg_insert(AgreementDocumentComment).values(
            id=_uuid_mod.uuid4(),
            comment_id=oo_id,
            review_document_id=review_document.id,
            agreement_id=agreement_id,
            author_email=raw.get("author") or "external_reviewer",
            comment_text=raw.get("text") or "",
            referenced_text=raw.get("referenced_text") or "",
            oo_date=raw.get("date") or "",
            status=CommentStatus.PENDING.value,
            parent_comment_id=parent_uuid,
            is_internal_reply="false",
        ).on_conflict_do_update(
            # Target the unique constraint on (comment_id, review_document_id)
            constraint="uq_agreement_doc_comment_oo_id",
            # On conflict: refresh content fields only.
            # Never touch: id, status (internal users own it), parent_comment_id,
            # is_internal_reply, agreement_id, review_document_id, oo_date.
            set_=dict(
                comment_text=raw.get("text") or "",
                referenced_text=raw.get("referenced_text") or "",
                updated_at=now,
            ),
        )
        await db.execute(stmt)
        processed += 1

    if commit:
        await db.commit()
    logger.info(
        "Upserted %d comment(s) from review_document %s (agreement %s)",
        processed,
        review_document.id,
        agreement_id,
    )
    return processed


async def persist_review_comments_now(
    db,
    agreement,
    review_document,
    *,
    commit: bool = False,
) -> int:
    """Authoritatively flush + persist a reviewer's OnlyOffice document comments for
    the CURRENT round, synchronously — so a caller can GUARANTEE the comments are in
    the DB before it flips workflow status (kills the old fire-and-forget race).

    Mirrors the proven submit-review path:
      (1) force-save the OO session so comment-only edits are written even when OO
          emits status=4 ("closed, no changes");
      (2) read the freshest review DOCX (re-download if it lives in Azure);
      (3) upsert its comments.

    With ``commit=False`` the upserts join the CALLER's transaction, so comments and
    the caller's status change commit atomically. General — no agreement-type or
    document assumptions; works for any review round and any reviewer.
    """
    # (1) Ask OO to flush the live session (incl. comment-only edits) to our callback.
    #     Best-effort: if the session already closed we still extract from disk below.
    try:
        await _oo_forcesave_review_doc(review_document, db)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "persist_review_comments_now: force-save failed for %s: %s",
            review_document.id, exc,
        )

    # (2) Resolve the freshest review DOCX — re-download from Azure when blob-backed.
    rfp = review_document.review_file_path or ""
    docx_path: Optional[str] = None
    tmp_to_clean: Optional[str] = None
    if rfp.startswith("agreement_reviews/"):
        from app.utils.azure_storage import get_document_storage
        storage = get_document_storage()
        if storage:
            data = await storage.download_file(rfp)
            if data:
                t = await asyncio.to_thread(_make_named_tempfile, ".docx", data)
                docx_path = t.name
                tmp_to_clean = t.name
    elif rfp:
        docx_path = rfp

    if not docx_path or not Path(docx_path).exists():
        logger.warning(
            "persist_review_comments_now: no review DOCX available for %s "
            "(path=%r) — nothing to persist", review_document.id, rfp,
        )
        return 0

    # (3) Upsert into the caller's transaction (commit=False) for atomicity with status.
    try:
        return await _upsert_comments_from_docx(
            db=db,
            agreement_id=agreement.id,
            review_document=review_document,
            docx_path=docx_path,
            commit=commit,
        )
    finally:
        if tmp_to_clean:
            try:
                os.unlink(tmp_to_clean)
            except OSError:
                pass


@router.post("/agreements/{agreement_id}/send-for-review")
async def send_agreement_for_review(
    agreement_id: UUID,
    recipient_email: str = Form(...),
    message: Optional[str] = Form(None),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
    origin: Optional[str] = Header(None, alias="Origin"),
    referer: Optional[str] = Header(None, alias="Referer"),
):
    """
    CRM linear workflow — "Mark as Ready & Send for Review" (PREPARATION → REVIEW).

    Send agreement for review to external site.
    Creates a secure review token and sends email with review link.
    Updates agreement status to UNDER_REVIEW if currently DRAFT.
    Re-sends from UNDER_REVIEW reuse this endpoint (same implementation).
    """
    from app.integrations.smtp_service import smtp_service
    from app.modules.agreements.routes.crud import create_agreement_system_comment
    from app.utils.document_comparison import compare_documents
    
    # Get agreement
    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement_id)
        .options(selectinload(Agreement.documents))
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    # Check if user is internal
    user_id = current_user.get("user_id") if current_user else None
    is_internal = is_user_internal(user_id, db) if user_id else True
    
    if not is_internal:
        raise HTTPException(status_code=403, detail="Only internal users can send agreements for review")

    # ── Workflow guard ─────────────────────────────────────────────────────────
    # Sending for review is only valid when the agreement is still in the
    # preparation/review stage.  Once the agreement advances to
    # READY_FOR_SIGNATURE or beyond the document is locked and must not be
    # shared for external editing.
    _allowed_review_statuses = {
        AgreementStatus.DRAFT,
        AgreementStatus.UNDER_REVIEW,
        AgreementStatus.UNDER_NEGOTIATION,  # legacy compat
    }
    if agreement.status not in _allowed_review_statuses:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Cannot send for review. Agreement status is '{agreement.status.value}'. "
                "Send for Review is only allowed from DRAFT or UNDER_REVIEW."
            ),
        )
    # ── end guard ─────────────────────────────────────────────────────────────

    # Validate agreement has documents
    if not agreement.documents:
        raise HTTPException(status_code=400, detail="Agreement has no documents to review")
    
    latest_document = _latest_agreement_document(agreement.documents)
    if not latest_document.document_file_path:
        raise HTTPException(status_code=400, detail="Latest document does not have a DOCX file")

    _review_temp_src = None
    _review_doc_url = getattr(latest_document, 'document_file_url', None)
    if _review_doc_url:
        from app.utils.azure_storage import get_document_storage as _gds_rev

        _rev_storage = _gds_rev()
        if _rev_storage:
            _rev_bytes = await _rev_storage.download_file(latest_document.document_file_path)
            if _rev_bytes:
                _review_temp_src = await asyncio.to_thread(_make_named_tempfile, ".docx", _rev_bytes)
                original_file_path = Path(_review_temp_src.name)
            else:
                raise HTTPException(status_code=404, detail="Document not found in Azure")
        else:
            original_file_path = Path(latest_document.document_file_path)
            if not original_file_path.is_file():
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Document is stored in Azure but blob storage is not configured, "
                        "and the file is not available on disk at the document path."
                    ),
                )
    else:
        original_file_path = Path(latest_document.document_file_path)
        if not original_file_path.exists():
            raise HTTPException(status_code=404, detail="Original document file not found")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    review_token = AgreementReviewToken(
        agreement_id=agreement.id,
        token=token,
        recipient_email=recipient_email,
        expires_at=expires_at,
        created_by=user_id,
        is_active='true',
    )
    db.add(review_token)
    await db.flush()

    _review_temp_out = None
    try:
        _review_temp_out = await asyncio.to_thread(_make_named_tempfile, ".docx")
        temp_review_path = Path(_review_temp_out.name)

        from app.utils.docx_placeholder_replace import remove_document_protection
        try:
            remove_document_protection(original_file_path, temp_review_path)
        except Exception as e:
            logger.warning(f"Failed to remove document protection, copying file as-is: {e}")
            shutil.copy2(str(original_file_path), str(temp_review_path))

        # NOTE: comments are intentionally NOT stripped anymore. The review comment thread
        # round-trips IN the document (OnlyOffice native comments): the reviewer comments,
        # the owner sees them in OnlyOffice and Accepts (edit + resolve) or Rejects (reply
        # with a reason), and on re-send those reasons must still be in the doc so the
        # reviewer sees them. Stripping here would erase that history. (The owner's working
        # copy is the reviewed version, which carries the thread — see unified_review.respond.)

        from app.utils.azure_storage import get_document_storage as _gds_rev2, build_review_blob_name
        _rev_storage2 = _gds_rev2()
        if _rev_storage2:
            _rv_study_r = await db.execute(select(Study).where(Study.id == agreement.study_id))
            _rv_study = _rv_study_r.scalar_one_or_none()
            _rv_site_r = await db.execute(select(Site).where(Site.id == agreement.site_id))
            _rv_site = _rv_site_r.scalar_one_or_none()
            _rv_count_r = await db.execute(
                select(func.count(AgreementReviewDocument.id))
                .where(AgreementReviewDocument.agreement_id == agreement.id)
            )
            _rv_num = (_rv_count_r.scalar_one_or_none() or 0) + 1
            _rev_blob = build_review_blob_name(
                study_name=_rv_study.name if _rv_study else str(agreement.study_id),
                site_name=(_rv_site.name or _rv_site.site_id) if _rv_site else "Unknown",
                agreement_title=agreement.title,
                review_number=_rv_num,
            )
            async with aiofiles.open(temp_review_path, "rb") as f:
                _rev_out_bytes = await f.read()
            await _rev_storage2.upload_file(
                _rev_out_bytes, _rev_blob,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            review_file_path_str = _rev_blob
        else:
            review_dir = Path(settings.upload_dir) / "agreement_reviews" / str(agreement.id)
            review_dir.mkdir(parents=True, exist_ok=True)
            local_review = review_dir / f"review_{review_token.id}_{uuid.uuid4()}.docx"
            shutil.copy2(str(temp_review_path), str(local_review))
            review_file_path_str = str(local_review)
    finally:
        if _review_temp_src and Path(_review_temp_src.name).exists():
            os.unlink(_review_temp_src.name)
        if _review_temp_out and Path(_review_temp_out.name).exists():
            os.unlink(_review_temp_out.name)

    review_document = AgreementReviewDocument(
        agreement_id=agreement.id,
        review_token_id=review_token.id,
        base_version_id=latest_document.id,
        review_file_path=review_file_path_str,
        is_submitted='false',
    )
    db.add(review_document)
    await db.flush()

    logger.info(f"Created review copy for agreement {agreement_id}: {review_file_path_str} (based on version {latest_document.version_number})")
    
    # Update agreement status to UNDER_REVIEW if currently DRAFT
    if agreement.status == AgreementStatus.DRAFT:
        try:
            await change_agreement_status_service(
                db,
                str(agreement.id),
                AgreementStatus.UNDER_REVIEW,
                user_id,
            )
        except Exception as e:
            logger.warning(f"Failed to update agreement status to UNDER_REVIEW: {str(e)}")
            # Continue even if status update fails

    # (Legacy CDA workflow review-send bridge sync removed with the bridges.)

    # Create system comment
    await create_agreement_system_comment(
        db,
        agreement.id,
        None,
        f"Agreement sent for review to {recipient_email}"
    )

    # Public Notice Board entry: Agreement sent for review
    try:
        site_result = await db.execute(select(Site).where(Site.id == agreement.site_id))
        site = site_result.scalar_one_or_none()
        site_display = (site.name or site.site_id) if site else str(agreement.site_id)

        await create_agreement_notice(
            db=db,
            agreement=agreement,
            event_type="agreement_sent_for_review",
            message=(
                f"Agreement '{agreement.title}' for Site '{site_display}' "
                f"has been sent for review."
            ),
            metadata={
                "agreement_id": str(agreement.id),
                "agreement_status": agreement.status.value,
                "agreement_title": agreement.title,
            },
        )
    except Exception as e:
        logger.error(
            "Failed to create Notice Board entry for agreement %s (sent for review): %s",
            agreement.id,
            str(e),
            exc_info=True,
        )
    
    # Generate review link
    # Priority:
    # 1. FRONTEND_BASE_URL environment variable (recommended for production)
    # 2. Origin header (if FRONTEND_BASE_URL is default localhost)
    # 3. Referer header (fallback)
    # 4. Default localhost (only for local development)
    frontend_base_url = settings.frontend_base_url
    
    # If using default localhost, try to detect from Origin or Referer header
    # But only if FRONTEND_BASE_URL wasn't explicitly set (still default)
    if frontend_base_url == "http://localhost:3000":
        if origin:
            # Use the Origin header as the frontend URL
            frontend_base_url = origin
            logger.info(f"Using detected frontend URL from Origin header: {frontend_base_url}")
            logger.warning(
                f"⚠️  Frontend URL detected from Origin header: {frontend_base_url}. "
                f"For production, set FRONTEND_BASE_URL environment variable to ensure correct URLs."
            )
        elif referer:
            # Extract base URL from Referer (remove path)
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            frontend_base_url = f"{parsed.scheme}://{parsed.netloc}"
            logger.info(f"Using detected frontend URL from Referer header: {frontend_base_url}")
            logger.warning(
                f"⚠️  Frontend URL detected from Referer header: {frontend_base_url}. "
                f"For production, set FRONTEND_BASE_URL environment variable to ensure correct URLs."
            )
    else:
        logger.info(f"Using configured FRONTEND_BASE_URL: {frontend_base_url}")
    
    review_link = f"{frontend_base_url}/agreement/review/{agreement_id}?token={token}"
    logger.info(f"Generated review link: {review_link}")
    
    # Context-rich EXTERNAL notification: external reviewers reach this via a token
    # link with no in-app context, so a bare link gets ignored. Populate the body
    # generically from study/agreement metadata (Study Title, Protocol #, Document,
    # required action). Internal users are notified in-app, not through this path.
    from app.models import Study as _Study
    from app.modules.agreements.notifications import build_external_email
    _study = None
    if agreement.study_id:
        _study = (await db.execute(
            select(_Study).where(_Study.id == agreement.study_id)
        )).scalar_one_or_none()
    email_subject, email_body = build_external_email(
        agreement=agreement,
        study=_study,
        action_label="Review and respond (comment, then Approve or Send back)",
        link=review_link,
        link_label="Open the secure review page",
        message=message,
    )

    email_sent = False
    email_error = None
    try:
        from_email = getattr(settings, "smtp_user", "noreply@crm.local")
        logger.info(
            f"Sending review email: to={sfmt(recipient_email)}, from={from_email}, "
            f"smtp_host={getattr(settings, 'smtp_host', 'N/A')}, "
            f"smtp_port={getattr(settings, 'smtp_port', 'N/A')}, "
            f"smtp_user={getattr(settings, 'smtp_user', 'N/A')}"
        )
        # Enqueue rather than send inline so the route doesn't block on SMTP.
        # The Celery worker retries on failure (autoretry_for in
        # send_email_task). email_sent is optimistic — the task id presence
        # means accepted by the broker, not yet delivered.
        from app.integrations.smtp_service import enqueue_email
        task_id = enqueue_email(
            to=recipient_email,
            subject=email_subject,
            body=email_body,
            from_email=from_email,
            from_name="Clinical Trials CRM",
        )
        if task_id:
            email_sent = True
            logger.info(f"Review email enqueued (task={task_id}) for agreement {agreement_id}")
        else:
            email_error = "Broker unreachable; check Celery worker"
            logger.error(f"Failed to enqueue review email for agreement {agreement_id}")
    except Exception as e:
        email_error = str(e)
        logger.error(f"Failed to send review email: {email_error}", exc_info=True)
    
    await db.commit()
    
    response = {
        "status": "success",
        "message": "Agreement sent for review",
        "review_link": review_link,
        "token": token,
        "expires_at": expires_at.isoformat(),
        "email_sent": email_sent,
    }
    if email_error:
        response["email_error"] = email_error
        response["message"] = f"Review created but email delivery failed: {email_error}. Share the review link manually."
    
    return response


