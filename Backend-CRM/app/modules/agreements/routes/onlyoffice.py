"""REST API: OnlyOffice integration - callback + config (the two biggest endpoints in legal_docs).

The 646-line onlyoffice-callback handles document save events from the editor,
extracts changes and inline comments, and persists them to the agreement.
The 320-line onlyoffice-config produces the editor initialization payload.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from sqlalchemy import delete, func, select
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
    AgreementChange,
    AgreementDocument,
    AgreementInlineComment,
    AgreementReviewDocument,
    AgreementReviewToken,
    AgreementSigningToken,
    AgreementStatus,
    AgreementStatus as AgreementStatusEnum,
    CommentType,
    Site,
    Study,
)
from app.modules.agreements.services.agreement_service import (
    get_agreement_permissions,
    is_user_internal,
)
from app.modules.agreements.blob_names import (
    _build_pretty_document_blob_name,
    _build_review_working_blob_name,
    _extract_blob_seq,
)
from app.modules.agreements.aggregator import (
    _latest_agreement_document,
    _latest_document_for_version,
    _latest_signed_agreement_document,
    _resolve_onlyoffice_internal_base,
)
logger = logging.getLogger(__name__)
router = APIRouter(tags=["Legal Documents"])


def _make_named_tempfile(suffix: str, data: Optional[bytes] = None) -> Path:
    """Create a NamedTemporaryFile(delete=False) with ``suffix``, optionally
    writing ``data`` into it, and return its path. Sync on purpose — call via
    ``asyncio.to_thread`` from async code so the blocking file I/O stays off
    the event loop."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        if data is not None:
            tmp.write(data)
        return Path(tmp.name)


def _legacy(name):
    import app.modules.agreements.aggregator as _ld
    return getattr(_ld, name)


async def _upsert_comments_from_docx(*args, **kwargs):
    from app.modules.agreements.routes.signing import _upsert_comments_from_docx as _fn
    return await _fn(*args, **kwargs)


@router.options("/agreements/{agreement_id}/onlyoffice-callback")
async def onlyoffice_callback_options(
    agreement_id: UUID,
):
    """Handle CORS preflight for ONLYOFFICE callback."""
    from fastapi.responses import Response
    return Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )

@router.post("/agreements/{agreement_id}/onlyoffice-callback")
async def onlyoffice_callback(
    agreement_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    ONLYOFFICE callback endpoint for document save.
    
    This endpoint receives the saved document from ONLYOFFICE when user saves.
    Creates a new version of the agreement document.
    """
    from app.utils.onlyoffice_utils import verify_jwt_token
    from app.modules.agreements.routes.crud import create_agreement_system_comment
    from app.modules.agreements.routes.signing import _upsert_comments_from_docx
    from fastapi.responses import JSONResponse
    import httpx
    
    try:
        # Get request body
        body = await request.json()

        # Log full payload (with token redacted) for debugging
        try:
            log_body = dict(body) if isinstance(body, dict) else {"raw": body}
            if "token" in log_body:
                log_body["token"] = "[REDACTED]"
        except Exception:
            log_body = {"raw": "unserializable body"}

        status = body.get("status", 0)
        logger.info(
            "ONLYOFFICE callback triggered for agreement %s with status=%s payload=%s",
            agreement_id,
            status,
            log_body,
        )

        # Verify JWT if enabled (ONLYOFFICE sends token in body, not header)
        if settings.onlyoffice_jwt_enabled and settings.onlyoffice_jwt_secret:
            token = body.get("token", "")
            if token:
                payload = verify_jwt_token(token)
                if not payload:
                    logger.warning("Invalid JWT token in ONLYOFFICE callback")
                    return JSONResponse(
                        content={"error": 1},
                        headers={
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "POST, OPTIONS",
                            "Access-Control-Allow-Headers": "Content-Type, Authorization",
                        }
                    )
        
        # Get agreement and latest document
        agreement_result = await db.execute(
            select(Agreement)
            .where(Agreement.id == agreement_id)
            .options(selectinload(Agreement.documents))
        )
        agreement = agreement_result.scalar_one_or_none()
        
        if not agreement:
            raise HTTPException(status_code=404, detail="Agreement not found")
        
        # Check if this is a review document save (external reviewer)
        # The document_key in the callback body corresponds to the document ID
        document_key = body.get("key", "")
        is_review_document_save = False
        review_document = None
        
        if document_key:
            # ── Extract raw UUID from the document key ───────────────────────
            # onlyoffice-config now generates timestamped keys to bust the
            # OnlyOffice server-side cache:
            #   internal:  "{doc_uuid}_{updated_at_ms}"
            #   review:    "{review_doc_uuid}_{updated_at_ms}_c"
            #
            # UUIDs are exactly 36 chars ([0-9a-f-]) and NEVER contain "_".
            # So we can recover the UUID by splitting on the first "_".
            #
            # We also handle the legacy "-comment" suffix from earlier sessions.
            lookup_key = document_key
            if "_" in document_key:
                candidate = document_key.split("_", 1)[0]
                # Validate: UUID is 36 chars with exactly 4 hyphens
                if len(candidate) == 36 and candidate.count("-") == 4:
                    lookup_key = candidate
                    logger.debug(
                        "Callback: extracted UUID '%s' from timestamped key '%s'",
                        lookup_key,
                        document_key,
                    )
            elif document_key.endswith("-comment"):
                # Legacy format from sessions before timestamp keys
                lookup_key = document_key[: -len("-comment")]
                logger.debug(
                    "Callback: stripped legacy '-comment' suffix, lookup_key='%s'",
                    lookup_key,
                )

            # Check if document_key matches a review document ID
            try:
                review_doc_result = await db.execute(
                    select(AgreementReviewDocument)
                    .where(AgreementReviewDocument.id == UUID(lookup_key))
                    .where(AgreementReviewDocument.agreement_id == agreement_id)
                    .where(AgreementReviewDocument.is_submitted == 'false')
                )
                review_document = review_doc_result.scalar_one_or_none()
                
                if review_document:
                    is_review_document_save = True
                    logger.info(
                        "ONLYOFFICE callback detected review document save: "
                        "review_document_id=%s, key=%s, status=%s",
                        review_document.id,
                        document_key,
                        status,
                    )
                else:
                    logger.debug(
                        "ONLYOFFICE callback - key %s (lookup=%s) does not match "
                        "any active review document",
                        document_key,
                        lookup_key,
                    )
            except (ValueError, TypeError) as e:
                # lookup_key is not a valid UUID — not a review document
                logger.debug(
                    "ONLYOFFICE callback - key %s is not a valid UUID "
                    "(not a review document): %s",
                    document_key,
                    e,
                )
                review_document = None
        
        # Get latest document (for internal users or comparison)
        if not agreement.documents:
            if not is_review_document_save:
                raise HTTPException(status_code=404, detail="No document found")
            latest_document = None
        else:
            latest_document = _latest_agreement_document(agreement.documents)
        
        # Handle document save events
        # Status 1: Document is ready for editing (do NOT create version)
        # Status 2: Document is being saved (do NOT create version - just acknowledge)
        # Status 6: Document is being force saved (CREATE version only for this)
        # Status 7: Document save error (do NOT create version)
        
        # Handle review document saves (external reviewers) - update review copy on status 2 or 6
        # For review documents, we need to save on both status 2 (regular save) and status 6 (force save)
        # because external users might submit without doing a force save
        if is_review_document_save and status in [2, 6]:
            # Get document URL from callback
            url = body.get("url")
            if not url:
                logger.warning("ONLYOFFICE callback missing document URL for review document")
                return JSONResponse(
                    content={"error": 0},
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    }
                )
            
            # Rewrite URL if needed (same logic as main document)
            try:
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(url)
                target_host = parsed.hostname
                rewrite_hosts = {"localhost", "127.0.0.1"}
                if target_host in rewrite_hosts:
                    internal_parsed = urlparse(settings.onlyoffice_url)
                    new_scheme = internal_parsed.scheme or parsed.scheme or "http"
                    new_netloc = internal_parsed.netloc or "onlyoffice"
                    rewritten = parsed._replace(scheme=new_scheme, netloc=new_netloc)
                    url = urlunparse(rewritten)
            except Exception as url_rewrite_error:
                logger.warning(f"Failed to rewrite review document URL: {url_rewrite_error}")
            
            # Download and save to review document file
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, timeout=30.0)
                    response.raise_for_status()
                    docx_content = response.content
                
                _rv_rfp_old = review_document.review_file_path
                from app.utils.azure_storage import get_document_storage as _gds_rvcb
                _rvcb_storage = _gds_rvcb()
                review_file_path = None
                if _rvcb_storage and _rv_rfp_old and _rv_rfp_old.startswith("agreement_reviews/"):
                    import io as _rvcb_io

                    _cb_study_r = await db.execute(select(Study).where(Study.id == agreement.study_id))
                    _cb_study = _cb_study_r.scalar_one_or_none()
                    _cb_site_r = await db.execute(select(Site).where(Site.id == agreement.site_id))
                    _cb_site = _cb_site_r.scalar_one_or_none()
                    _prev_seq = _extract_blob_seq(_rv_rfp_old)
                    _new_seq = (_prev_seq + 1) if _prev_seq > 0 else 1
                    _new_blob = _build_review_working_blob_name(
                        study_name=_cb_study.name if _cb_study else str(agreement.study_id),
                        site_name=(_cb_site.name or _cb_site.site_id) if _cb_site else "Unknown",
                        agreement_title=agreement.title,
                        review_document_id=review_document.id,
                        seq=_new_seq,
                        when_utc=datetime.now(timezone.utc),
                    )
                    await _rvcb_storage.upload_file(
                        _rvcb_io.BytesIO(docx_content),
                        _new_blob,
                        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        overwrite=False,
                    )
                    review_document.review_file_path = _new_blob
                    review_document.updated_at = datetime.now(timezone.utc)
                    await db.commit()
                    logger.info(
                        "Review document saved to Azure (new blob, status %s): %s (was %s, size=%s bytes)",
                        status,
                        _new_blob,
                        _rv_rfp_old,
                        len(docx_content),
                    )
                else:
                    review_file_path = Path(_rv_rfp_old)
                    review_file_path.parent.mkdir(parents=True, exist_ok=True)
                    old_size = review_file_path.stat().st_size if review_file_path.exists() else 0
                    _stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
                    _new_local = review_file_path.parent / f"{review_file_path.stem}_{_stamp}{review_file_path.suffix or '.docx'}"
                    async with aiofiles.open(_new_local, "wb") as f:
                        await f.write(docx_content)
                    review_document.review_file_path = str(_new_local)
                    review_document.updated_at = datetime.now(timezone.utc)
                    await db.commit()
                    new_size = _new_local.stat().st_size
                    review_file_path = _new_local
                    logger.info(
                        "Review document saved locally (new file, status %s): %s (size=%s bytes, changed by %s bytes)",
                        status,
                        _new_local,
                        new_size,
                        new_size - old_size,
                    )

                _comment_docx_path = str(
                    await asyncio.to_thread(_make_named_tempfile, ".docx", docx_content)
                )

                try:
                    await _upsert_comments_from_docx(
                        db=db,
                        agreement_id=agreement_id,
                        review_document=review_document,
                        docx_path=_comment_docx_path,
                    )
                except Exception as comment_err:
                    # Rollback so the session stays usable for the response below.
                    # The file was already saved; only the comment rows failed.
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    logger.warning(
                        "Comment extraction failed for review_document %s: %s",
                        review_document.id,
                        comment_err,
                        exc_info=True,
                    )
                finally:
                    if _comment_docx_path and Path(_comment_docx_path).exists():
                        os.unlink(_comment_docx_path)

                return JSONResponse(
                    content={"error": 0},
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    }
                )
            except Exception as save_error:
                logger.error(f"Failed to save review document: {save_error}", exc_info=True)
                return JSONResponse(
                    content={"error": 1, "message": str(save_error)},
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    }
                )
        
        # Only create new version for status 6 (manual force save) - internal users only
        if status == 6 and not is_review_document_save:
            # Get document URL from callback
            url = body.get("url")
            if not url:
                logger.warning("ONLYOFFICE callback missing document URL")
                return JSONResponse(
                    content={"error": 0},
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    }
                )

            # ----------------------------------------------------------------
            # VERSIONING POLICY
            # ----------------------------------------------------------------
            # DRAFT / UNDER_REVIEW  → Overwrite the existing file in-place.
            #   No new AgreementDocument record is created.  The draft document
            #   (version 1) is kept as the single working copy until a change is
            #   formally accepted (accept_change endpoint) which creates the next
            #   sequential version.
            #
            # All other statuses   → Create a new version as before.
            #   (In practice the editor is read-only for READY_FOR_SIGNATURE and
            #   beyond, so this branch is a safety net for edge cases.)
            # ----------------------------------------------------------------
            draft_statuses = {
                AgreementStatus.DRAFT,
                AgreementStatus.UNDER_REVIEW,
                AgreementStatus.UNDER_NEGOTIATION,
            }
            is_draft_or_review = agreement.status in draft_statuses

            # Log the original URL from ONLYOFFICE
            logger.info("ONLYOFFICE callback document URL (original): %s", url)

            # Some ONLYOFFICE configs use 'localhost' in the URL, which is not
            # reachable from inside the backend container. Rewrite such hosts
            # to the internal ONLYOFFICE service host from settings.onlyoffice_url
            # (defaults to the docker-compose service 'onlyoffice:80').
            try:
                from urllib.parse import urlparse, urlunparse

                parsed = urlparse(url)
                target_host = parsed.hostname

                # Only ever rewrite localhost-style hosts. Public cloud hostnames
                # (e.g. *.azurewebsites.net) must be left untouched so DNS works.
                rewrite_hosts = {"localhost", "127.0.0.1"}

                if target_host in rewrite_hosts:
                    # Use the internal ONLYOFFICE URL (host:port) from settings.
                    internal_parsed = urlparse(settings.onlyoffice_url)
                    new_scheme = internal_parsed.scheme or parsed.scheme or "http"
                    new_netloc = internal_parsed.netloc or "onlyoffice"

                    rewritten = parsed._replace(scheme=new_scheme, netloc=new_netloc)
                    fixed_url = urlunparse(rewritten)
                    logger.info(
                        "Rewriting ONLYOFFICE document URL from %s to %s "
                        "for backend container connectivity.",
                        url,
                        fixed_url,
                    )
                    url = fixed_url
            except Exception as url_rewrite_error:
                logger.warning(
                    "Failed to analyze/rewrite ONLYOFFICE document URL %s: %s. "
                    "Proceeding with original URL.",
                    url,
                    str(url_rewrite_error),
                )

            # Download the saved document
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, timeout=30.0)
                    response.raise_for_status()
                    docx_content = response.content
                logger.info(
                    "ONLYOFFICE document downloaded for agreement %s from %s (size=%s bytes, status=%s)",
                    agreement_id,
                    url,
                    len(docx_content),
                    response.status_code,
                )

                if is_draft_or_review:
                    try:
                        from app.utils.azure_storage import get_document_storage
                        _cb_storage = get_document_storage()
                        _doc_url = getattr(latest_document, 'document_file_url', None)

                        if _cb_storage and _doc_url:
                            import io as _cb_io
                            _cb_study_r = await db.execute(select(Study).where(Study.id == agreement.study_id))
                            _cb_study = _cb_study_r.scalar_one_or_none()
                            _cb_site_r = await db.execute(select(Site).where(Site.id == agreement.site_id))
                            _cb_site = _cb_site_r.scalar_one_or_none()
                            _prev_seq = _extract_blob_seq(latest_document.document_file_path)
                            _new_seq = (_prev_seq + 1) if _prev_seq > 0 else (latest_document.version_number + 1)
                            _new_blob = _build_pretty_document_blob_name(
                                study_name=_cb_study.name if _cb_study else str(agreement.study_id),
                                site_name=(_cb_site.name or _cb_site.site_id) if _cb_site else "Unknown",
                                agreement_title=agreement.title,
                                seq=_new_seq,
                                when_utc=datetime.now(timezone.utc),
                            )
                            new_url = await _cb_storage.upload_file(
                                _cb_io.BytesIO(docx_content),
                                _new_blob,
                                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                overwrite=False,
                            )
                            latest_document.document_file_path = _new_blob
                            latest_document.document_file_url = new_url
                        else:
                            # Local fallback: create a new file per save instead of overwriting.
                            _base_local_path = Path(latest_document.document_file_path)
                            _base_local_path.parent.mkdir(parents=True, exist_ok=True)
                            _stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
                            _new_local_name = f"{_base_local_path.stem}_{_stamp}{_base_local_path.suffix or '.docx'}"
                            draft_file_path = _base_local_path.parent / _new_local_name
                            draft_file_path.parent.mkdir(parents=True, exist_ok=True)
                            async with aiofiles.open(draft_file_path, "wb") as f:
                                await f.write(docx_content)
                            latest_document.document_file_path = str(draft_file_path)
                            latest_document.document_file_url = None

                        await db.commit()
                        logger.info(
                            "Draft save: created new file %s for agreement %s "
                            "(status=%s, size=%d bytes, azure=%s)",
                            latest_document.document_file_path,
                            agreement_id,
                            agreement.status.value,
                            len(docx_content),
                            bool(_doc_url),
                        )
                    except Exception as draft_save_error:
                        logger.error(
                            "Failed to overwrite draft document for agreement %s: %s",
                            agreement_id,
                            str(draft_save_error),
                            exc_info=True,
                        )
                        await db.rollback()
                        return JSONResponse(
                            content={"error": 1},
                            headers={
                                "Access-Control-Allow-Origin": "*",
                                "Access-Control-Allow-Methods": "POST, OPTIONS",
                                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                            }
                        )
                else:
                    # ── All other statuses: create a new version ──────────────
                    # (In practice the editor is read-only once the agreement
                    # leaves UNDER_REVIEW, so this is a safety-net path.)
                    #
                    # Server-side lock: refuse version creation for statuses that
                    # must not allow any document changes.  get_onlyoffice_config
                    # already returns view-mode for these statuses, but a
                    # stale/replayed callback could still arrive.
                    _locked_for_write = {
                        AgreementStatus.READY_FOR_SIGNATURE,
                        AgreementStatus.SENT_FOR_SIGNATURE,
                        AgreementStatus.EXECUTED,
                        AgreementStatus.CLOSED,
                    }
                    if agreement.status in _locked_for_write:
                        logger.warning(
                            "Blocked version creation from ONLYOFFICE callback for "
                            "locked agreement %s (status=%s)",
                            agreement_id,
                            agreement.status.value,
                        )
                        return JSONResponse(
                            content={"error": 0},
                            headers={
                                "Access-Control-Allow-Origin": "*",
                                "Access-Control-Allow-Methods": "POST, OPTIONS",
                                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                            }
                        )

                    # PART 2: Duplicate save protection - compare file hashes
                    new_file_hash = hashlib.sha256(docx_content).hexdigest()
                    logger.info(
                        "Computed SHA256 hash of new document: %s (first 16 chars: %s)",
                        new_file_hash,
                        new_file_hash[:16]
                    )

                    latest_file_hash = None
                    _latest_doc_url = getattr(latest_document, 'document_file_url', None)
                    try:
                        if _latest_doc_url and latest_document.document_file_path:
                            from app.utils.azure_storage import get_document_storage as _gds
                            _hash_storage = _gds()
                            if _hash_storage:
                                _hash_bytes = await _hash_storage.download_file(latest_document.document_file_path)
                                if _hash_bytes:
                                    latest_file_hash = hashlib.sha256(_hash_bytes).hexdigest()
                        elif latest_document.document_file_path and Path(latest_document.document_file_path).exists():
                            async with aiofiles.open(latest_document.document_file_path, "rb") as f:
                                latest_file_content = await f.read()
                            latest_file_hash = hashlib.sha256(latest_file_content).hexdigest()
                        if latest_file_hash:
                            logger.info(
                                "Computed SHA256 hash of latest version file: %s (first 16 chars: %s)",
                                latest_file_hash,
                                latest_file_hash[:16]
                            )
                    except Exception as hash_error:
                        logger.warning(
                            "Failed to compute hash of latest version file: %s. "
                            "Proceeding with version creation.",
                            str(hash_error)
                        )

                    if latest_file_hash and new_file_hash == latest_file_hash:
                        logger.info(
                            "No content change detected (hashes match). "
                            "Skipping version creation for agreement %s",
                            agreement_id
                        )
                        return JSONResponse(
                            content={"error": 0},
                            headers={
                                "Access-Control-Allow-Origin": "*",
                                "Access-Control-Allow-Methods": "POST, OPTIONS",
                                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                            }
                        )

                    max_version_result = await db.execute(
                        select(func.max(AgreementDocument.version_number))
                        .where(AgreementDocument.agreement_id == agreement_id)
                    )
                    max_version_number = max_version_result.scalar_one_or_none()
                    next_version_number = (max_version_number if max_version_number else 0) + 1

                    logger.info(
                        "Creating version %s from manual save (status 6) for agreement %s",
                        next_version_number,
                        agreement_id
                    )

                    from app.utils.azure_storage import get_document_storage as _gds2, build_document_blob_name as _bdbn
                    _ver_storage = _gds2()
                    _ver_doc_url = None
                    if _ver_storage:
                        import io as _ver_io
                        _oo_study_r = await db.execute(select(Study).where(Study.id == agreement.study_id))
                        _oo_study = _oo_study_r.scalar_one_or_none()
                        _oo_site_r = await db.execute(select(Site).where(Site.id == agreement.site_id))
                        _oo_site = _oo_site_r.scalar_one_or_none()
                        _ver_blob = _bdbn(
                            study_name=_oo_study.name if _oo_study else str(agreement.study_id),
                            site_name=(_oo_site.name or _oo_site.site_id) if _oo_site else "Unknown",
                            agreement_title=agreement.title,
                            version_number=next_version_number,
                        )
                        _ver_doc_url = await _ver_storage.upload_file(
                            _ver_io.BytesIO(docx_content),
                            _ver_blob,
                            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                        _ver_file_path = _ver_blob
                    else:
                        agreement_dir = Path(settings.upload_dir) / "agreements" / str(agreement.id)
                        agreement_dir.mkdir(parents=True, exist_ok=True)
                        _ver_local = agreement_dir / f"version_{next_version_number}_{uuid.uuid4()}.docx"
                        async with aiofiles.open(_ver_local, "wb") as f:
                            await f.write(docx_content)
                        _ver_file_path = str(_ver_local)

                    new_document = AgreementDocument(
                        agreement_id=agreement.id,
                        version_number=next_version_number,
                        document_content=None,
                        document_file_path=_ver_file_path,
                        document_file_url=_ver_doc_url,
                        document_html='',
                        created_by=latest_document.created_by,
                        is_signed_version='true' if agreement.status == AgreementStatus.REVIEWED_AND_SIGNED else 'false',
                    )
                    db.add(new_document)

                    await create_agreement_system_comment(
                        db,
                        agreement.id,
                        None,
                        (
                            f"Version {next_version_number} created after OTP signature insertion via ONLYOFFICE"
                            if agreement.status == AgreementStatus.REVIEWED_AND_SIGNED
                            else f"Version {next_version_number} created after document edit via ONLYOFFICE"
                        )
                    )

                    await db.commit()
                    logger.info(
                        "Saved document version %s for agreement %s (hash: %s)",
                        next_version_number,
                        agreement_id,
                        new_file_hash[:16]
                    )
            
            except Exception as e:
                logger.error(
                    "Failed to save document from ONLYOFFICE callback for agreement %s: %s",
                    agreement_id,
                    str(e),
                    exc_info=True,
                )
                await db.rollback()
                return JSONResponse(
                    content={"error": 1},
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    }
                )
        
        # Return success with CORS headers
        return JSONResponse(
            content={"error": 0},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            }
        )
        
    except Exception as e:
        logger.exception(f"ONLYOFFICE callback error: {str(e)}")
        return JSONResponse(
            content={"error": 1},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            }
        )



@router.get("/agreements/{agreement_id}/onlyoffice-config")
async def get_onlyoffice_config(
    agreement_id: UUID,
    request: Request,
    version: Optional[int] = None,
    document_id: Optional[UUID] = None,
    token: Optional[str] = Query(None, description="Review token for external access"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get ONLYOFFICE editor configuration for an agreement document.
    
    Returns:
        Configuration object for ONLYOFFICE editor initialization
    """
    from app.utils.onlyoffice_utils import create_document_config, get_onlyoffice_editor_url
    from fastapi.responses import JSONResponse
    
    # Get agreement and documents
    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement_id)
        .options(selectinload(Agreement.documents))
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    if not agreement.documents:
        raise HTTPException(status_code=404, detail="No document found")

    # Check if access is via public token (review or signing)
    is_external_review = False
    is_external_sign = False
    review_document = None
    if token:
        token_result = await db.execute(
            select(AgreementReviewToken)
            .where(AgreementReviewToken.token == token)
            .where(AgreementReviewToken.agreement_id == agreement_id)
            .where(AgreementReviewToken.is_active == 'true')
        )
        review_token = token_result.scalar_one_or_none()
        
        if review_token and review_token.expires_at >= datetime.now(timezone.utc):
            is_external_review = True
            # External reviewers open the document in COMMENT-ONLY mode:
            # they can add / view comments but cannot edit the document text.
            # This maps to OnlyOffice permissions.edit=False, permissions.comment=True.
            mode = "comment"
            user_id = "external_reviewer"
            user_name = "External Reviewer"
            
            # Get review document (external users edit review copy, not main document)
            review_doc_result = await db.execute(
                select(AgreementReviewDocument)
                .where(AgreementReviewDocument.review_token_id == review_token.id)
                .where(AgreementReviewDocument.is_submitted == 'false')
                .options(selectinload(AgreementReviewDocument.base_version))
            )
            review_document = review_doc_result.scalar_one_or_none()
            
            if not review_document:
                raise HTTPException(status_code=404, detail="Review document not found. The review may have already been submitted.")

            _oo_rfp = review_document.review_file_path
            from app.utils.azure_storage import get_document_storage as _gds_oo
            _oo_storage = _gds_oo()
            if _oo_storage and _oo_rfp and _oo_rfp.startswith("agreement_reviews/"):
                _oo_exists = await _oo_storage.file_exists(_oo_rfp)
                if not _oo_exists:
                    raise HTTPException(status_code=404, detail="Review document file not found in Azure")
            else:
                if not Path(_oo_rfp).exists():
                    raise HTTPException(status_code=404, detail="Review document file not found")

            logger.info(f"External review - serving review document: {review_document.review_file_path}")
        else:
            sign_token_result = await db.execute(
                select(AgreementSigningToken)
                .where(AgreementSigningToken.token == token)
                .where(AgreementSigningToken.agreement_id == agreement_id)
                .where(AgreementSigningToken.is_active == 'true')
            )
            sign_token = sign_token_result.scalar_one_or_none()
            if sign_token and sign_token.expires_at >= datetime.now(timezone.utc):
                is_external_sign = True
                mode = "readonly"
                user_id = f"signer_{sign_token.role}"
                user_name = sign_token.recipient_email or "Signer"
                logger.info("External sign link - serving main document for signing token %s", sign_token.id)
            else:
                raise HTTPException(status_code=403, detail="Invalid or expired token")
    else:
        # Internal user - check and acquire edit lock if editing
        # Determine edit mode based on agreement status.
        # Locking rules:
        # - SENT_FOR_SIGNATURE: Read-only (view mode)
        # - EXECUTED: Read-only (view mode) - users can view the document but cannot edit
        
        permissions = get_agreement_permissions(agreement, True)  # Assume internal for now
        # If status is SENT_FOR_SIGNATURE, force view mode
        if agreement.status == AgreementStatus.SENT_FOR_SIGNATURE:
            mode = "view"
        else:
            mode = "view" if not permissions["can_edit"] else "edit"
        
        # Get user info
        user_id = current_user.get("user_id", "anonymous") if current_user else "anonymous"
        user_name = current_user.get("name", "User") if current_user else "User"
        
        # If editing mode, acquire edit lock
        if mode == "edit" and user_id != "anonymous":
            from datetime import timedelta
            has_lock = agreement.editing_user_id is not None and agreement.editing_started_at is not None
            
            if has_lock:
                # Check if lock is expired
                lock_age = datetime.now(timezone.utc) - agreement.editing_started_at
                is_expired = lock_age > timedelta(minutes=30)
                is_own_lock = agreement.editing_user_id == user_id
                
                if not is_expired and not is_own_lock:
                    # Lock is held by another user - return error
                    raise HTTPException(
                        status_code=409,
                        detail="Document is currently being edited by another user. Please try again later."
                    )
            
            # Acquire or refresh lock
            agreement.editing_user_id = user_id
            agreement.editing_started_at = datetime.now(timezone.utc)
            await db.commit()
    
    # For external reviewers, use review document; for internal users, use main document
    if is_external_review and review_document:
        # External users edit review copy
        document_file_path = review_document.review_file_path
        document_id_for_key = str(review_document.id)
        logger.info(f"External review - using review document: {document_file_path}")
    else:
        # Internal users edit main document
        # Select document by explicit document_id first; then by requested version;
        # otherwise latest.
        if document_id is not None:
            document = next(
                (d for d in agreement.documents if d.id == document_id),
                None,
            )
            if not document:
                raise HTTPException(
                    status_code=404,
                    detail=f"Document id {document_id} not found",
                )

            # For EXECUTED agreements, always show the signed version in ONLYOFFICE.
            # The frontend sometimes passes `document_id` to "pin" the doc being viewed;
            # if that pinned doc is unsigned, we override to the latest signed doc.
            if agreement.status == AgreementStatus.EXECUTED and getattr(document, "is_signed_version", None) != "true":
                signed_document = _latest_signed_agreement_document(agreement.documents)
                if signed_document:
                    document = signed_document
                    document_id = document.id  # Ensure document-file URL uses the overridden id
        elif version is not None:
            document = _latest_document_for_version(agreement.documents, version)
            if not document:
                raise HTTPException(
                    status_code=404,
                    detail=f"Document version {version} not found",
                )
        else:
            # For EXECUTED agreements, prefer the signed document version.
            # Signed versions may not match `_vNNN_` naming conventions, so
            # `_latest_agreement_document` can otherwise pick the wrong DOCX.
            if agreement.status in (
                AgreementStatus.REVIEWED_AND_SIGNED,
                AgreementStatus.FULLY_SIGNED,
                AgreementStatus.EXECUTED,
            ):
                document = _latest_signed_agreement_document(agreement.documents) or _latest_agreement_document(agreement.documents)
            else:
                document = _latest_agreement_document(agreement.documents)
        
        # Check if document has DOCX file
        if not hasattr(document, 'document_file_path') or not document.document_file_path:
            raise HTTPException(
                status_code=400,
                detail="Document does not have a DOCX file. Please create document from template."
            )
        document_file_path = document.document_file_path
        document_id_for_key = str(document.id)
    
    # Create document and callback URLs
    # IMPORTANT (ONLYOFFICE behavior):
    # - Document URL is fetched by ONLYOFFICE Document Server (in the Docker container),
    #   NOT directly by the browser, so it must be reachable from the container.
    # - Callback URL is also called from the Document Server.
    # - Backend and ONLYOFFICE may be in the same docker-compose network (local dev),
    #   or reachable via a public URL in production (Azure App Service).
    # - Use a configurable backend_internal_url so that:
    #     * Local default is http://backend:8000 (docker-compose service name)
    #     * Production can set BACKEND_INTERNAL_URL to the public HTTPS URL.
    
    # Use configured backend internal URL for ONLYOFFICE callbacks
    internal_base = _resolve_onlyoffice_internal_base(settings.backend_internal_url)
    
    # Both document and callback URLs must be reachable from ONLYOFFICE container
    # For external reviewers, include token in document URL; for internal users, use version
    if is_external_review and review_document:
        _cb_ms = (
            int(review_document.updated_at.timestamp() * 1000)
            if review_document.updated_at
            else 0
        )
        document_url = (
            f"{internal_base}/api/agreements/{agreement_id}/review-document-file"
            f"?token={token}&cb={_cb_ms}"
        )
    else:
        document_url = f"{internal_base}/api/agreements/{agreement_id}/document-file"
        _cb = int(hashlib.md5((document.document_file_path or "").encode(), usedforsecurity=False).hexdigest(), 16) % (10**9)
        if document_id is not None:
            document_url = f"{document_url}?document_id={document_id}&cb={_cb}"
        elif version is not None:
            document_url = f"{document_url}?version={version}&cb={_cb}"
        else:
            # Neither `document_id` nor `version` was provided by the caller.
            # Still, we selected a specific `document` above (e.g. signed doc
            # for EXECUTED agreements), so we must request that exact version.
            document_url = f"{document_url}?document_id={document.id}&cb={_cb}"
    callback_url = f"{internal_base}/api/agreements/{agreement_id}/onlyoffice-callback"
    
    logger.info(f"ONLYOFFICE config - document_url: {sfmt(document_url)}, callback_url: {sfmt(callback_url)}")
    
    # ── Document key strategy ────────────────────────────────────────────────
    # OnlyOffice caches file content server-side by document key.  If the key
    # never changes the editor always loads the cached (original) file even
    # after the file on disk has been overwritten.
    #
    # Fix: embed a millisecond timestamp derived from the document's updated_at
    # field.  The key changes every time the callback saves the file, so OO
    # fetches the fresh content on the very next open.
    #
    # Key formats
    #   internal:  "{doc_uuid}_{updated_at_ms}"
    #   review:    "{review_doc_uuid}_{updated_at_ms}_c"
    #   sign:      "{doc_uuid}_{updated_at_ms}_s"
    #
    # The "_c" suffix forces OO to open a brand-new session with the
    # comment-only permissions rather than reusing a cached edit session.
    # The callback key-parser (below in onlyoffice_callback) strips everything
    # after the first "_" to recover the raw UUID for review-doc lookup.
    if is_external_review and review_document:
        _updated_at = review_document.updated_at
        _ts_ms = int(_updated_at.timestamp() * 1000) if _updated_at else 0
        _rp = review_document.review_file_path or ""
        _rp_sig = int(hashlib.md5(_rp.encode(), usedforsecurity=False).hexdigest(), 16) % (10**9)
        document_key = f"{document_id_for_key}_{_ts_ms}_{_rp_sig}_c"
    elif is_external_sign:
        # Signers should always see the version that was current at link issuance,
        # so embed updated_at_ms — guaranteed to change whenever the file is saved.
        _doc_updated_at = getattr(document, "updated_at", None)
        _doc_ts_ms = int(_doc_updated_at.timestamp() * 1000) if _doc_updated_at else 0
        _path = document.document_file_path or ""
        _path_sig = int(hashlib.md5(_path.encode(), usedforsecurity=False).hexdigest(), 16) % (10**9)
        document_key = f"{document_id_for_key}_{_doc_ts_ms}_{_path_sig}_s"
    else:
        # Internal users: bust OnlyOffice's server-side cache whenever the
        # underlying file is saved. Without updated_at_ms, the key only
        # changes when the blob path changes — which is unreliable for local
        # storage and for promote-in-place flows (reviewer submit overwrites
        # base_version row without bumping its UUID). Aligns with the
        # "{doc_uuid}_{updated_at_ms}" strategy documented above.
        _doc_updated_at = getattr(document, "updated_at", None)
        _doc_ts_ms = int(_doc_updated_at.timestamp() * 1000) if _doc_updated_at else 0
        _path = document.document_file_path or ""
        _path_sig = int(hashlib.md5(_path.encode(), usedforsecurity=False).hexdigest(), 16) % (10**9)
        document_key = f"{document_id_for_key}_{_doc_ts_ms}_{_path_sig}"
    
    # Create configuration
    _path_for_type = (
        review_document.review_file_path
        if is_external_review and review_document
        else getattr(document, "document_file_path", "") if not is_external_review else ""
    )
    _is_pdf = str(_path_for_type or "").lower().endswith(".pdf")
    _file_type = "pdf" if _is_pdf else "docx"
    _document_type = "pdf" if _is_pdf else "word"
    config = create_document_config(
        document_url=document_url,
        callback_url=callback_url,
        document_key=document_key,
        document_title=agreement.title,
        user_id=user_id,
        user_name=user_name,
        mode=mode,
        file_type=_file_type,
        document_type=_document_type,
    )
    
    editor_url = get_onlyoffice_editor_url(request)
    _log_version = None
    if not is_external_review:
        _log_version = version if version is not None else document.version_number
    elif review_document and review_document.base_version:
        _log_version = review_document.base_version.version_number
    _path_for_oo_log = (
        review_document.review_file_path
        if is_external_review and review_document
        else document.document_file_path
    )
    logger.info(
        "ONLYOFFICE config - document_url: %s, callback_url: %s, editor_url: %s, version=%s, document_id=%s, selected_path=%s, blob_seq=%s, document_key=%s",
        sfmt(document_url),
        sfmt(callback_url),
        sfmt(editor_url),
        _log_version,
        sfmt(document_id) if document_id is not None else None,
        sfmt(_path_for_oo_log),
        _extract_blob_seq(_path_for_oo_log),
        sfmt(document_key),
    )

    return JSONResponse(
        content={
            "editorUrl": editor_url,
            "config": config,
        }
    )



