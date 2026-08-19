"""REST API: agreement document operations - create-from-template + save-document."""
from __future__ import annotations

import asyncio
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
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import schemas
from app.auth import get_current_user_optional
from app.config import settings
from app.db import get_db
from app.models import (
    Agreement,
    AgreementDocument,
    AgreementStatus,
    Site,
    SiteDocument,
    SiteProfile,
    Study,
    StudySite,
    StudyTemplate,
    TemplateType,
)
from app.modules.agreements.services.agreement_service import (
    get_agreement_permissions,
    is_user_internal,
)
from app.modules.agreements.blob_names import _build_pretty_document_blob_name
from app.modules.agreements.aggregator import _latest_agreement_document

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Legal Documents"])


def _legacy(name):
    import app.modules.agreements.aggregator as _ld
    return getattr(_ld, name)


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


@router.post("/agreements/{agreement_id}/create-from-template", response_model=schemas.AgreementDocumentResponse)
async def create_agreement_document_from_template(
    agreement_id: UUID,
    template_id: UUID = Form(...),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new document version from a template for an existing agreement.
    This is used when an agreement has been reset and needs a new document.
    """
    from app.modules.agreements.routes.crud import create_agreement_system_comment
    # Get agreement
    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement_id)
        .options(selectinload(Agreement.documents))
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    # Validate template exists and is active
    template_result = await db.execute(
        select(StudyTemplate)
        .where(StudyTemplate.id == template_id)
        .where(StudyTemplate.is_active == 'true')
    )
    template = template_result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(
            status_code=404,
            detail="Template not found or inactive"
        )
    
    # Check if agreement already has documents
    if agreement.documents and len(agreement.documents) > 0:
        raise HTTPException(
            status_code=400,
            detail="Agreement already has documents. Use save-document endpoint to create new versions."
        )
    
    # Check if agreement status allows document creation
    if agreement.status not in [AgreementStatus.DRAFT, AgreementStatus.UNDER_REVIEW]:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot create document. Agreement status '{agreement.status.value}' does not allow document creation."
        )
    
    user_id = current_user.get("user_id") if current_user else None

    _cft_study_result = await db.execute(select(Study).where(Study.id == agreement.study_id))
    _cft_study = _cft_study_result.scalar_one_or_none()
    _cft_study_name = _cft_study.name if _cft_study else str(agreement.study_id)
    _cft_site_result = await db.execute(select(Site).where(Site.id == agreement.site_id))
    _cft_site = _cft_site_result.scalar_one_or_none()
    _cft_site_name = (_cft_site.name or _cft_site.site_id) if _cft_site else "Unknown"

    if not hasattr(template, 'template_file_path') or not template.template_file_path:
        raise HTTPException(
            status_code=400,
            detail="Template does not have a DOCX file. Please re-upload the template."
        )

    _temp_template_file = None
    template_file_url = getattr(template, 'template_file_url', None)
    if template_file_url:
        from app.utils.azure_storage import get_template_storage
        storage = get_template_storage()
        if storage:
            blob_bytes = await storage.download_file(template.template_file_path)
            if blob_bytes:
                _temp_template_file = await asyncio.to_thread(_make_named_tempfile, ".docx", blob_bytes)
                template_docx_path = Path(_temp_template_file.name)
                logger.info("Downloaded template from Azure for document creation: %s", template.template_file_path)
            else:
                raise HTTPException(status_code=404, detail=f"Template file not found in Azure: {template.template_file_path}")
        else:
            template_docx_path = Path(template.template_file_path)
            if template_docx_path.is_file():
                logger.info(
                    "Azure template storage not configured; using local template path: %s",
                    template_docx_path,
                )
            else:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Template is stored in Azure but blob storage is not configured, "
                        "and the template file is not available on disk. Set AZURE_STORAGE_CONNECTION_STRING "
                        "or re-upload the template so template_file_path points to a local .docx."
                    ),
                )
    else:
        template_docx_path = Path(template.template_file_path)
        if not template_docx_path.exists():
            raise HTTPException(status_code=404, detail=f"Template DOCX file not found: {template.template_file_path}")
    
    # Fetch SiteProfile for placeholder merging
    profile_result = await db.execute(
        select(SiteProfile).where(SiteProfile.site_id == agreement.site_id)
    )
    profile = profile_result.scalar_one_or_none()
    
    if not profile:
        if _temp_template_file and Path(_temp_template_file.name).exists():
            os.unlink(_temp_template_file.name)
        raise HTTPException(
            status_code=400,
            detail="SiteProfile not found. Please complete Site Profile before creating agreement."
        )
    
    _temp_output_file = None
    try:
        _temp_output_file = await asyncio.to_thread(_make_named_tempfile, ".docx")
        temp_output_path = Path(_temp_output_file.name)

        from app.utils.docx_placeholder_replace import replace_placeholders_in_docx

        sponsor_signatory_name = settings.sponsor_signatory_name
        sponsor_signatory_email = settings.sponsor_signatory_email
        current_user_email = current_user.get("email") if current_user else None
        field_mappings = template.field_mappings if hasattr(template, 'field_mappings') and template.field_mappings else None
        placeholder_config = template.placeholder_config if hasattr(template, 'placeholder_config') and template.placeholder_config else None

        # Pre-resolve placeholder values across ALL data sources + DEFAULT_TOKEN_MAP
        # (see crud.create_agreement) so mappings/well-known placeholders actually fill.
        from app.modules.agreements.services.placeholder_fill import resolve_field_mapping_values
        resolved_values = await resolve_field_mapping_values(field_mappings, agreement, db)

        replace_placeholders_in_docx(
            template_docx_path,
            profile,
            temp_output_path,
            sponsor_signatory_name,
            sponsor_signatory_email,
            current_user_email,
            field_mappings=field_mappings,
            agreement=agreement,
            template_id=str(template.id),
            placeholder_config=placeholder_config,
            resolved_values=resolved_values,
        )

        from app.utils.azure_storage import get_document_storage

        storage = get_document_storage()
        if storage:
            blob_name = _build_pretty_document_blob_name(
                study_name=_cft_study_name,
                site_name=_cft_site_name,
                agreement_title=agreement.title,
                seq=1,
            )
            async with aiofiles.open(temp_output_path, "rb") as f:
                _out_bytes = await f.read()
            doc_file_url = await storage.upload_file(
                _out_bytes,
                blob_name,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            doc_file_path = blob_name
            logger.info("Uploaded agreement document to Azure: %s", blob_name)
        else:
            agreement_docs_dir = Path(settings.upload_dir) / "agreements" / str(agreement.id)
            agreement_docs_dir.mkdir(parents=True, exist_ok=True)
            dest_path = agreement_docs_dir / "agreement_v001.docx"
            shutil.copy2(temp_output_path, dest_path)
            doc_file_path = str(dest_path.resolve())
            doc_file_url = None
            logger.info(
                "Blob storage not configured; saved generated agreement DOCX locally at %s",
                doc_file_path,
            )
    finally:
        if _temp_template_file and Path(_temp_template_file.name).exists():
            os.unlink(_temp_template_file.name)
        if _temp_output_file and Path(_temp_output_file.name).exists():
            os.unlink(_temp_output_file.name)

    document = AgreementDocument(
        agreement_id=agreement.id,
        version_number=1,
        document_content=None,
        document_file_path=doc_file_path,
        document_file_url=doc_file_url,
        document_html='',
        created_from_template_id=template.id,
        created_by=user_id,
        is_signed_version='false',
    )
    db.add(document)
    await db.flush()
    
    # Create system comment
    await create_agreement_system_comment(
        db,
        agreement.id,
        None,
        f"Agreement draft created from template '{template.template_name}'"
    )
    
    await db.commit()
    await db.refresh(document)
    
    return {
        "id": document.id,
        "agreement_id": document.agreement_id,
        "version_number": document.version_number,
        "document_content": document.document_content if document.document_content else {},
        "document_file_path": document.document_file_path if hasattr(document, 'document_file_path') else None,
        "created_from_template_id": str(document.created_from_template_id) if document.created_from_template_id else None,
        "created_by": document.created_by,
        "created_at": document.created_at,
        "is_signed_version": document.is_signed_version,
    }


@router.post("/agreements/{agreement_id}/save-document", response_model=schemas.AgreementDocumentResponse)
async def save_agreement_document(
    agreement_id: UUID,
    save_data: schemas.DocumentSaveRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Save document content and create a new version.

    This endpoint:
    - Creates a new AgreementDocument version (does NOT overwrite previous)
    - Increments version_number
    - Creates SYSTEM comment: "Version X created after document edit"

    Validation rules:
    - Rejects if agreement.status in: READY_FOR_SIGNATURE, SENT_FOR_SIGNATURE, EXECUTED, CLOSED
    - Rejects if any document has is_signed_version = true

    Permissions:
    - Uses backend can_edit flag (no hardcoded status logic in frontend)
    """
    from app.modules.agreements.routes.crud import create_agreement_system_comment
    # Get agreement with documents
    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement_id)
        .options(
            selectinload(Agreement.documents),
            selectinload(Agreement.signed_documents)
        )
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    # Determine if user is internal for permission check
    user_id = current_user.get("user_id") if current_user else None
    is_internal = is_user_internal(user_id, db) if user_id else True
    
    # Get permissions using comprehensive permission engine
    permissions = get_agreement_permissions(agreement, is_internal)
    
    # Enforce can_save permission (403 Forbidden for locked statuses)
    if not permissions["can_save"]:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot save document. Agreement is locked or status '{agreement.status.value}' does not allow saving."
        )
    
    # Additional validation: Reject if signed version exists (double-check)
    has_signed_version = any(
        doc.is_signed_version == 'true' for doc in agreement.documents
    )
    if has_signed_version:
        raise HTTPException(
            status_code=403,
            detail="Cannot save document. A signed version exists."
        )
    
    # Get current max version number
    max_version_result = await db.execute(
        select(func.max(AgreementDocument.version_number))
        .where(AgreementDocument.agreement_id == agreement_id)
    )
    max_version_number = max_version_result.scalar_one_or_none()
    next_version_number = (max_version_number if max_version_number else 0) + 1
    
    # Get latest document to copy file path structure
    latest_document = _latest_agreement_document(agreement.documents) if agreement.documents else None
    
    from app.utils.azure_storage import get_document_storage as _gds_save, build_document_blob_name as _bdbn_save
    _save_storage = _gds_save()
    _save_doc_url = None
    if _save_storage:
        _sv_study_r = await db.execute(select(Study).where(Study.id == agreement.study_id))
        _sv_study = _sv_study_r.scalar_one_or_none()
        _sv_site_r = await db.execute(select(Site).where(Site.id == agreement.site_id))
        _sv_site = _sv_site_r.scalar_one_or_none()
        _save_blob = _bdbn_save(
            study_name=_sv_study.name if _sv_study else str(agreement.study_id),
            site_name=(_sv_site.name or _sv_site.site_id) if _sv_site else "Unknown",
            agreement_title=agreement.title,
            version_number=next_version_number,
        )
        _save_file_path = _save_blob
        _save_doc_url = "pending"
    else:
        agreement_dir = Path(settings.upload_dir) / "agreements" / str(agreement.id)
        agreement_dir.mkdir(parents=True, exist_ok=True)
        _save_file_path = str(agreement_dir / f"version_{next_version_number}_{uuid.uuid4()}.docx")

    new_document = AgreementDocument(
        agreement_id=agreement.id,
        version_number=next_version_number,
        document_content=None,
        document_file_path=_save_file_path,
        document_file_url=_save_doc_url,
        document_html='',
        created_by=user_id,
        is_signed_version='false',
    )
    db.add(new_document)
    await db.flush()
    
    # Create SYSTEM comment
    await create_agreement_system_comment(
        db,
        agreement.id,
        None,
        f"Version {next_version_number} created after document edit"
    )
    
    await db.commit()
    await db.refresh(new_document)
    
    return {
        "id": new_document.id,
        "agreement_id": new_document.agreement_id,
        "version_number": new_document.version_number,
        "document_content": new_document.document_content if new_document.document_content else {},
        "document_file_path": new_document.document_file_path if hasattr(new_document, 'document_file_path') else None,
        "created_from_template_id": new_document.created_from_template_id,
        "created_by": new_document.created_by,
        "created_at": new_document.created_at,
        "is_signed_version": new_document.is_signed_version,
    }


# ---------------------------------------------------------------------------
# Source-backed field drift (#6) — GENERAL, document-type-agnostic.
# Surfaces source-backed fields whose CURRENT document value differs from the live
# source (the field was edited, or the source moved on). The UI WARNS; nothing is
# silently overwritten. "Pull source" lets the user opt a drifted field back to the
# source value, producing a new document version. Free-text fields (no source) are
# never flagged.
# ---------------------------------------------------------------------------

async def _resolve_latest_docx_local(agreement, db) -> Optional[tuple]:
    """Resolve the agreement's latest EDITABLE (.docx) document to a local path (download
    from Azure when blob-backed). Returns (local_path, latest_doc, template, tmp_to_clean)
    or None when there is no DOCX document to check. Signed PDFs are skipped — drift only
    applies to editable docs with content controls."""
    docs = [d for d in (agreement.documents or [])
            if (getattr(d, "document_file_path", "") or "").lower().endswith(".docx")]
    if not docs:
        return None
    latest = max(docs, key=lambda d: d.version_number or 0)

    template = None
    if latest.created_from_template_id:
        template = (await db.execute(
            select(StudyTemplate).where(StudyTemplate.id == latest.created_from_template_id)
        )).scalar_one_or_none()

    path = latest.document_file_path or ""
    tmp_to_clean = None
    local_path = None
    url = getattr(latest, "document_file_url", None)
    if url or (path and not Path(path).exists()):
        from app.utils.azure_storage import get_document_storage
        storage = get_document_storage()
        if storage:
            data = await storage.download_file(path)
            if data:
                t = await asyncio.to_thread(_make_named_tempfile, ".docx", data)
                local_path = t.name
                tmp_to_clean = t.name
    elif path and Path(path).exists():
        local_path = path

    if not local_path or not Path(local_path).exists():
        return None
    return local_path, latest, template, tmp_to_clean


@router.get("/agreements/{agreement_id}/source-drift")
async def get_source_drift(
    agreement_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Report source-backed fields whose current document value differs from their live
    source value. General across agreement types. Returns {in_sync, drifted:[{token,
    doc_value, source_value}]}. Never modifies the document."""
    agreement = (await db.execute(
        select(Agreement).where(Agreement.id == agreement_id)
        .options(selectinload(Agreement.documents))
    )).scalar_one_or_none()
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")

    resolved = await _resolve_latest_docx_local(agreement, db)
    if resolved is None:
        return JSONResponse(content={"in_sync": [], "drifted": [],
                                     "note": "No editable (.docx) document to check."})
    local_path, _latest, template, tmp_to_clean = resolved
    field_mappings = (template.field_mappings if template and getattr(template, "field_mappings", None) else None)
    try:
        from app.modules.agreements.services.placeholder_fill import detect_source_drift
        report = await detect_source_drift(local_path, field_mappings, agreement, db)
        return JSONResponse(content=report)
    finally:
        if tmp_to_clean:
            try:
                os.unlink(tmp_to_clean)
            except OSError:
                pass


@router.post("/agreements/{agreement_id}/source-drift/pull")
async def pull_source_values(
    agreement_id: UUID,
    payload: Dict[str, Any],
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Pull the live source value into the user-selected drifted fields (they chose source
    over their edit). Updates ONLY those tagged fields, leaving every other edit intact,
    and persists a new document version. Body: {"tokens": ["HOSPITAL_NAME", ...]}. General."""
    tokens = [str(t).strip().upper() for t in (payload.get("tokens") or []) if str(t).strip()]
    if not tokens:
        raise HTTPException(status_code=400, detail="Provide one or more 'tokens' to pull from source.")

    agreement = (await db.execute(
        select(Agreement).where(Agreement.id == agreement_id)
        .options(selectinload(Agreement.documents))
    )).scalar_one_or_none()
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")

    resolved = await _resolve_latest_docx_local(agreement, db)
    if resolved is None:
        raise HTTPException(status_code=400, detail="No editable (.docx) document to update.")
    local_path, latest, template, tmp_to_clean = resolved
    field_mappings = (template.field_mappings if template and getattr(template, "field_mappings", None) else None)

    try:
        from app.modules.agreements.services.placeholder_fill import (
            resolve_field_mapping_values, set_filled_field_values,
        )
        source = await resolve_field_mapping_values(field_mappings, agreement, db)
        updates = {tok: source[tok] for tok in tokens if tok in source}
        if not updates:
            raise HTTPException(status_code=400, detail="None of the requested tokens resolve to a source value.")

        resynced_path = set_filled_field_values(local_path, updates)
        async with aiofiles.open(resynced_path, "rb") as fh:
            new_bytes = await fh.read()

        next_version = (max((d.version_number or 0) for d in agreement.documents) + 1) if agreement.documents else 1
        file_path = resynced_path
        file_url = None
        from app.utils.azure_storage import get_document_storage
        storage = get_document_storage()
        if storage and (getattr(latest, "document_file_url", None) or settings.azure_storage_connection_string):
            blob_name = _build_pretty_document_blob_name(
                study_name=str(agreement.study_id), site_name=str(agreement.site_id),
                agreement_title=agreement.title, seq=next_version,
            )
            file_url = await storage.upload_file(
                io.BytesIO(new_bytes), blob_name,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                overwrite=False,
            )
            file_path = blob_name

        new_document = AgreementDocument(
            agreement_id=agreement.id, version_number=next_version,
            document_file_path=file_path, document_file_url=file_url, document_html="",
            created_from_template_id=latest.created_from_template_id,
            created_by=(current_user or {}).get("email") if current_user else None,
            is_signed_version="false",
        )
        db.add(new_document)
        await db.flush()
        from app.modules.agreements.routes.crud import create_agreement_system_comment
        await create_agreement_system_comment(
            db, agreement.id, None,
            f"Re-synced {len(updates)} source-backed field(s) from source: {', '.join(sorted(updates))}",
        )
        await db.commit()
        return JSONResponse(content={"updated": sorted(updates.keys()), "version_number": next_version})
    finally:
        if tmp_to_clean:
            try:
                os.unlink(tmp_to_clean)
            except OSError:
                pass


