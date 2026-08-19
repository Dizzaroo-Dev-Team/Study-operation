"""REST API: public token-gated review + sign pages (HTML or JSON responses)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import schemas
from app.config import settings
from app.db import get_db
from app.models import (
    Agreement,
    AgreementDocument,
    AgreementReviewDocument,
    AgreementReviewToken,
    AgreementSigningToken,
    AgreementStatus,
    AgreementStatus as AgreementStatusEnum,
    Site,
)
from app.modules.agreements.aggregator import _get_active_signing_context
from app.utils.log_sanitize import sfmt

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Legal Documents"])


def _legacy(name):
    import app.modules.agreements.aggregator as _ld
    return getattr(_ld, name)


@router.get("/agreement/review/{agreement_id}")
async def get_review_agreement(
    agreement_id: UUID,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Public endpoint to access agreement for review (no authentication required).
    Validates token and returns agreement data for review page.
    """
    try:
        # Validate token
        logger.info(f"Review token validation request - agreement_id: {sfmt(agreement_id)}, token: {sfmt(token[:10])}...")
        
        token_result = await db.execute(
            select(AgreementReviewToken)
            .where(AgreementReviewToken.token == token)
            .where(AgreementReviewToken.agreement_id == agreement_id)
            .where(AgreementReviewToken.is_active == 'true')
        )
        review_token = token_result.scalar_one_or_none()
        
        if not review_token:
            logger.warning(f"Review token not found or inactive - agreement_id: {agreement_id}, token: {token[:10]}...")
            # Check if token exists but is inactive
            inactive_token_result = await db.execute(
                select(AgreementReviewToken)
                .where(AgreementReviewToken.token == token)
                .where(AgreementReviewToken.agreement_id == agreement_id)
            )
            inactive_token = inactive_token_result.scalar_one_or_none()
            if inactive_token:
                logger.warning(f"Token found but is_active={inactive_token.is_active}")
            raise HTTPException(status_code=403, detail="Invalid or expired review token")
        
        # Check if token expired
        now = datetime.now(timezone.utc)
        if review_token.expires_at < now:
            logger.warning(f"Review token expired - expires_at: {review_token.expires_at}, now: {now}")
            raise HTTPException(status_code=403, detail="Review token has expired")
        
        logger.info(f"Review token validated successfully - token_id: {review_token.id}")
        
        # Get agreement with documents
        agreement_result = await db.execute(
            select(Agreement)
            .where(Agreement.id == agreement_id)
            .options(
                selectinload(Agreement.documents),
                selectinload(Agreement.site),
            )
        )
        agreement = agreement_result.scalar_one_or_none()
        
        if not agreement:
            raise HTTPException(status_code=404, detail="Agreement not found")

        # ── Workflow guard ─────────────────────────────────────────────────
        # External review access is only permitted while the agreement is
        # still in the review/negotiation stage.  Once it advances to
        # READY_FOR_SIGNATURE or beyond, the document is locked and the
        # review link must no longer work.
        _allowed_review_access_statuses = {
            AgreementStatusEnum.UNDER_REVIEW,
            AgreementStatusEnum.UNDER_NEGOTIATION,  # legacy compat
        }
        if agreement.status not in _allowed_review_access_statuses:
            logger.warning(
                "Review link access blocked for agreement %s: status is %s",
                agreement_id,
                agreement.status.value,
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    "This agreement is no longer available for review. "
                    "The review period has ended."
                ),
            )
        # ── end guard ──────────────────────────────────────────────────────

        # Get review document for this token (external users edit review copy, not main document)
        review_doc_result = await db.execute(
            select(AgreementReviewDocument)
            .where(AgreementReviewDocument.review_token_id == review_token.id)
            .where(AgreementReviewDocument.is_submitted == 'false')
            .options(selectinload(AgreementReviewDocument.base_version))
        )
        review_document = review_doc_result.scalar_one_or_none()
        
        if not review_document:
            raise HTTPException(status_code=404, detail="Review document not found. The review may have already been submitted.")

        _rfp_check = review_document.review_file_path
        from app.utils.azure_storage import get_document_storage as _gds_check
        _check_storage = _gds_check()
        if _check_storage and _rfp_check and _rfp_check.startswith("agreement_reviews/"):
            _exists = await _check_storage.file_exists(_rfp_check)
            if not _exists:
                raise HTTPException(status_code=404, detail="Review document file not found in Azure")
        else:
            if not Path(_rfp_check).exists():
                raise HTTPException(status_code=404, detail="Review document file not found")

        # Mark token as used (first time only)
        if not review_token.used_at:
            review_token.used_at = datetime.now(timezone.utc)
            await db.commit()
        
        return {
            "agreement": {
                "id": str(agreement.id),
                "title": agreement.title or "Untitled Agreement",
                "status": agreement.status.value if hasattr(agreement.status, 'value') else str(agreement.status),
            },
            "site": {
                "id": str(agreement.site.id) if agreement.site and hasattr(agreement.site, 'id') else None,
                "site_id": agreement.site.site_id if agreement.site and hasattr(agreement.site, 'site_id') else None,
                "name": agreement.site.site_name if agreement.site and hasattr(agreement.site, 'site_name') else None,
            },
            "document": {
                "id": str(review_document.id),
                "version_number": review_document.base_version.version_number if review_document.base_version else None,
                "document_file_path": review_document.review_file_path,  # Return review copy path, not main document
                "is_review_copy": True,  # Flag to indicate this is a review copy
            },
            "token": token,
            "reviewer_email": review_token.recipient_email,
            "can_sign_with_otp": True,
        }
    except HTTPException:
        # Re-raise HTTP exceptions as-is (they already have proper status codes)
        raise
    except Exception as e:
        logger.error(f"Error in get_review_agreement for {agreement_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error loading agreement data: {str(e)}"
        )


@router.get("/agreement/sign/{agreement_id}")
async def get_sign_agreement(
    agreement_id: UUID,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    from app.modules.agreements.aggregator import _get_active_signing_context

    agreement, signing_token, document = await _get_active_signing_context(db, agreement_id, token)

    site_result = await db.execute(select(Site).where(Site.id == agreement.site_id))
    site = site_result.scalar_one_or_none()

    return {
        "agreement": {
            "id": str(agreement.id),
            "title": agreement.title or "Untitled Agreement",
            "status": agreement.status.value if hasattr(agreement.status, "value") else str(agreement.status),
        },
        "site": {
            "id": str(site.id) if site and hasattr(site, "id") else None,
            "site_id": site.site_id if site and hasattr(site, "site_id") else None,
            "name": site.site_name if site and hasattr(site, "site_name") else None,
        },
        "document": {
            "id": str(document.id),
            "version_number": document.version_number,
            "document_file_path": document.document_file_path,
            "is_review_copy": False,
        },
        "token": token,
        "signer_email": signing_token.recipient_email,
        "role": signing_token.role,
        "can_sign_with_otp": True,
    }




