"""REST API: agreement document changes (accept/reject) + review tokens listing.

These endpoints are internal-only (gated by is_user_internal) and operate on
AgreementChange / AgreementReviewToken records produced during the OnlyOffice
review/negotiate workflow.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

import aiofiles
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user_optional
from app.config import settings
from app.db import get_db
from app.models import (
    Agreement,
    AgreementChange,
    AgreementDocument,
    AgreementReviewToken,
    AgreementStatus,
    AgreementStatus as AgreementStatusEnum,
    Site,
    Study,
)
from app.modules.agreements.services.agreement_service import (
    create_agreement_notice,
    is_user_internal,
)
from app.modules.agreements.aggregator import _latest_agreement_document
from app.modules.agreements.routes.crud import create_agreement_system_comment

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


@router.get("/agreements/{agreement_id}/changes")
async def get_agreement_changes(
    agreement_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get change history for an agreement.
    Only accessible to internal users.
    """
    # Check if user is internal
    user_id = current_user.get("user_id") if current_user else None
    is_internal = is_user_internal(user_id, db) if user_id else True
    
    if not is_internal:
        raise HTTPException(status_code=403, detail="Only internal users can view change history")
    
    # Get agreement
    agreement_result = await db.execute(
        select(Agreement).where(Agreement.id == agreement_id)
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    # Get all changes
    changes_result = await db.execute(
        select(AgreementChange)
        .where(AgreementChange.agreement_id == agreement_id)
        .order_by(AgreementChange.created_at.desc())
    )
    changes = changes_result.scalars().all()
    
    return {
        "changes": [
            {
                "id": str(change.id),
                "change_type": change.change_type,
                "old_text": change.old_text,
                "new_text": change.new_text,
                "section_reference": change.section_reference,
                "paragraph_index": change.paragraph_index,
                "table_index": change.table_index,
                "row_index": change.row_index,
                "cell_index": change.cell_index,
                "created_by": change.created_by,
                "created_at": change.created_at.isoformat(),
                "is_external_change": change.is_external_change == 'true',
                "is_accepted": change.is_accepted == 'true',
                "accepted_by": change.accepted_by,
                "accepted_at": change.accepted_at.isoformat() if change.accepted_at else None,
                "document_version_id": str(change.document_version_id),
            }
            for change in changes
        ]
    }


@router.post("/agreements/{agreement_id}/changes/{change_id}/accept")
async def accept_change(
    agreement_id: UUID,
    change_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Accept a change made by external site and merge it into the main document.

    Flow:
      1. Mark change as accepted in DB.
      2. Load the latest main AgreementDocument DOCX file.
      3. Apply the change (ADDED / DELETED / MODIFIED) to that file using
         document_apply_changes.apply_change_to_docx().
      4. Save the result as a new AgreementDocument version so the previous
         version is preserved for audit and OnlyOffice reloads the new file.
      5. Create a system comment recording the merge.

    Only accessible to internal users.
    """
    from app.utils.document_apply_changes import apply_change_to_docx
    from app.modules.agreements.aggregator import _latest_agreement_document
    from app.modules.agreements.routes.crud import create_agreement_system_comment

    # ── auth ──────────────────────────────────────────────────────────────
    user_id = current_user.get("user_id") if current_user else None
    is_internal = is_user_internal(user_id, db) if user_id else True

    if not is_internal:
        raise HTTPException(status_code=403, detail="Only internal users can accept changes")

    # ── load change ───────────────────────────────────────────────────────
    change_result = await db.execute(
        select(AgreementChange)
        .where(AgreementChange.id == change_id)
        .where(AgreementChange.agreement_id == agreement_id)
    )
    change = change_result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change not found")

    if change.is_accepted == 'true':
        return {
            "status": "already_accepted",
            "message": "Change was already accepted",
        }

    # ── load agreement + documents ────────────────────────────────────────
    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement_id)
        .options(selectinload(Agreement.documents))
    )
    agreement = agreement_result.scalar_one_or_none()

    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")

    # ── Workflow guard ─────────────────────────────────────────────────────
    # Accepting changes is only allowed while the agreement is in the review
    # stage.  Once locked for signature the document must not change.
    _allowed_change_statuses = {
        AgreementStatusEnum.UNDER_REVIEW,
        AgreementStatusEnum.UNDER_NEGOTIATION,  # legacy compat
    }
    if agreement.status not in _allowed_change_statuses:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Cannot accept changes. Agreement status is '{agreement.status.value}'. "
                "Negotiation actions are only allowed in UNDER_REVIEW."
            ),
        )
    # ── end guard ──────────────────────────────────────────────────────────

    if not agreement.documents:
        raise HTTPException(status_code=400, detail="No document versions found for this agreement")

    latest_document = _latest_agreement_document(agreement.documents)

    if not latest_document.document_file_path:
        raise HTTPException(status_code=400, detail="Latest document has no DOCX file path")

    _ac_temp_src = None
    _ac_doc_url = getattr(latest_document, 'document_file_url', None)
    if _ac_doc_url:
        from app.utils.azure_storage import get_document_storage as _gds_ac
        _ac_storage = _gds_ac()
        if _ac_storage:
            _ac_bytes = await _ac_storage.download_file(latest_document.document_file_path)
            if _ac_bytes:
                _ac_temp_src = await asyncio.to_thread(_make_named_tempfile, ".docx", _ac_bytes)
                source_path = Path(_ac_temp_src.name)
            else:
                raise HTTPException(status_code=404, detail="Document not found in Azure")
        else:
            raise HTTPException(status_code=500, detail="Azure storage not configured but document is in Azure")
    else:
        source_path = Path(latest_document.document_file_path)
        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"Document file not found on disk: {latest_document.document_file_path}")

    max_version_result = await db.execute(
        select(func.max(AgreementDocument.version_number))
        .where(AgreementDocument.agreement_id == agreement_id)
    )
    max_version_number = max_version_result.scalar_one_or_none() or 0
    next_version_number = max_version_number + 1

    _ac_temp_out = await asyncio.to_thread(_make_named_tempfile, ".docx")
    output_path = Path(_ac_temp_out.name)

    applied = apply_change_to_docx(
        source_path=source_path,
        change_type=change.change_type,
        old_text=change.old_text,
        new_text=change.new_text,
        paragraph_index=change.paragraph_index,
        output_path=output_path,
    )

    if not applied:
        logger.warning(
            f"accept_change: could not locate text in document for change {change_id} "
            f"(type={change.change_type}, old_text={change.old_text!r}). "
            "Marking accepted without document modification."
        )
        if _ac_temp_src and Path(_ac_temp_src.name).exists():
            os.unlink(_ac_temp_src.name)
        if Path(_ac_temp_out.name).exists():
            os.unlink(_ac_temp_out.name)
        change.is_accepted = 'true'
        change.accepted_by = user_id
        change.accepted_at = datetime.now(timezone.utc)
        await db.commit()
        return {
            "status": "accepted_no_merge",
            "message": "Change marked as accepted but could not be located in the document text.",
            "new_version": None,
        }

    try:
        from app.utils.azure_storage import get_document_storage as _gds_ac2, build_document_blob_name as _bdbn_ac
        _ac_storage2 = _gds_ac2()
        _ac_new_url = None
        if _ac_storage2:
            _ac_study_r = await db.execute(select(Study).where(Study.id == agreement.study_id))
            _ac_study = _ac_study_r.scalar_one_or_none()
            _ac_site_r = await db.execute(select(Site).where(Site.id == agreement.site_id))
            _ac_site = _ac_site_r.scalar_one_or_none()
            _ac_blob = _bdbn_ac(
                study_name=_ac_study.name if _ac_study else str(agreement.study_id),
                site_name=(_ac_site.name or _ac_site.site_id) if _ac_site else "Unknown",
                agreement_title=agreement.title,
                version_number=next_version_number,
            )
            async with aiofiles.open(output_path, "rb") as f:
                _ac_out_bytes = await f.read()
            _ac_new_url = await _ac_storage2.upload_file(
                _ac_out_bytes, _ac_blob,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            _ac_new_path = _ac_blob
        else:
            agreement_dir = Path(settings.upload_dir) / "agreements" / str(agreement.id)
            agreement_dir.mkdir(parents=True, exist_ok=True)
            local_path = agreement_dir / f"version_{next_version_number}_{uuid.uuid4()}.docx"
            shutil.copy2(str(output_path), str(local_path))
            _ac_new_path = str(local_path)
    finally:
        if _ac_temp_src and Path(_ac_temp_src.name).exists():
            os.unlink(_ac_temp_src.name)
        if Path(_ac_temp_out.name).exists():
            os.unlink(_ac_temp_out.name)

    new_document = AgreementDocument(
        agreement_id=agreement.id,
        version_number=next_version_number,
        document_content=None,
        document_file_path=_ac_new_path,
        document_file_url=_ac_new_url,
        document_html='',
        created_by=user_id,
        is_signed_version='false',
    )
    db.add(new_document)
    await db.flush()  # get new_document.id

    # ── mark change as accepted ───────────────────────────────────────────
    change.is_accepted = 'true'
    change.accepted_by = user_id
    change.accepted_at = datetime.now(timezone.utc)

    # ── system comment ────────────────────────────────────────────────────
    change_snippet = (
        (change.new_text or change.old_text or "")[:80]
        + ("…" if len(change.new_text or change.old_text or "") > 80 else "")
    )
    await create_agreement_system_comment(
        db,
        agreement.id,
        new_document.id,
        f"Version {next_version_number} created: accepted {change.change_type} change "
        f"(section: {change.section_reference or 'unspecified'}). "
        f"Snippet: \"{change_snippet}\""
    )

    # Public Notice Board entry: Agreement modified after review
    try:
        await create_agreement_notice(
            db=db,
            agreement=agreement,
            event_type="agreement_modified_after_review",
            message=(
                f"Agreement '{agreement.title}' for Site '{agreement.site_id}' "
                f"has been updated after review."
            ),
            metadata={
                "agreement_id": str(agreement.id),
                "agreement_status": agreement.status.value,
                "agreement_title": agreement.title,
                "new_version_number": next_version_number,
                "change_id": str(change_id),
            },
        )
    except Exception as e:
        logger.error(
            "Failed to create Notice Board entry for agreement %s (modified after review): %s",
            agreement.id,
            str(e),
            exc_info=True,
        )

    await db.commit()

    logger.info(
        f"accept_change: change {change_id} applied and new version {next_version_number} "
        f"created for agreement {agreement_id}"
    )

    return {
        "status": "success",
        "message": f"Change accepted and merged into document version {next_version_number}",
        "new_version": next_version_number,
        "new_document_id": str(new_document.id),
    }


@router.post("/agreements/{agreement_id}/changes/{change_id}/reject")
async def reject_change(
    agreement_id: UUID,
    change_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Reject a change made by external site.
    Only accessible to internal users.
    
    Rejecting a change marks it as rejected but keeps it in history.
    The change can be reverted by restoring the original text in the document.
    """
    # Check if user is internal
    user_id = current_user.get("user_id") if current_user else None
    is_internal = is_user_internal(user_id, db) if user_id else True
    
    if not is_internal:
        raise HTTPException(status_code=403, detail="Only internal users can reject changes")
    
    # Get change
    change_result = await db.execute(
        select(AgreementChange)
        .where(AgreementChange.id == change_id)
        .where(AgreementChange.agreement_id == agreement_id)
    )
    change = change_result.scalar_one_or_none()
    
    if not change:
        raise HTTPException(status_code=404, detail="Change not found")

    # ── Workflow guard ──────────────────────────────────────────────────────
    # Rejecting changes is only allowed while the agreement is in the review
    # stage.  Once locked for signature, negotiation actions are blocked.
    agreement_for_reject_result = await db.execute(
        select(Agreement).where(Agreement.id == agreement_id)
    )
    agreement_for_reject = agreement_for_reject_result.scalar_one_or_none()
    if agreement_for_reject:
        _allowed_reject_statuses = {
            AgreementStatusEnum.UNDER_REVIEW,
            AgreementStatusEnum.UNDER_NEGOTIATION,  # legacy compat
        }
        if agreement_for_reject.status not in _allowed_reject_statuses:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Cannot reject changes. Agreement status is "
                    f"'{agreement_for_reject.status.value}'. "
                    "Negotiation actions are only allowed in UNDER_REVIEW."
                ),
            )
    # ── end guard ──────────────────────────────────────────────────────────

    # Reject change (mark as not accepted, clear acceptance fields)
    change.is_accepted = 'false'
    change.accepted_by = None
    change.accepted_at = None
    
    await db.commit()
    
    return {
        "status": "success",
        "message": "Change rejected",
    }


@router.get("/agreements/{agreement_id}/review-tokens")
async def list_review_tokens(
    agreement_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    List all review tokens for an agreement.
    Only accessible to internal users.
    """
    # Check if user is internal
    user_id = current_user.get("user_id") if current_user else None
    is_internal = is_user_internal(user_id, db) if user_id else True
    
    if not is_internal:
        raise HTTPException(status_code=403, detail="Only internal users can view review tokens")
    
    # Get tokens
    tokens_result = await db.execute(
        select(AgreementReviewToken)
        .where(AgreementReviewToken.agreement_id == agreement_id)
        .order_by(AgreementReviewToken.created_at.desc())
    )
    tokens = tokens_result.scalars().all()
    
    frontend_base_url = getattr(settings, "frontend_base_url", "http://localhost:5173")
    
    return {
        "tokens": [
            {
                "id": str(token.id),
                "token": token.token,
                "expires_at": token.expires_at.isoformat(),
                "created_by": token.created_by,
                "created_at": token.created_at.isoformat(),
                "used_at": token.used_at.isoformat() if token.used_at else None,
                "is_active": token.is_active == 'true',
                "is_expired": token.expires_at < datetime.now(timezone.utc),
                "review_link": f"{frontend_base_url}/agreement/review/{agreement_id}?token={token.token}",
            }
            for token in tokens
        ]
    }


# ---------------------------------------------------------------------------
# Study Template Management Endpoints
# ---------------------------------------------------------------------------



