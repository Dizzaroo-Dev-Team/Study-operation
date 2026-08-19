"""REST API: agreement review submission + save-review-document + latest-saved-review.

The 480-line submit_review endpoint is the largest in this cluster -- it
applies the OnlyOffice-extracted DOCX changes back to the agreement after
the external reviewer signs and returns the document.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
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
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import schemas
from app.auth import get_current_user_optional
from app.config import settings
from app.db import get_db
from app.models import (
    Agreement,
    AgreementChange,
    AgreementDocument,
    AgreementInlineComment,
    AgreementReviewDocument,
    AgreementReviewerSignature,
    AgreementReviewToken,
    AgreementSignedDocument,
    AgreementStatus,
    AgreementStatus as AgreementStatusEnum,
    Site,
)
from app.modules.agreements.services.agreement_service import create_agreement_notice
from app.modules.agreements.aggregator import (
    _promote_review_file_to_agreement_document,
)
from app.modules.agreements.routes.signing import (
    _oo_forcesave_review_doc,
    _upsert_comments_from_docx,
)
from app.modules.agreements.routes.crud import create_agreement_system_comment
from app.modules.agreements.services.agreement_service import create_agreement_notice

AgreementStatusEnum = AgreementStatus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Legal Documents"])


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


# Lazy import: helpers that still live in the legacy file (parsing, save-doc context, etc.)
def _legacy_get_active_review_context(*args, **kwargs):
    from app.modules.agreements.aggregator import _get_active_review_context
    return _get_active_review_context(*args, **kwargs)


async def _oo_forcesave_review_doc(review_document, db) -> bool:
    from app.modules.agreements.routes.signing import _oo_forcesave_review_doc as _fn
    return await _fn(review_document, db)


async def _upsert_comments_from_docx(*args, **kwargs):
    from app.modules.agreements.routes.signing import _upsert_comments_from_docx as _fn
    return await _fn(*args, **kwargs)


async def _promote_review_file_to_agreement_document(*args, **kwargs):
    from app.modules.agreements.aggregator import _promote_review_file_to_agreement_document as _fn
    return await _fn(*args, **kwargs)


@router.options("/agreements/{agreement_id}/submit-review")
async def submit_review_options(agreement_id: UUID):
    """Handle CORS preflight requests for submit-review endpoint."""
    from fastapi.responses import Response
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
    )


@router.post("/agreements/{agreement_id}/submit-review")
async def submit_review_changes(
    agreement_id: UUID,
    token: str = Form(...),
    document_file: Optional[UploadFile] = File(None),  # Optional - can be edited via OnlyOffice without upload
    message: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit reviewed/edited document from external site.

    Compares with previous version, detects changes, and stores them.
    Creates new document version.
    """
    from app.utils.document_comparison import compare_documents, DocumentChange
    from app.modules.agreements.routes.crud import create_agreement_system_comment
    
    # CORS headers for all responses (success and error)
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }
    
    try:
        # Validate token
        token_result = await db.execute(
            select(AgreementReviewToken)
            .where(AgreementReviewToken.token == token)
            .where(AgreementReviewToken.agreement_id == agreement_id)
            .where(AgreementReviewToken.is_active == 'true')
        )
        review_token = token_result.scalar_one_or_none()
        
        if not review_token:
            raise HTTPException(
                status_code=404,
                detail="Invalid or expired review token",
                headers=cors_headers
            )
        
        if review_token.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=403,
                detail="Review token has expired",
                headers=cors_headers
            )
        
        # Get agreement with documents
        agreement_result = await db.execute(
            select(Agreement)
            .where(Agreement.id == agreement_id)
            .options(selectinload(Agreement.documents))
        )
        agreement = agreement_result.scalar_one_or_none()
        
        if not agreement:
            raise HTTPException(
                status_code=404,
                detail="Agreement not found",
                headers=cors_headers
            )

        # ── Workflow guard ──────────────────────────────────────────────────
        # Submissions are only accepted while the agreement is in the review
        # stage.  Reject any submission once the agreement has moved to
        # READY_FOR_SIGNATURE or beyond.
        _allowed_submit_statuses = {
            AgreementStatusEnum.UNDER_REVIEW,
            AgreementStatusEnum.UNDER_NEGOTIATION,  # legacy compat
        }
        if agreement.status not in _allowed_submit_statuses:
            logger.warning(
                "Review submission blocked for agreement %s: status is %s",
                agreement_id,
                agreement.status.value,
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    "This agreement is no longer accepting review submissions. "
                    "The review period has ended."
                ),
                headers=cors_headers,
            )
        # ── end guard ──────────────────────────────────────────────────────

        # Get review document for this token
        review_doc_result = await db.execute(
            select(AgreementReviewDocument)
            .where(AgreementReviewDocument.review_token_id == review_token.id)
            .where(AgreementReviewDocument.is_submitted == 'false')
            .options(selectinload(AgreementReviewDocument.base_version))
        )
        review_document = review_doc_result.scalar_one_or_none()
        
        if not review_document:
            raise HTTPException(
                status_code=404,
                detail="Review document not found. The review may have already been submitted.",
                headers=cors_headers
            )
        
        # Get the base version (main document this review copy was created from)
        base_version = review_document.base_version
        if not base_version or not base_version.document_file_path:
            raise HTTPException(
                status_code=400,
                detail="Base document version not found",
                headers=cors_headers
            )
        
        # Use the review document file (which may have been edited via OnlyOffice) or uploaded file
        # If OnlyOffice was used, the review document file should already be updated
        # If file upload is used, use the uploaded file
        temp_file_path = None
        _sr_temp_review = None
        
        # Prefer the newest snapshot: explicit "Save Document" blob vs. working review file.
        _dt_rev = review_document.updated_at or datetime.min.replace(tzinfo=timezone.utc)
        _dt_saved = review_document.saved_at
        _prefer_saved = (
            review_document.saved_review_path
            and review_document.saved_review_url
            and _dt_saved is not None
            and _dt_saved >= _dt_rev
        )
        if _prefer_saved:
            logger.info(f"Using saved review document (newer than working copy): {review_document.saved_review_path}")
            _rfp_raw = review_document.saved_review_path
            from app.utils.azure_storage import get_document_storage as _gds_sr2
            _sr_storage2 = _gds_sr2()
            if _sr_storage2:
                _sr_rev_bytes = await _sr_storage2.download_file(_rfp_raw)
                if _sr_rev_bytes:
                    _sr_temp_review = await asyncio.to_thread(_make_named_tempfile, ".docx", _sr_rev_bytes)
                    review_file_path = Path(_sr_temp_review.name)
                    logger.info(f"Downloaded saved review document: {review_file_path} (size={len(_sr_rev_bytes)} bytes)")
                else:
                    raise HTTPException(status_code=404, detail="Saved review document not found in Azure", headers=cors_headers)
            else:
                raise HTTPException(status_code=500, detail="Azure storage not configured", headers=cors_headers)
        else:
            # Use the original review document path
            _rfp_raw = review_document.review_file_path
            from app.utils.azure_storage import get_document_storage as _gds_sr2
            _sr_storage2 = _gds_sr2()
            if _sr_storage2 and _rfp_raw and _rfp_raw.startswith("agreement_reviews/"):
                _sr_rev_bytes = await _sr_storage2.download_file(_rfp_raw)
                if _sr_rev_bytes:
                    _sr_temp_review = await asyncio.to_thread(_make_named_tempfile, ".docx", _sr_rev_bytes)
                    review_file_path = Path(_sr_temp_review.name)
                else:
                    raise HTTPException(status_code=404, detail="Review document not found in Azure", headers=cors_headers)
            else:
                review_file_path = Path(_rfp_raw)

        logger.info(f"Submit review - review_document_id={review_document.id}, review_file_path={review_file_path}, file_exists={review_file_path.exists() if review_file_path.exists() else False}")
        if review_file_path.exists():
            file_stat = review_file_path.stat()
            logger.info(f"Review document file stats - size={file_stat.st_size}, modified={datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc)}, updated_at={review_document.updated_at}")
        
        # If file is uploaded, use it; otherwise try to download from OnlyOffice or use the review document file
        if document_file and document_file.filename:
            # Save uploaded file temporarily
            temp_dir = Path(settings.upload_dir) / "temp_reviews"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file_path = temp_dir / f"review_{agreement_id}_{uuid4()}.docx"
            
            async with aiofiles.open(temp_file_path, "wb") as f:
                content = await document_file.read()
                await f.write(content)
            
            logger.info(f"Using uploaded file for comparison: {temp_file_path} (size={len(content)} bytes)")
            # Use uploaded file for comparison
            review_file_path = temp_file_path
        else:
            # No file uploaded — use the review document file.
            # ── STEP A: Use OO Command Service to force-save the session ─────
            # When permissions.edit=false (comment-only mode) OnlyOffice may
            # never fire its normal auto-save callback.  We explicitly tell
            # the OO Document Server to flush its in-memory session (including
            # all comments) to our callback endpoint right now.
            # This runs before we read the file so we get the freshest DOCX.
            logger.info(
                "submit-review: calling OO Command Service to force-save "
                "review_document %s before comment extraction",
                review_document.id,
            )
            oo_flushed = await _oo_forcesave_review_doc(review_document, db)
            if oo_flushed:
                logger.info(
                    "submit-review: OO forcesave confirmed — "
                    "review_document %s was updated on disk by callback",
                    review_document.id,
                )
                _rfp_fresh = review_document.review_file_path
                if _sr_storage2 and _rfp_fresh and _rfp_fresh.startswith("agreement_reviews/"):
                    if _sr_temp_review and Path(_sr_temp_review.name).exists():
                        os.unlink(_sr_temp_review.name)
                    _fresh_bytes = await _sr_storage2.download_file(_rfp_fresh)
                    if _fresh_bytes:
                        _sr_temp_review = await asyncio.to_thread(_make_named_tempfile, ".docx", _fresh_bytes)
                        review_file_path = Path(_sr_temp_review.name)
                    else:
                        logger.warning("Could not re-download review doc from Azure after forcesave")
                else:
                    review_file_path = Path(review_document.review_file_path)
            else:
                logger.warning(
                    "submit-review: OO forcesave did not confirm update for "
                    "review_document %s — extracting from whatever is on disk",
                    review_document.id,
                )

            logger.info(f"Using review document file for comparison: {review_file_path}")

        if not review_file_path.exists():
            raise HTTPException(
                status_code=404,
                detail="Review document file not found",
                headers=cors_headers
            )
        
        _sr_temp_base = None
        _sr_base_url = getattr(base_version, 'document_file_url', None)
        if _sr_base_url:
            from app.utils.azure_storage import get_document_storage as _gds_sr
            _sr_storage = _gds_sr()
            if _sr_storage:
                _sr_base_bytes = await _sr_storage.download_file(base_version.document_file_path)
                if _sr_base_bytes:
                    _sr_temp_base = await asyncio.to_thread(_make_named_tempfile, ".docx", _sr_base_bytes)
                    original_path = Path(_sr_temp_base.name)
                else:
                    raise HTTPException(status_code=404, detail="Base document not found in Azure", headers=cors_headers)
            else:
                raise HTTPException(status_code=500, detail="Azure storage not configured", headers=cors_headers)
        else:
            original_path = Path(base_version.document_file_path)
            if not original_path.exists():
                raise HTTPException(status_code=404, detail="Base document file not found", headers=cors_headers)
        
        logger.info(f"Comparing documents - original: {original_path}, review: {review_file_path}")
        
        # Log file sizes for debugging
        if original_path.exists() and review_file_path.exists():
            orig_size = original_path.stat().st_size
            review_size = review_file_path.stat().st_size
            logger.info(f"File sizes - original: {orig_size} bytes, review: {review_size} bytes, difference: {review_size - orig_size} bytes")
        
        changes = compare_documents(original_path, review_file_path)
        logger.info(f"Document comparison result: {len(changes)} changes detected")
        
        # Log first few changes for debugging
        if changes:
            for i, change in enumerate(changes[:5]):  # Log first 5 changes
                logger.info(f"Change {i+1}: {change.change_type} - old_text length: {len(change.old_text) if change.old_text else 0}, new_text length: {len(change.new_text) if change.new_text else 0}")
        else:
            logger.warning("No changes detected - this might indicate a comparison issue. Files may be identical or comparison logic needs improvement.")
        
        # IMPORTANT: Do NOT create a new main document version here.
        # External reviewers edit review copies, not main documents.
        # The main document is only updated when internal users accept changes.
        
        # If file was uploaded, update the review document file
        if document_file and document_file.filename and review_file_path != Path(review_document.review_file_path):
            # Copy uploaded file to review document location
            review_doc_dir = Path(review_document.review_file_path).parent
            review_doc_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(review_file_path), review_document.review_file_path)
        
        # ── Comment extraction safety net ────────────────────────────────────
        # The OnlyOffice callback already calls _upsert_comments_from_docx on
        # every auto-save (status 2/6).  However, if the reviewer adds a
        # comment and immediately clicks "Submit Review" before the next
        # auto-save cycle fires, those last comments would be lost.
        # Extracting here guarantees all comments from the current file are
        # in the DB before the review document is locked as submitted.
        _review_document_id = review_document.id
        _base_version_id = base_version.id

        async def _reload_submit_context() -> None:
            nonlocal review_document, base_version, agreement
            review_document = (
                await db.execute(
                    select(AgreementReviewDocument)
                    .where(AgreementReviewDocument.id == _review_document_id)
                    .options(selectinload(AgreementReviewDocument.base_version))
                )
            ).scalar_one()
            base_version = review_document.base_version
            if base_version is None:
                base_version = (
                    await db.execute(
                        select(AgreementDocument).where(
                            AgreementDocument.id == _base_version_id
                        )
                    )
                ).scalar_one()
            agreement = (
                await db.execute(
                    select(Agreement)
                    .where(Agreement.id == agreement_id)
                    .options(selectinload(Agreement.documents))
                )
            ).scalar_one()

        try:
            await _upsert_comments_from_docx(
                db=db,
                agreement_id=agreement_id,
                review_document=review_document,
                docx_path=str(review_file_path),
            )
            logger.info(
                "Comment extraction at submit time completed for "
                "review_document %s",
                _review_document_id,
            )
            try:
                await _reload_submit_context()
            except Exception as reload_err:
                logger.warning(
                    "Failed to reload ORM objects after comment extraction commit: %s",
                    reload_err,
                )
        except Exception as _comment_err:
            # Rollback so the session is usable for the "mark submitted" step.
            # A comment extraction failure must NEVER prevent the review from
            # being submitted — comments can be re-extracted on demand.
            try:
                await db.rollback()
                await _reload_submit_context()
            except Exception as reload_err:
                logger.warning(
                    "Failed to reload ORM objects after comment extraction rollback: %s",
                    reload_err,
                )
            logger.warning(
                "Comment extraction at submit time failed for "
                "review_document %s: %s",
                _review_document_id,
                _comment_err,
                exc_info=True,
            )
        # ── end comment extraction ───────────────────────────────────────────

        # Promote reviewed DOCX onto the **base_version** AgreementDocument row (not
        # "latest" across versions — avoids refresh loading an older version file).
        _review_bytes_len = review_file_path.stat().st_size if review_file_path.exists() else 0
        logger.info(
            "submit-review: reviewer file for promote path=%s size=%s bytes base_document_id=%s v=%s",
            review_file_path,
            _review_bytes_len,
            base_version.id,
            base_version.version_number,
        )
        try:
            _promo_path, _promo_url = await _promote_review_file_to_agreement_document(
                db, agreement, base_version, review_file_path
            )
            logger.info(
                "submit-review: active main document after submit document_id=%s path=%s (must match document-file/onlyoffice on refresh)",
                base_version.id,
                _promo_path,
            )
        except Exception as promo_err:
            logger.error(
                "submit-review: promote to main agreement document failed: %s",
                promo_err,
                exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to update main document from review submission.",
                headers=cors_headers,
            )

        # Mark review document as submitted
        review_document.is_submitted = 'true'
        review_document.submitted_at = datetime.now(timezone.utc)
        await db.flush()

        # (Removed) Legacy CTA negotiation-round close: AgreementNegotiationRound is
        # deprecated and `mark_negotiation_round_submitted` was never defined — the
        # import here always raised and was swallowed, so this was a dead no-op. Dropped
        # to sever shared review code's dependency on the legacy CTA type module.

        # Store changes (comparing review copy with base main document version)
        # Changes reference the base_version, not a new main document version
        # The main document is NOT updated here - only when internal users accept changes
        site_email = review_token.created_by  # Could be enhanced to store site email
        for change in changes:
            change_record = AgreementChange(
                agreement_id=agreement.id,
                document_version_id=base_version.id,  # Reference base version, not a new version
                previous_version_id=base_version.id,  # Same as document_version_id (changes detected vs base)
                change_type=change.change_type,
                section_reference=change.section_reference,
                old_text=change.old_text,
                new_text=change.new_text,
                paragraph_index=change.paragraph_index,
                table_index=change.table_index,
                row_index=change.row_index,
                cell_index=change.cell_index,
                created_by=site_email or "external_user",
                is_external_change='true',
                is_accepted='false',
            )
            db.add(change_record)
        
        # Note: Do NOT update agreement status here.
        # Status remains UNDER_REVIEW until internal users review and accept/reject changes.
        # The status will change when internal users take action (accept changes, send again, etc.)
        
        # Create system comment
        changes_summary = f"{len(changes)} change(s) detected"
        if changes:
            change_types = {}
            for c in changes:
                change_types[c.change_type] = change_types.get(c.change_type, 0) + 1
            changes_summary += f": {', '.join([f'{count} {ctype.lower()}' for ctype, count in change_types.items()])}"
        
        await create_agreement_system_comment(
            db,
            agreement.id,
            None,
            f"Review submitted by external site. {changes_summary}. Review copy compared with base version {base_version.version_number}."
        )

        # Public Notice Board entry: Review submitted / comments received
        try:
            site_result = await db.execute(select(Site).where(Site.id == agreement.site_id))
            site = site_result.scalar_one_or_none()
            site_display = (site.name or site.site_id) if site else str(agreement.site_id)

            await create_agreement_notice(
                db=db,
                agreement=agreement,
                event_type="review_submitted",
                message=(
                    f"Agreement '{agreement.title}' for Site '{site_display}' "
                    f"has received reviewer comments."
                ),
                metadata={
                    "agreement_id": str(agreement.id),
                    "agreement_status": agreement.status.value,
                    "agreement_title": agreement.title,
                    "changes_detected": len(changes),
                },
            )
        except Exception as e:
            logger.error(
                "Failed to create Notice Board entry for agreement %s (review submitted): %s",
                agreement.id,
                str(e),
                exc_info=True,
            )

        await db.commit()
        
        if '_sr_temp_review' in locals() and _sr_temp_review and Path(_sr_temp_review.name).exists():
            os.unlink(_sr_temp_review.name)
        if '_sr_temp_base' in locals() and _sr_temp_base and Path(_sr_temp_base.name).exists():
            os.unlink(_sr_temp_base.name)

        return JSONResponse(
            content={
                "status": "success",
                "message": "Review submitted successfully",
                "changes_detected": len(changes),
                "base_version_number": base_version.version_number,
            },
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            }
        )

    except HTTPException as http_err:
        # Re-raise HTTP exceptions with CORS headers (if not already set)
        if not http_err.headers or "Access-Control-Allow-Origin" not in http_err.headers:
            raise HTTPException(
                status_code=http_err.status_code,
                detail=http_err.detail,
                headers=cors_headers
            )
        raise
    except Exception as e:
        if 'temp_file_path' in locals() and temp_file_path and temp_file_path.exists():
            try:
                temp_file_path.unlink()
            except Exception:
                pass
        if '_sr_temp_review' in locals() and _sr_temp_review and Path(_sr_temp_review.name).exists():
            try:
                os.unlink(_sr_temp_review.name)
            except Exception:
                pass
        if '_sr_temp_base' in locals() and _sr_temp_base and Path(_sr_temp_base.name).exists():
            try:
                os.unlink(_sr_temp_base.name)
            except Exception:
                pass
        logger.error(f"Error submitting review: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit review: {str(e)}",
            headers=cors_headers
        )


# ============================================================================
# REVIEW DOCUMENT SAVE FUNCTIONALITY
# ============================================================================

@router.post("/agreements/{agreement_id}/save-review-document")
async def save_review_document(
    agreement_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Save the current state of a review document (including comments) to Azure Blob Storage.
    
    This endpoint:
    - Captures the current state of the document with all comments
    - Uploads it to a separate review-documents folder in Azure Blob Storage
    - Uses unique naming (timestamp/UUID) to maintain versions
    - Does NOT overwrite the original file
    - Returns the URL of the saved document for later retrieval
    
    Used by the "Save Document" button in the review interface.
    """
    # Get agreement with review documents
    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement_id)
        .options(selectinload(Agreement.review_documents))
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    # Active (not yet submitted) review copy — same as OnlyOffice session.
    _rd_res = await db.execute(
        select(AgreementReviewDocument)
        .where(AgreementReviewDocument.agreement_id == agreement_id)
        .where(AgreementReviewDocument.is_submitted == "false")
        .order_by(AgreementReviewDocument.created_at.desc())
    )
    latest_review_doc = _rd_res.scalars().first()

    if not latest_review_doc:
        raise HTTPException(
            status_code=404, 
            detail="No review document found. Please start a review first."
        )
    
    # Force save the current state from OnlyOffice before downloading
    logger.info(
        "save-review-document: calling OO Command Service to force-save "
        "review_document %s before saving to Azure",
        latest_review_doc.id,
    )
    oo_flushed = await _oo_forcesave_review_doc(latest_review_doc, db)
    
    # Get the current file content
    review_file_path = None
    if latest_review_doc.review_file_path and latest_review_doc.review_file_path.startswith("agreement_reviews/"):
        # Download from Azure
        from app.utils.azure_storage import get_document_storage as _gds_save
        save_storage = _gds_save()
        if save_storage:
            try:
                file_bytes = await save_storage.download_file(latest_review_doc.review_file_path)
                if not file_bytes:
                    raise HTTPException(status_code=404, detail="Review document not found in Azure")
            except Exception as e:
                logger.exception(f"Failed to download review document from Azure: {e}")
                raise HTTPException(status_code=500, detail="Failed to download review document")
        else:
            raise HTTPException(status_code=500, detail="Azure storage not configured")
    else:
        # Use local file
        review_file_path = Path(latest_review_doc.review_file_path)
        if not review_file_path.exists():
            raise HTTPException(status_code=404, detail="Review document file not found on disk")
        
        # Read file content
        async with aiofiles.open(review_file_path, 'rb') as f:
            file_bytes = await f.read()
    
    # Upload to Azure Blob Storage in review-documents folder
    from app.utils.azure_storage import get_document_storage as _gds_upload
    upload_storage = _gds_upload()
    
    if not upload_storage:
        raise HTTPException(status_code=500, detail="Azure storage not configured")
    
    # Generate unique filename with timestamp and UUID
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid4())[:8]
    
    # Use the new blob naming function
    from app.utils.azure_storage import build_review_save_blob_name
    blob_path = build_review_save_blob_name(
        agreement_id=str(agreement_id),
        timestamp=timestamp,
        unique_id=unique_id
    )
    
    try:
        _cmt_file = None
        # Upload to Azure
        await upload_storage.upload_file(file_bytes, blob_path)
        
        # Get the URL of the uploaded file
        file_url = await upload_storage.get_file_url(blob_path)
        
        # Update the review document with the saved file info
        latest_review_doc.saved_review_url = file_url
        latest_review_doc.saved_review_path = blob_path
        latest_review_doc.saved_at = datetime.now(timezone.utc)
        
        await db.commit()
        
        # Ensure newly added reviewer comments are also persisted to the DB.
        # This makes the external comment panel immediately reflect the
        # current review cycle (it relies on agreement_document_comments).
        try:
            _cmt_file = await asyncio.to_thread(_make_named_tempfile, ".docx", file_bytes)

            await _upsert_comments_from_docx(
                db=db,
                agreement_id=agreement_id,
                review_document=latest_review_doc,
                docx_path=_cmt_file.name,
            )
        except Exception as _comment_err:
            logger.warning(
                "save-review-document: comment extraction failed for review_document %s: %s",
                latest_review_doc.id,
                _comment_err,
                exc_info=True,
            )
        finally:
            try:
                if _cmt_file and Path(_cmt_file.name).exists():
                    os.unlink(_cmt_file.name)
            except Exception:
                pass

        logger.info(
            f"Review document saved: agreement_id={agreement_id}, "
            f"review_document_id={latest_review_doc.id}, blob_path={blob_path}"
        )
        
        return {
            "success": True,
            "message": "Review document saved successfully",
            "file_url": file_url,
            "blob_path": blob_path,
            "saved_at": latest_review_doc.saved_at,
            "review_document_id": latest_review_doc.id
        }
        
    except Exception as e:
        logger.error(f"Failed to save review document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save review document: {str(e)}")


@router.get("/agreements/{agreement_id}/latest-saved-review")
async def get_latest_saved_review(
    agreement_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the latest saved review document for rendering in OnlyOffice.
    
    This endpoint:
    - Retrieves the most recently saved review document
    - Returns the file URL and metadata for OnlyOffice configuration
    - Ensures the document.key is updated to avoid cache issues
    
    Used by the "Submit Review" functionality to load the latest saved version.
    """
    # Get agreement with review documents
    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement_id)
        .options(selectinload(Agreement.review_documents))
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    # Find the review document with the most recent save
    latest_saved_doc = None
    latest_save_time = None
    
    for review_doc in agreement.review_documents:
        if review_doc.saved_review_url and review_doc.saved_at:
            if latest_save_time is None or review_doc.saved_at > latest_save_time:
                latest_save_time = review_doc.saved_at
                latest_saved_doc = review_doc
    
    if not latest_saved_doc:
        raise HTTPException(
            status_code=404, 
            detail="No saved review document found. Please save a review document first."
        )
    
    # Generate a unique key for OnlyOffice to avoid cache issues
    document_key = f"review_{agreement_id}_{latest_saved_doc.id}_{int(latest_saved_doc.saved_at.timestamp())}"
    
    return {
        "success": True,
        "file_url": latest_saved_doc.saved_review_url,
        "document_key": document_key,
        "saved_at": latest_saved_doc.saved_at,
        "review_document_id": latest_saved_doc.id,
        "file_type": "docx"
    }

