"""REST API: OTP-based signing flow.

Six endpoints making up the e-signature OTP challenge/response loop:
  POST /auth/send-otp              -- reviewer flow start
  POST /document/sign-with-otp     -- reviewer flow commit
  POST /auth/send-sign-otp         -- site flow start
  POST /agreement/sign             -- site flow commit
  POST /auth/send-site-sign-otp    -- variant for site signer
  POST /agreement/site-sign-with-otp

NOTE: This cluster is signing-fragile (PII + legal exposure). The plan calls
for a parallel-rewrite + feature-flag rollout when meaningfully refactoring
its internals. This file is a one-to-one relocation -- byte-identical
behaviour preserved via verbatim extraction.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


async def _atomic_increment_otp_attempts(db: AsyncSession, otp_model, otp_id) -> int:
    """
    Atomically increment the attempts counter on an OTP row and return the new
    value. Replaces the read-modify-write pattern that races under concurrent
    wrong-guess submissions.
    """
    result = await db.execute(
        update(otp_model)
        .where(otp_model.id == otp_id)
        .values(attempts=otp_model.attempts + 1)
        .returning(otp_model.attempts)
    )
    new_value = result.scalar_one()
    return int(new_value or 0)


async def _invalidate_active_otps(db: AsyncSession, otp_model, *filters) -> None:
    """
    Mark every still-active OTP matching `filters` as inactive. Called by every
    OTP send endpoint immediately before inserting a fresh code so that earlier
    codes for the same recipient cannot be brute-forced in parallel with the
    new one (defense against the per-record attempt counter being reset on
    resend).
    """
    await db.execute(
        update(otp_model)
        .where(*filters)
        .where(otp_model.is_active == 'true')
        .where(otp_model.consumed_at.is_(None))
        .values(is_active='false')
    )

from app import schemas
from app.auth import get_current_user, get_current_user_optional
from app.config import settings
from app.db import get_db
from app.models import (
    Agreement,
    AgreementChange,
    AgreementDocument,
    AgreementDocumentComment,
    AgreementInlineComment,
    AgreementInternalSignature,
    AgreementReviewDocument,
    AgreementReviewerSignature,
    AgreementReviewOtp,
    AgreementReviewToken,
    AgreementSignatureSource,
    AgreementSigningOtp,
    AgreementSigningToken,
    AgreementStatus,
    AgreementStatus as AgreementStatusEnum,
    AuditLog,
)
from app.modules.agreements.services.agreement_service import (
    change_agreement_status as change_agreement_status_service,
    is_user_internal,
)
from app.modules.agreements.aggregator import (
    OTP_EXPIRY_MINUTES,
    OTP_MAX_ATTEMPTS,
    OTP_MEANING,
    OTP_RESEND_COOLDOWN_SECONDS,
    SITE_SIGN_MEANING,
    _append_signature_to_docx_and_create_signed_version,
    _extract_request_ip,
    _get_active_review_context,
    _get_active_signing_context,
    _get_review_document_local_path,
    _hash_otp_value,
    _latest_agreement_document,
    _document_for_signature_apply,
)
from app.modules.agreements.routes.signing import (
    _oo_forcesave_review_doc,
    _upsert_comments_from_docx,
)
from app.integrations.smtp_service import smtp_service

AgreementStatusEnum = AgreementStatus
OTP_EXPIRY_MINUTES = 5
OTP_RESEND_COOLDOWN_SECONDS = 30
OTP_MEANING = "Reviewed & Approved"
SITE_SIGN_MEANING = "Signed & Approved"

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


def _legacy(name):
    import app.modules.agreements.aggregator as _ld
    return getattr(_ld, name)


def _hash_otp_value(otp: str) -> str:
    return _legacy("_hash_otp_value")(otp)


def _extract_request_ip(request: Request) -> Optional[str]:
    return _legacy("_extract_request_ip")(request)


OTP_MAX_ATTEMPTS = 5  # mirrors aggregator.OTP_MAX_ATTEMPTS


async def _get_active_review_context(*args, **kwargs):
    return await _legacy("_get_active_review_context")(*args, **kwargs)


async def _get_active_signing_context(*args, **kwargs):
    return await _legacy("_get_active_signing_context")(*args, **kwargs)


async def _get_review_document_local_path(*args, **kwargs):
    return await _legacy("_get_review_document_local_path")(*args, **kwargs)


async def _append_signature_to_docx_and_create_signed_version(*args, **kwargs):
    return await _legacy("_append_signature_to_docx_and_create_signed_version")(*args, **kwargs)


async def _oo_forcesave_review_doc(review_document, db) -> bool:
    from app.modules.agreements.routes.signing import _oo_forcesave_review_doc as _fn
    return await _fn(review_document, db)


async def _upsert_comments_from_docx(*args, **kwargs):
    from app.modules.agreements.routes.signing import _upsert_comments_from_docx as _fn
    return await _fn(*args, **kwargs)


async def _count_substantive_review_comments(db, review_document_id):
    from app.modules.agreements.routes.signing import count_substantive_review_comments as _fn
    return await _fn(db, review_document_id)


def _count_substantive_comments_in_docx(docx_path: str) -> int:
    from app.modules.agreements.routes.signing import count_substantive_comments_in_docx as _fn
    return _fn(docx_path)


@router.post("/auth/send-otp")
async def send_reviewer_otp(
    payload: schemas.AgreementOtpSendRequest,
    db: AsyncSession = Depends(get_db),
):
    agreement, review_token, review_document = await _get_active_review_context(
        db, payload.agreement_id, payload.token
    )
    logger.info("Routing agreement %s through internal reviewer OTP flow", agreement.id)

    recipient_email = (review_token.recipient_email or "").strip()
    if not recipient_email:
        raise HTTPException(
            status_code=400,
            detail="Reviewer email is not available for this review token.",
        )

    latest_otp_result = await db.execute(
        select(AgreementReviewOtp)
        .where(AgreementReviewOtp.review_token_id == review_token.id)
        .order_by(AgreementReviewOtp.created_at.desc())
    )
    latest_otp = latest_otp_result.scalars().first()
    now = datetime.now(timezone.utc)
    if latest_otp and latest_otp.last_sent_at and latest_otp.last_sent_at > now - timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS):
        retry_after = OTP_RESEND_COOLDOWN_SECONDS - int((now - latest_otp.last_sent_at).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {max(retry_after, 1)} seconds before requesting a new OTP.",
        )

    # Invalidate any earlier active OTPs for this review token so a resend
    # cannot grant a fresh 5-attempt brute-force window in parallel with the
    # old one. (Defense for O2 from the audit.)
    await _invalidate_active_otps(
        db,
        AgreementReviewOtp,
        AgreementReviewOtp.review_token_id == review_token.id,
    )

    otp_value = f"{secrets.randbelow(1_000_000):06d}"
    otp_record = AgreementReviewOtp(
        agreement_id=agreement.id,
        review_token_id=review_token.id,
        document_id=review_document.base_version_id,
        email=recipient_email,
        otp_hash=_hash_otp_value(otp_value),
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        attempts=0,
        last_sent_at=now,
        is_active='true',
    )
    db.add(otp_record)

    email_subject = f"Your OTP for {agreement.title}"
    email_body = (
        f"Your one-time password for signing agreement '{agreement.title}' is {otp_value}.\n\n"
        f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n"
        f"If you did not request this, you can ignore this email."
    )
    from app.integrations.smtp_service import smtp_service
    from_email = getattr(settings, "smtp_user", "noreply@crm.local")
    # Async send so this in-flow OTP route doesn't block the FastAPI event
    # loop during the SMTP handshake (~1-5s on each call). Same dict shape
    # back so the success-check below is unchanged.
    result = await smtp_service.send_email_async(
        to=recipient_email,
        subject=email_subject,
        body=email_body,
        from_email=from_email,
        from_name="Clinical Trials CRM",
    )
    if not result.get("success"):
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Failed to send OTP email."),
        )

    await db.commit()
    return {
        "status": "success",
        "message": "OTP sent successfully.",
        "expires_in_seconds": OTP_EXPIRY_MINUTES * 60,
        "resend_cooldown_seconds": OTP_RESEND_COOLDOWN_SECONDS,
        "email": recipient_email,
    }


@router.post("/document/sign-with-otp")
async def sign_review_with_otp(
    payload: schemas.AgreementOtpSignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from app.modules.agreements.routes.crud import create_agreement_system_comment, create_agreement_notice_board_entry
    agreement, review_token, review_document = await _get_active_review_context(
        db, payload.agreement_id, payload.token
    )
    logger.info("Processing internal reviewer OTP signature for agreement %s", agreement.id)

    otp_result = await db.execute(
        select(AgreementReviewOtp)
        .where(AgreementReviewOtp.review_token_id == review_token.id)
        .where(AgreementReviewOtp.is_active == 'true')
        .where(AgreementReviewOtp.consumed_at.is_(None))
        .order_by(AgreementReviewOtp.created_at.desc())
    )
    otp_record = otp_result.scalars().first()
    if not otp_record:
        raise HTTPException(status_code=404, detail="No active OTP challenge found.")

    now = datetime.now(timezone.utc)
    if otp_record.expires_at < now:
        otp_record.is_active = 'false'
        await db.commit()
        raise HTTPException(status_code=403, detail="OTP has expired.")

    if otp_record.attempts >= OTP_MAX_ATTEMPTS:
        otp_record.is_active = 'false'
        await db.commit()
        raise HTTPException(status_code=429, detail="Too many invalid OTP attempts.")

    submitted_otp = (payload.otp or "").strip()
    if not submitted_otp:
        raise HTTPException(status_code=400, detail="OTP is required.")

    if not hmac.compare_digest(otp_record.otp_hash, _hash_otp_value(submitted_otp)):
        new_attempts = await _atomic_increment_otp_attempts(
            db, AgreementReviewOtp, otp_record.id,
        )
        if new_attempts >= OTP_MAX_ATTEMPTS:
            await db.execute(
                update(AgreementReviewOtp)
                .where(AgreementReviewOtp.id == otp_record.id)
                .values(is_active='false')
            )
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    temp_review = None
    try:
        oo_flushed = await _oo_forcesave_review_doc(review_document, db)
        if oo_flushed:
            await asyncio.sleep(2)
            agreement, review_token, review_document = await _get_active_review_context(
                db, payload.agreement_id, payload.token
            )

        review_file_path, temp_review = await _get_review_document_local_path(review_document)

        # Block OTP sign-off when the saved DOCX (or DB) has real review comments.
        # Check DOCX before upsert so empty OO placeholders do not commit then 400.
        substantive_in_docx = _count_substantive_comments_in_docx(str(review_file_path))
        substantive_in_db = await _count_substantive_review_comments(db, review_document.id)
        if substantive_in_docx > 0 or substantive_in_db > 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "This review contains comments. Remove them in the editor or use "
                    '"Submit Review" instead of signing with OTP.'
                ),
            )

        try:
            await _upsert_comments_from_docx(
                db=db,
                agreement_id=agreement.id,
                review_document=review_document,
                docx_path=str(review_file_path),
                commit=False,
            )
        except Exception as comment_err:
            logger.warning(
                "OTP sign flow comment extraction failed for review_document %s: %s",
                review_document.id,
                comment_err,
                exc_info=True,
            )
            await db.rollback()
            agreement, review_token, review_document = await _get_active_review_context(
                db, payload.agreement_id, payload.token
            )
            otp_result = await db.execute(
                select(AgreementReviewOtp).where(AgreementReviewOtp.id == otp_record.id)
            )
            otp_record = otp_result.scalar_one()

        base_version = review_document.base_version
        if not base_version:
            raise HTTPException(status_code=400, detail="Base document version not found")

        async with aiofiles.open(review_file_path, "rb") as doc_file:
            doc_bytes = await doc_file.read()
        document_hash = hashlib.sha256(doc_bytes).hexdigest()

        signature_timestamp_display = now.strftime("%Y-%m-%d %H:%M:%S UTC")
        signature_document = base_version
        try:
            signature_document = await _append_signature_to_docx_and_create_signed_version(
                db=db,
                agreement=agreement,
                source_document=base_version,
                source_docx_path=review_file_path,
                signature_data={
                    "email": otp_record.email,
                    "signer_name": (payload.signer_name or "").strip() or None,
                    "signer_title": (payload.signer_title or "").strip() or None,
                    "meaning": OTP_MEANING,
                    "timestamp": now.isoformat(),
                    "timestamp_display": signature_timestamp_display,
                    "auth_method": "OTP",
                    "role": "reviewer",
                },
            )
        except Exception as signature_doc_err:
            logger.error(
                "Failed to append visible OTP signature block for agreement %s: %s",
                agreement.id,
                signature_doc_err,
                exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to create the signed document with the visible signature block.",
            ) from signature_doc_err

        internal_signature = AgreementInternalSignature(
            agreement_id=agreement.id,
            document_id=signature_document.id,
            role="reviewer",
            email=otp_record.email,
            meaning=OTP_MEANING,
            auth_method="otp",
            version=signature_document.version_number,
            ip_address=_extract_request_ip(request),
            document_hash=document_hash,
        )
        db.add(internal_signature)

        review_document.is_submitted = 'true'
        review_document.submitted_at = now
        otp_record.consumed_at = now
        otp_record.is_active = 'false'
        review_token.is_active = 'false'

        agreement.status = AgreementStatusEnum.REVIEWED_AND_SIGNED

        await create_agreement_system_comment(
            db,
            agreement.id,
            None,
            f"Agreement reviewed and signed by external reviewer via OTP. Meaning: {OTP_MEANING}.",
        )

        audit_log = AuditLog(
            user=otp_record.email,
            action="SIGNED_WITH_OTP",
            target_type="agreement",
            target_id=str(agreement.id),
            details={
                "documentId": str(signature_document.id),
                "meaning": OTP_MEANING,
                "timestamp": now.isoformat(),
            },
        )
        db.add(audit_log)

        try:
            await create_agreement_notice_board_entry(
                db,
                agreement,
                AgreementStatusEnum.REVIEWED_AND_SIGNED.value,
                created_by=None,
            )
        except Exception as notice_err:
            logger.error(
                "Failed to create Notice Board entry for OTP-signed agreement %s: %s",
                agreement.id,
                notice_err,
                exc_info=True,
            )

        # Sequential multi-signer: mark this signer as signed, then auto-invite
        # the next signer in sign_order. No-op for legacy agreements with no
        # AgreementSigner rows.
        from app.modules.agreements.aggregator import (
            mark_signer_signed as _mark_signer_signed,
            dispatch_next_signer_otp as _dispatch_next_signer_otp,
        )
        await _mark_signer_signed(
            db, agreement.id, "reviewer", otp_record.email,
        )
        next_invited = await _dispatch_next_signer_otp(db, agreement)

        await db.commit()
        return {
            "status": "success",
            "message": "Agreement signed and sent back successfully.",
            "agreement_status": AgreementStatusEnum.REVIEWED_AND_SIGNED.value,
            "meaning": OTP_MEANING,
            "email": otp_record.email,
            "timestamp": now.isoformat(),
            "auth_method": "otp",
            "document_id": str(signature_document.id),
            "version": signature_document.version_number,
            "next_signer": {
                "role": next_invited.role,
                "email": next_invited.email,
                "name": next_invited.name,
                "sign_order": next_invited.sign_order,
            } if next_invited else None,
        }
    finally:
        if temp_review and Path(temp_review.name).exists():
            try:
                os.unlink(temp_review.name)
            except OSError:
                pass


@router.post("/auth/send-sign-otp")
async def send_signing_otp(
    payload: schemas.AgreementOtpSendRequest,
    db: AsyncSession = Depends(get_db),
):
    agreement, signing_token, latest_doc = await _get_active_signing_context(
        db, payload.agreement_id, payload.token
    )
    logger.info("Routing agreement %s through public signing OTP flow", agreement.id)

    if signing_token.role == "site":
        reviewer_sig_result = await db.execute(
            select(func.count(AgreementInternalSignature.id))
            .where(AgreementInternalSignature.agreement_id == agreement.id)
            .where(AgreementInternalSignature.role == "reviewer")
        )
        if agreement.status == AgreementStatusEnum.REVIEWED_AND_SIGNED:
            pass
        elif (reviewer_sig_result.scalar_one() or 0) == 0:
            raise HTTPException(status_code=400, detail="Reviewer must sign first.")

    now = datetime.now(timezone.utc)
    latest_otp_result = await db.execute(
        select(AgreementSigningOtp)
        .where(AgreementSigningOtp.agreement_id == agreement.id)
        .where(AgreementSigningOtp.role == signing_token.role)
        .where(AgreementSigningOtp.email == signing_token.recipient_email)
        .order_by(AgreementSigningOtp.created_at.desc())
    )
    latest_otp = latest_otp_result.scalars().first()
    if latest_otp and latest_otp.last_sent_at and latest_otp.last_sent_at > now - timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS):
        retry_after = OTP_RESEND_COOLDOWN_SECONDS - int((now - latest_otp.last_sent_at).total_seconds())
        raise HTTPException(status_code=429, detail=f"Please wait {max(retry_after, 1)} seconds before requesting a new OTP.")

    # Invalidate older active OTPs for this role+email so resend can't widen the
    # brute-force window. (Defense for O2 from the audit.)
    await _invalidate_active_otps(
        db,
        AgreementSigningOtp,
        AgreementSigningOtp.agreement_id == agreement.id,
        AgreementSigningOtp.role == signing_token.role,
        AgreementSigningOtp.email == signing_token.recipient_email,
    )

    otp_value = f"{secrets.randbelow(1_000_000):06d}"
    otp_record = AgreementSigningOtp(
        agreement_id=agreement.id,
        document_id=latest_doc.id,
        role=signing_token.role,
        email=signing_token.recipient_email,
        otp_hash=_hash_otp_value(otp_value),
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        attempts=0,
        last_sent_at=now,
        is_active='true',
    )
    db.add(otp_record)

    from app.integrations.smtp_service import smtp_service
    # Async send — in-flow OTP route, transactional contract preserved.
    result = await smtp_service.send_email_async(
        to=signing_token.recipient_email,
        subject=f"Your OTP to sign {agreement.title}",
        body=(
            f"Your one-time password for signing agreement '{agreement.title}' is {otp_value}.\n\n"
            f"This code expires in {OTP_EXPIRY_MINUTES} minutes."
        ),
        from_email=getattr(settings, "smtp_user", "noreply@crm.local"),
        from_name="Clinical Trials CRM",
    )
    if not result.get("success"):
        await db.rollback()
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to send OTP email."))

    await db.commit()
    return {
        "status": "success",
        "message": "OTP sent successfully.",
        "expires_in_seconds": OTP_EXPIRY_MINUTES * 60,
        "resend_cooldown_seconds": OTP_RESEND_COOLDOWN_SECONDS,
        "email": signing_token.recipient_email,
    }


@router.post("/agreement/sign")
async def sign_agreement_with_otp(
    payload: schemas.AgreementOtpSignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    agreement, signing_token, latest_doc = await _get_active_signing_context(
        db, payload.agreement_id, payload.token
    )

    otp_result = await db.execute(
        select(AgreementSigningOtp)
        .where(AgreementSigningOtp.agreement_id == agreement.id)
        .where(AgreementSigningOtp.role == signing_token.role)
        .where(AgreementSigningOtp.email == signing_token.recipient_email)
        .where(AgreementSigningOtp.is_active == 'true')
        .where(AgreementSigningOtp.consumed_at.is_(None))
        .order_by(AgreementSigningOtp.created_at.desc())
    )
    otp_record = otp_result.scalars().first()
    if not otp_record:
        raise HTTPException(status_code=404, detail="No active OTP challenge found.")

    now = datetime.now(timezone.utc)
    if otp_record.expires_at < now:
        otp_record.is_active = 'false'
        await db.commit()
        raise HTTPException(status_code=403, detail="OTP has expired.")

    if otp_record.attempts >= OTP_MAX_ATTEMPTS:
        otp_record.is_active = 'false'
        await db.commit()
        raise HTTPException(status_code=429, detail="Too many invalid OTP attempts.")

    submitted_otp = (payload.otp or "").strip()
    if not submitted_otp:
        raise HTTPException(status_code=400, detail="OTP is required.")

    if not hmac.compare_digest(otp_record.otp_hash, _hash_otp_value(submitted_otp)):
        new_attempts = await _atomic_increment_otp_attempts(
            db, AgreementSigningOtp, otp_record.id,
        )
        if new_attempts >= OTP_MAX_ATTEMPTS:
            await db.execute(
                update(AgreementSigningOtp)
                .where(AgreementSigningOtp.id == otp_record.id)
                .values(is_active='false')
            )
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    if signing_token.role == "site":
        reviewer_sig_result = await db.execute(
            select(func.count(AgreementInternalSignature.id))
            .where(AgreementInternalSignature.agreement_id == agreement.id)
            .where(AgreementInternalSignature.role == "reviewer")
        )
        if agreement.status == AgreementStatusEnum.REVIEWED_AND_SIGNED:
            pass
        elif (reviewer_sig_result.scalar_one() or 0) == 0:
            raise HTTPException(status_code=400, detail="Reviewer must sign first.")

    source_path = None
    tmp_file = None
    from app.utils.azure_storage import get_document_storage as _gds
    storage = _gds()
    if storage and latest_doc.document_file_path and latest_doc.document_file_path.startswith("agreements/"):
        doc_bytes = await storage.download_file(latest_doc.document_file_path)
        if not doc_bytes:
            raise HTTPException(status_code=404, detail="Document not found in Azure")
        tmp_file = await asyncio.to_thread(_make_named_tempfile, ".docx", doc_bytes)
        source_path = Path(tmp_file.name)
    else:
        source_path = Path(latest_doc.document_file_path)

    meaning = SITE_SIGN_MEANING if signing_token.role == "site" else OTP_MEANING
    next_status = AgreementStatusEnum.FULLY_SIGNED if signing_token.role == "site" else AgreementStatusEnum.REVIEWED_AND_SIGNED
    try:
        signed_doc = await _append_signature_to_docx_and_create_signed_version(
            db=db,
            agreement=agreement,
            source_document=latest_doc,
            source_docx_path=source_path,
            signature_data={
                "email": signing_token.recipient_email,
                "signer_name": (payload.signer_name or "").strip() or None,
                "signer_title": (payload.signer_title or "").strip() or None,
                "meaning": meaning,
                "timestamp": now.isoformat(),
                "timestamp_display": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "auth_method": "OTP",
                "role": signing_token.role,
            },
        )
    finally:
        if tmp_file and Path(tmp_file.name).exists():
            try:
                os.unlink(tmp_file.name)
            except OSError:
                pass

    try:
        if tmp_file:
            document_hash = hashlib.sha256(doc_bytes).hexdigest()
        else:
            async with aiofiles.open(source_path, "rb") as f:
                document_hash = hashlib.sha256(await f.read()).hexdigest()
    except Exception:
        document_hash = hashlib.sha256(f"{agreement.id}-{now.isoformat()}".encode()).hexdigest()

    db.add(AgreementInternalSignature(
        agreement_id=agreement.id,
        document_id=signed_doc.id,
        role=signing_token.role,
        email=signing_token.recipient_email,
        meaning=meaning,
        auth_method="otp",
        version=signed_doc.version_number,
        ip_address=_extract_request_ip(request),
        document_hash=document_hash,
    ))
    otp_record.consumed_at = now
    otp_record.is_active = 'false'
    signing_token.is_active = 'false'
    agreement.status = next_status

    db.add(AuditLog(
        user=signing_token.recipient_email,
        action="SIGNED_WITH_OTP",
        target_type="agreement",
        target_id=str(agreement.id),
        details={"role": signing_token.role, "documentId": str(signed_doc.id), "meaning": meaning, "timestamp": now.isoformat()},
    ))

    # Sequential multi-signer: mark this signer as signed, then auto-invite
    # the next signer in sign_order (if any). Both are no-ops for legacy
    # agreements that have no AgreementSigner rows configured.
    from app.modules.agreements.aggregator import (
        mark_signer_signed as _mark_signer_signed,
        dispatch_next_signer_otp as _dispatch_next_signer_otp,
    )
    signed_signer = await _mark_signer_signed(
        db, agreement.id, signing_token.role, signing_token.recipient_email,
    )
    next_invited = await _dispatch_next_signer_otp(db, agreement)

    # If this agreement is part of a multi-signer chain (signed_signer != None),
    # override the legacy next_status set above. Legacy CDA/single-signer
    # behaviour is preserved for agreements with no AgreementSigner rows.
    if signed_signer is not None:
        if next_invited is not None:
            # More signatures pending — keep the chain in "sent for signature"
            agreement.status = AgreementStatusEnum.SENT_FOR_SIGNATURE
        else:
            # Last signer in the chain — fully executed.
            agreement.status = AgreementStatusEnum.EXECUTED
        next_status = agreement.status  # for the response payload below

    # (The legacy CDA workflow OTP-bridge sync was removed with the bridges. The
    # unified signing path advances its engine instance inside record_signature.)

    await db.commit()
    logger.info("Agreement %s signed via secure email-link OTP flow by %s", agreement.id, signing_token.recipient_email)

    # Kafka: when a CDA or CTA reaches EXECUTED (last signer in the chain just
    # signed), publish CDA_FULLY_EXECUTED / CTA_FULLY_EXECUTED to the Data
    # Platform. Best-effort & self-guarded — must never break the already-
    # committed signature.
    try:
        if agreement.status == AgreementStatusEnum.EXECUTED and agreement.site_id:
            atype = str(
                getattr(agreement.agreement_type, "value", agreement.agreement_type) or ""
            ).upper()
            from app.integrations.milestones_kafka import publish_site_milestone, SiteMilestone

            executed_milestone = {
                "CDA": SiteMilestone.CDA_FULLY_EXECUTED,
                "CTA": SiteMilestone.CTA_FULLY_EXECUTED,
            }.get(atype)
            if executed_milestone is not None:
                await publish_site_milestone(
                    executed_milestone, site_id=str(agreement.site_id)
                )
    except Exception:
        logger.exception(
            "Failed to publish agreement-executed milestone for agreement %s", agreement.id
        )
    return {
        "status": "success",
        "agreement_status": next_status.value,
        "document_id": str(signed_doc.id),
        "version": signed_doc.version_number,
        "next_signer": {
            "role": next_invited.role,
            "email": next_invited.email,
            "name": next_invited.name,
            "sign_order": next_invited.sign_order,
        } if next_invited else None,
    }


@router.post("/auth/send-site-sign-otp")
async def send_site_sign_otp(
    agreement_id: UUID,
    email: str = Form(...),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    # Internal trigger only (additive safety)
    user_id = current_user.get("user_id") if current_user else None
    is_internal = is_user_internal(user_id, db) if user_id else True
    if not is_internal:
        raise HTTPException(status_code=403, detail="Only internal users can send site signing OTP.")

    agreement_result = await db.execute(
        select(Agreement).where(Agreement.id == agreement_id).options(selectinload(Agreement.documents))
    )
    agreement = agreement_result.scalar_one_or_none()
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")

    logger.info("Routing agreement %s through internal site OTP flow", agreement.id)

    # Enforce reviewer signed before initiating site sign
    reviewer_sig_result = await db.execute(
        select(func.count(AgreementInternalSignature.id))
        .where(AgreementInternalSignature.agreement_id == agreement.id)
        .where(AgreementInternalSignature.role == "reviewer")
    )
    if (reviewer_sig_result.scalar_one() or 0) == 0:
        raise HTTPException(status_code=400, detail="Reviewer must sign first.")

    latest_doc = _latest_agreement_document(list(agreement.documents or []))
    if not latest_doc or not latest_doc.document_file_path:
        raise HTTPException(status_code=404, detail="No document found")

    now = datetime.now(timezone.utc)
    latest_otp_result = await db.execute(
        select(AgreementSigningOtp)
        .where(AgreementSigningOtp.agreement_id == agreement.id)
        .where(AgreementSigningOtp.role == "site")
        .where(AgreementSigningOtp.email == email)
        .order_by(AgreementSigningOtp.created_at.desc())
    )
    latest_otp = latest_otp_result.scalars().first()
    if latest_otp and latest_otp.last_sent_at and latest_otp.last_sent_at > now - timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS):
        retry_after = OTP_RESEND_COOLDOWN_SECONDS - int((now - latest_otp.last_sent_at).total_seconds())
        raise HTTPException(status_code=429, detail=f"Please wait {max(retry_after, 1)} seconds before requesting a new OTP.")

    # Invalidate older active OTPs for this role+email so resend can't widen the
    # brute-force window. (Defense for O2 from the audit.)
    await _invalidate_active_otps(
        db,
        AgreementSigningOtp,
        AgreementSigningOtp.agreement_id == agreement.id,
        AgreementSigningOtp.role == "site",
        AgreementSigningOtp.email == email.strip(),
    )

    otp_value = f"{secrets.randbelow(1_000_000):06d}"
    otp_record = AgreementSigningOtp(
        agreement_id=agreement.id,
        document_id=latest_doc.id,
        role="site",
        email=email.strip(),
        otp_hash=_hash_otp_value(otp_value),
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        attempts=0,
        last_sent_at=now,
        is_active='true',
    )
    db.add(otp_record)

    from app.integrations.smtp_service import smtp_service
    from_email = getattr(settings, "smtp_user", "noreply@crm.local")
    # Async send — in-flow OTP resend.
    result = await smtp_service.send_email_async(
        to=email.strip(),
        subject=f"Your OTP to sign {agreement.title}",
        body=(
            f"Your one-time password for signing agreement '{agreement.title}' is {otp_value}.\n\n"
            f"This code expires in {OTP_EXPIRY_MINUTES} minutes."
        ),
        from_email=from_email,
        from_name="Clinical Trials CRM",
    )
    if not result.get("success"):
        await db.rollback()
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to send OTP email."))

    await db.commit()
    return {
        "status": "success",
        "message": "OTP sent successfully.",
        "expires_in_seconds": OTP_EXPIRY_MINUTES * 60,
        "resend_cooldown_seconds": OTP_RESEND_COOLDOWN_SECONDS,
        "email": email.strip(),
    }


@router.post("/agreement/site-sign-with-otp")
async def site_sign_with_otp(
    agreement_id: UUID,
    email: str = Form(...),
    otp: str = Form(...),
    signer_name: Optional[str] = Form(None),
    signer_title: Optional[str] = Form(None),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    agreement_result = await db.execute(
        select(Agreement).where(Agreement.id == agreement_id).options(selectinload(Agreement.documents))
    )
    agreement = agreement_result.scalar_one_or_none()
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")

    logger.info("Processing internal site OTP signature for agreement %s", agreement.id)

    reviewer_sig_result = await db.execute(
        select(func.count(AgreementInternalSignature.id))
        .where(AgreementInternalSignature.agreement_id == agreement.id)
        .where(AgreementInternalSignature.role == "reviewer")
    )
    if (reviewer_sig_result.scalar_one() or 0) == 0:
        raise HTTPException(status_code=400, detail="Reviewer must sign first.")

    otp_result = await db.execute(
        select(AgreementSigningOtp)
        .where(AgreementSigningOtp.agreement_id == agreement.id)
        .where(AgreementSigningOtp.role == "site")
        .where(AgreementSigningOtp.email == email.strip())
        .where(AgreementSigningOtp.is_active == 'true')
        .where(AgreementSigningOtp.consumed_at.is_(None))
        .order_by(AgreementSigningOtp.created_at.desc())
    )
    otp_record = otp_result.scalars().first()
    if not otp_record:
        raise HTTPException(status_code=404, detail="No active OTP challenge found.")

    now = datetime.now(timezone.utc)
    if otp_record.expires_at < now:
        otp_record.is_active = 'false'
        await db.commit()
        raise HTTPException(status_code=403, detail="OTP has expired.")

    if otp_record.attempts >= OTP_MAX_ATTEMPTS:
        otp_record.is_active = 'false'
        await db.commit()
        raise HTTPException(status_code=429, detail="Too many invalid OTP attempts.")

    submitted_otp = (otp or "").strip()
    if not submitted_otp:
        raise HTTPException(status_code=400, detail="OTP is required.")

    if not hmac.compare_digest(otp_record.otp_hash, _hash_otp_value(submitted_otp)):
        new_attempts = await _atomic_increment_otp_attempts(
            db, AgreementSigningOtp, otp_record.id,
        )
        if new_attempts >= OTP_MAX_ATTEMPTS:
            await db.execute(
                update(AgreementSigningOtp)
                .where(AgreementSigningOtp.id == otp_record.id)
                .values(is_active='false')
            )
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    latest_doc = _document_for_signature_apply(list(agreement.documents or []), "site")
    if not latest_doc or not latest_doc.document_file_path:
        raise HTTPException(status_code=404, detail="No document found")

    # Resolve local path to DOCX for python-docx
    source_path = None
    tmp_file = None
    from app.utils.azure_storage import get_document_storage as _gds
    storage = _gds()
    if storage and latest_doc.document_file_path and latest_doc.document_file_path.startswith("agreements/"):
        doc_bytes = await storage.download_file(latest_doc.document_file_path)
        if not doc_bytes:
            raise HTTPException(status_code=404, detail="Document not found in Azure")
        tmp_file = await asyncio.to_thread(_make_named_tempfile, ".docx", doc_bytes)
        source_path = Path(tmp_file.name)
    else:
        source_path = Path(latest_doc.document_file_path)

    try:
        signed_doc = await _append_signature_to_docx_and_create_signed_version(
            db=db,
            agreement=agreement,
            source_document=latest_doc,
            source_docx_path=source_path,
            signature_data={
                "email": email.strip(),
                "signer_name": (signer_name or "").strip() or None,
                "signer_title": (signer_title or "").strip() or None,
                "meaning": SITE_SIGN_MEANING,
                "timestamp": now.isoformat(),
                "timestamp_display": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "auth_method": "OTP",
                "role": "site",
            },
        )
    finally:
        if tmp_file and Path(tmp_file.name).exists():
            try:
                os.unlink(tmp_file.name)
            except OSError:
                pass

    doc_hash = ""
    try:
        # hash source bytes (good enough for audit)
        if tmp_file:
            doc_hash = hashlib.sha256(doc_bytes).hexdigest()
        else:
            async with aiofiles.open(source_path, "rb") as f:
                doc_hash = hashlib.sha256(await f.read()).hexdigest()
    except Exception:
        doc_hash = hashlib.sha256(f"{agreement.id}-{now.isoformat()}".encode()).hexdigest()

    internal_signature = AgreementInternalSignature(
        agreement_id=agreement.id,
        document_id=signed_doc.id,
        role="site",
        email=email.strip(),
        meaning=SITE_SIGN_MEANING,
        auth_method="otp",
        version=signed_doc.version_number,
        ip_address=_extract_request_ip(request) if request else None,
        document_hash=doc_hash,
    )
    db.add(internal_signature)

    otp_record.consumed_at = now
    otp_record.is_active = 'false'
    agreement.status = AgreementStatusEnum.FULLY_SIGNED

    db.add(AuditLog(
        user=email.strip(),
        action="SIGNED_WITH_OTP",
        target_type="agreement",
        target_id=str(agreement.id),
        details={"role": "site", "documentId": str(signed_doc.id), "meaning": SITE_SIGN_MEANING, "timestamp": now.isoformat()},
    ))

    # Sequential multi-signer: mark this signer as signed, then auto-invite
    # the next signer in sign_order. No-op for legacy agreements with no
    # AgreementSigner rows.
    from app.modules.agreements.aggregator import (
        mark_signer_signed as _mark_signer_signed,
        dispatch_next_signer_otp as _dispatch_next_signer_otp,
    )
    await _mark_signer_signed(db, agreement.id, "site", email)
    next_invited = await _dispatch_next_signer_otp(db, agreement)

    await db.commit()
    return {
        "status": "success",
        "agreement_status": AgreementStatusEnum.FULLY_SIGNED.value,
        "document_id": str(signed_doc.id),
        "version": signed_doc.version_number,
        "next_signer": {
            "role": next_invited.role,
            "email": next_invited.email,
            "name": next_invited.name,
            "sign_order": next_invited.sign_order,
        } if next_invited else None,
    }



