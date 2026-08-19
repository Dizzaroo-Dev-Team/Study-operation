"""REST API: agreement CRUD (list, create, get, next-status, status transition, versions, reset).

Extracted from app/api/v1/endpoints/legal_docs.py during Phase 2.1f. Includes
the agreement state machine via change_agreement_status (delegated to
app.modules.agreements.services.agreement_service).
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional
from uuid import UUID

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.auth import get_current_user_optional
from app.config import settings
from app.db import get_db
from app.utils.log_sanitize import sfmt
from app.models import (
    Agreement,
    AgreementChange,
    AgreementComment,
    AgreementDocument,
    AgreementInlineComment,
    AgreementReviewDocument,
    AgreementReviewToken,
    AgreementSignatureSource,
    AgreementSignedDocument,
    AgreementSignatureSource,
    AgreementStatus,
    AgreementStatus as AgreementStatusEnum,
    CommentType,
    Site,
    SiteProfile,
    SiteWorkflowStep,
    StepStatus,
    Study,
    StudySite,
    StudyTemplate,
    TemplateType,
    WorkflowStepName,
)
from app.modules.agreements.blob_names import _build_pretty_document_blob_name
from app.modules.agreements.services.agreement_service import (
    build_agreement_response,
    change_agreement_status as change_agreement_status_service,
    check_can_upload_new_version,
    create_agreement_notice,
    filter_comments_by_role,
    filter_versions_by_role,
    get_agreement_permissions,
    get_next_allowed_status as get_next_allowed_status_service,
    is_user_internal,
)

# Same enum as `Agreement.status` / workflow helpers that reference "AgreementStatusEnum".
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


async def _resolve_template_docx_path(template, db):
    """Resolve a template's uploaded DOCX to a local Path.

    Returns (path, temp_file_or_none). The temp file (if any) must be unlinked
    by the caller after use. Raises HTTPException when the file can't be found.
    """
    if not getattr(template, "template_file_path", None):
        raise HTTPException(
            status_code=400,
            detail="Template has no Clause Builder content and no DOCX file. "
                   "Open it in the Clause Builder and add content, or re-upload a DOCX.",
        )

    template_file_url = getattr(template, "template_file_url", None)
    if template_file_url:
        from app.utils.azure_storage import get_template_storage

        storage = get_template_storage()
        if storage:
            blob_bytes = await storage.download_file(template.template_file_path)
            if blob_bytes:
                tmp = await asyncio.to_thread(_make_named_tempfile, ".docx", blob_bytes)
                logger.info("Downloaded template from Azure for agreement creation: %s", template.template_file_path)
                return Path(tmp.name), tmp
            raise HTTPException(
                status_code=404,
                detail=f"Template file not found in Azure: {template.template_file_path}",
            )
        # Local dev: row references Azure URL but no connection string configured.
        local = Path(template.template_file_path)
        if local.is_file():
            logger.info("Azure template storage not configured; using local template path: %s", local)
            return local, None
        raise HTTPException(
            status_code=503,
            detail=(
                "Template is stored in Azure but blob storage is not configured, "
                "and the template file is not available on disk. Set AZURE_STORAGE_CONNECTION_STRING "
                "or re-upload the template so template_file_path points to a local .docx."
            ),
        )

    local = Path(template.template_file_path)
    if not local.exists():
        raise HTTPException(status_code=404, detail=f"Template DOCX file not found: {template.template_file_path}")
    return local, None


async def _build_source_docx_for_agreement(template, db):
    """Produce the source DOCX an agreement is generated from.

    Returns (path, needs_cleanup). `needs_cleanup` is True when `path` is a temp
    file the caller should unlink afterwards.

    - Template with a DOCX: clone it and splice Clause Builder insertions into the
      clone (original formatting preserved). If there are no insertions, the
      resolved original path is returned as-is.
    - Template without a DOCX (clause-only): generate the DOCX from template_content.
    """
    from app.utils.tiptap_to_docx import has_renderable_content, tiptap_json_to_docx

    has_docx = bool(getattr(template, "template_file_path", None))
    insertions = getattr(template, "clause_insertions", None) or []

    if has_docx:
        original_path, temp_handle = await _resolve_template_docx_path(template, db)

        if not insertions:
            # No clauses to add — use the original DOCX directly
            return original_path, bool(temp_handle)

        # Resolve clause content for every referenced clause
        from app.modules.agreements.services import clause_service
        clause_content_by_id = {}
        for ins in insertions:
            cid = str(ins.get("clause_id"))
            if cid in clause_content_by_id:
                continue
            clause = await clause_service.get_clause(db, UUID(cid))
            if clause and clause.current_version and clause.current_version.content_json:
                clause_content_by_id[cid] = clause.current_version.content_json

        from app.utils.docx_clause_splice import splice_clauses_into_docx
        out = await asyncio.to_thread(_make_named_tempfile, ".docx")
        splice_clauses_into_docx(original_path, insertions, clause_content_by_id, Path(out.name))

        # Original temp (if any) no longer needed
        if temp_handle:
            try:
                os.unlink(temp_handle.name)
            except OSError:
                pass
        logger.info("Spliced %d clause insertion(s) into template %s", len(insertions), template.id)
        return Path(out.name), True

    # No DOCX → generate from builder TipTap content
    content = getattr(template, "template_content", None)
    if not has_renderable_content(content):
        raise HTTPException(
            status_code=400,
            detail="Template has no DOCX file and no Clause Builder content. "
                   "Open it in the Clause Builder and add content first.",
        )
    out = await asyncio.to_thread(_make_named_tempfile, ".docx")
    tiptap_json_to_docx(content, Path(out.name))
    logger.info("Generated clause-only agreement DOCX from template_content for %s", template.id)
    return Path(out.name), True


@router.get("/sites/{site_id}/agreements", response_model=List[schemas.AgreementResponse])
async def list_site_agreements(
    site_id: str,
    study_id: UUID | None = Query(None, description="Study identifier for scoping agreements"),
    agreement_type: Optional[str] = Query(
        None,
        description="Filter by agreement type: CDA, CTA, BUDGET, OTHER. Case-insensitive.",
    ),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    List all agreements for a site.
    """
    try:
        # Resolve site
        try:
            site_uuid = UUID(str(site_id))
            site_result = await db.execute(select(Site).where(Site.id == site_uuid))
            site = site_result.scalar_one_or_none()
        except (ValueError, TypeError):
            site_result = await db.execute(select(Site).where(Site.site_id == site_id))
            site = site_result.scalar_one_or_none()

        if not site:
            raise HTTPException(status_code=404, detail="Site not found")

        if study_id is None:
            raise HTTPException(status_code=400, detail="study_id query parameter is required")

        # Resolve StudySite mapping for this Study + Site pair (required)
        study_site_result = await db.execute(
            select(StudySite)
            .where(StudySite.site_id == site.id)
            .where(StudySite.study_id == study_id)
        )
        study_site = study_site_result.scalar_one_or_none()

        if not study_site:
            logger.info(
                "No StudySite mapping found for study_id=%s, site_id=%s (site_id_external=%s) – returning empty agreement list",
                str(study_id),
                str(site.id),
                site.site_id,
            )
            return []

        # Build base query for agreements with relationships (documents only)
        base_query = select(Agreement).options(
            selectinload(Agreement.comments),
            selectinload(Agreement.documents),
            selectinload(Agreement.signed_documents),
        ).order_by(Agreement.created_at.desc())

        logger.info(
            "Listing agreements for study_id=%s, site_id=%s (site_id_external=%s) via study_site_id=%s",
            str(study_id),
            str(site.id),
            site.site_id,
            str(study_site.id),
        )
        agreements_query = base_query.where(Agreement.study_site_id == study_site.id)

        if agreement_type:
            type_upper = agreement_type.strip().upper()
            try:
                from app.models import TemplateType
                type_enum = TemplateType(type_upper)
                agreements_query = agreements_query.where(Agreement.agreement_type == type_enum)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown agreement_type {agreement_type!r}; expected CDA, CTA, BUDGET, or OTHER.",
                )

        agreements_result = await db.execute(agreements_query)
        agreements = agreements_result.scalars().all()

        # Determine if user is internal
        user_id = current_user.get("user_id") if current_user else None
        is_internal = is_user_internal(user_id, db) if user_id else True

        # Build responses for all agreements (can't use list comprehension with await)
        responses = []
        for agreement in agreements:
            response = await build_agreement_response(db, agreement, is_internal, user_id)
            responses.append(response)
        return responses
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed listing site agreements for site_id=%s study_id=%s",
            sfmt(site_id),
            sfmt(study_id) if study_id is not None else None,
        )
        raise HTTPException(status_code=500, detail=f"Failed to list agreements: {str(e)}")


async def create_agreement_system_comment(
    db: AsyncSession,
    agreement_id: UUID,
    version_id: Optional[UUID],
    content: str
):
    """Helper function to create system comments for agreement events."""
    comment = AgreementComment(
        agreement_id=agreement_id,
        version_id=version_id,
        comment_type=CommentType.SYSTEM,
        content=content,
        created_by=None  # System comments have no creator
    )
    db.add(comment)
    await db.flush()
    return comment


async def create_agreement_notice_board_entry(
    db: AsyncSession,
    agreement: Agreement,
    status: str,
    created_by: Optional[str] = None
):
    """
    Create a Notice Board entry for agreement status changes.
    Only creates notices for SENT_FOR_SIGNATURE, REVIEWED_AND_SIGNED and EXECUTED statuses.
    Includes duplicate prevention to avoid creating multiple notices for the same status.

    Delegates to create_agreement_notice with identical message and metadata.
    """
    # Only create notices for specific statuses
    if status not in [
        AgreementStatusEnum.SENT_FOR_SIGNATURE.value,
        AgreementStatusEnum.REVIEWED_AND_SIGNED.value,
        AgreementStatusEnum.EXECUTED.value,
    ]:
        return None

    site_result = await db.execute(select(Site).where(Site.id == agreement.site_id))
    site = site_result.scalar_one_or_none()
    site_display = (site.name or site.site_id) if site else str(agreement.site_id)

    if status == AgreementStatusEnum.SENT_FOR_SIGNATURE.value:
        event_type = "agreement_sent_for_signature"
        message = f"Agreement '{agreement.title}' for Site '{site_display}' has been sent for signature."
    elif status == AgreementStatusEnum.REVIEWED_AND_SIGNED.value:
        event_type = "agreement_reviewed_and_signed"
        message = f"Agreement '{agreement.title}' for Site '{site_display}' has been reviewed and approved by the external reviewer."
    else:
        event_type = "agreement_executed"
        message = f"Agreement '{agreement.title}' for Site '{site_display}' has been executed successfully."

    try:
        await create_agreement_notice(
            db=db,
            agreement=agreement,
            event_type=event_type,
            message=message,
            metadata={
                "agreement_id": str(agreement.id),
                "agreement_status": status,
                "agreement_title": agreement.title,
            },
        )
        logger.info("Created Notice Board entry for agreement %s, status: %s", agreement.id, status)
    except Exception as e:
        logger.error(
            "Failed to create Notice Board entry for agreement %s: %s",
            agreement.id,
            str(e),
            exc_info=True,
        )


# NOTE: complete_cda_execution_milestone was moved (2026-05-27) to
#   app/modules/agreements/types/cda/service.py
# as part of the Phase 2 isolation work. It was dead code here (no callers in
# this file or any other) and is CDA-specific. The shared CRUD layer must not
# know about a single agreement type's side-effects — that contract is now
# enforced by the registry's cda_on_status_change hook.


@router.post("/sites/{site_id}/agreements", response_model=schemas.AgreementResponse)
async def create_agreement(
    site_id: str,
    agreement_data: schemas.AgreementCreate,
    study_id: UUID | None = Query(None, description="Study identifier for agreement creation"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new agreement for a site.
    """
    # Resolve site
    try:
        site_uuid = UUID(str(site_id))
        site_result = await db.execute(select(Site).where(Site.id == site_uuid))
        site = site_result.scalar_one_or_none()
    except (ValueError, TypeError):
        site_result = await db.execute(select(Site).where(Site.site_id == site_id))
        site = site_result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    if study_id is None:
        raise HTTPException(status_code=400, detail="study_id query parameter is required")
    
    # Check if SiteProfile exists - required before creating CDA Agreement
    profile_result = await db.execute(
        select(SiteProfile).where(SiteProfile.site_id == site.id)
    )
    profile = profile_result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=400,
            detail="Please complete Site Profile before creating CDA."
        )
    
    # Validate status
    try:
        status_enum = AgreementStatus(agreement_data.status.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {agreement_data.status}")
    
    # For new agreements, template_id is required (non-legacy)
    template_id = getattr(agreement_data, 'template_id', None)
    is_legacy = 'false'
    
    if not template_id:
        raise HTTPException(
            status_code=400,
            detail="Template selection is required for new agreements. Please provide template_id."
        )
    
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

    # Resolve or create StudySite mapping for this Study + Site pair
    study_site_result = await db.execute(
        select(StudySite)
        .where(StudySite.site_id == site.id)
        .where(StudySite.study_id == study_id)
    )
    study_site = study_site_result.scalar_one_or_none()

    if not study_site:
        study_site = StudySite(
            study_id=study_id,
            site_id=site.id,
        )
        db.add(study_site)
        await db.flush()
        logger.info(
            "Created new StudySite mapping id=%s for study=%s, site=%s (site_id=%s)",
            str(study_site.id),
            str(study_id),
            str(site.id),
            site.site_id,
        )

    # One agreement per (StudySite, agreement_type) — enforced by the DB unique index
    # uq_agreements_study_site_type. When one already exists we either RESUME it (same
    # template, still an UNSIGNED draft) or SUPERSEDE it in place (it was already signed,
    # or a DIFFERENT template was chosen): keep the existing row + its full document
    # history (incl. signed copies), clear the prior workflow run, and lay down a FRESH
    # clean version from the chosen template reset to draft. This is what makes "create a
    # workflow from a template" render a clean document instead of a previously-signed one.
    superseding = False
    existing_agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.study_site_id == study_site.id)
        .where(Agreement.agreement_type == template.template_type)
        .options(
            selectinload(Agreement.comments),
            selectinload(Agreement.documents),
            selectinload(Agreement.signed_documents),
        )
    )
    existing_agreement = existing_agreement_result.scalar_one_or_none()

    if existing_agreement:
        docs = existing_agreement.documents or []
        # Originating template = the template recorded on the highest-version document.
        current_tpl_id = next(
            (d.created_from_template_id
             for d in sorted(docs, key=lambda d: -(d.version_number or 0))
             if d.created_from_template_id),
            None,
        )
        has_signed = any(getattr(d, "is_signed_version", None) == "true" for d in docs)
        is_terminal = existing_agreement.status in {
            AgreementStatus.FULLY_SIGNED, AgreementStatus.REVIEWED_AND_SIGNED,
            AgreementStatus.EXECUTED, AgreementStatus.CLOSED,
        }
        same_template = current_tpl_id == template.id

        if same_template and not has_signed and not is_terminal:
            # In-progress draft of the SAME template → resume it exactly as before.
            logger.info(
                "Resuming existing unsigned agreement %s (same template %s)",
                str(existing_agreement.id), str(template.id),
            )
            user_id = current_user.get("user_id") if current_user else None
            is_internal = is_user_internal(user_id, db) if user_id else True
            return await build_agreement_response(db, existing_agreement, is_internal, user_id)

        # Otherwise SUPERSEDE in place: keep the row + every document version (incl.
        # signed history), clear the prior engine run, reset to draft, and fall through
        # to lay down a fresh clean version from the chosen template.
        logger.info(
            "Superseding agreement %s (has_signed=%s terminal=%s same_template=%s) — "
            "fresh draft from template %s",
            str(existing_agreement.id), has_signed, is_terminal, same_template, str(template.id),
        )
        superseding = True
        agreement = existing_agreement
        agreement.status = AgreementStatus.DRAFT
        from app.modules.workflows.service import reset_agreement_workflow
        await reset_agreement_workflow(db, str(agreement.id))
        await create_agreement_system_comment(
            db, agreement.id, None,
            f"Superseded by a fresh draft from template '{template.template_name}'. "
            f"Prior versions (including any signed copies) are retained in history.",
        )
        await db.flush()

    # Safety: ensure template belongs to the same study (if template.study_id is set)
    if hasattr(template, "study_id") and template.study_id and template.study_id != study_id:
        raise HTTPException(
            status_code=400,
            detail="Template does not belong to the requested study_id"
        )

    if not superseding:
        # Create agreement (non-legacy), now explicitly linked to StudySite
        default_signature_source = (
            AgreementSignatureSource.INTERNAL
            if settings.enable_internal_signing
            else AgreementSignatureSource.ZOHO
        )

        agreement = Agreement(
            site_id=site.id,
            study_id=study_id,                       # Explicit Study + Site scoping from query
            study_site_id=study_site.id,             # StudySite-based scoping
            agreement_type=template.template_type,   # CDA / CTA / BUDGET / OTHER
            title=agreement_data.title,
            status=status_enum,
            created_by=current_user.get("user_id") if current_user else None,
            is_legacy=is_legacy,
            signature_source=default_signature_source,
        )
        logger.info(
            "Creating agreement %s with study_site_id=%s, study_id=%s, site_id=%s (site_id_external=%s)",
            str(agreement.id) if getattr(agreement, "id", None) else "<pending>",
            str(study_site.id),
            str(template.study_id),
            str(site.id),
            site.site_id,
        )
        db.add(agreement)
        await db.flush()

    # New agreement → version 1. Supersede → next sequential version on top of the kept
    # history, so the fresh template copy becomes the LATEST document the editor shows.
    if superseding:
        from app.modules.agreements.services.document_versioning import next_version_number
        _doc_version = await next_version_number(db, agreement.id)
    else:
        _doc_version = 1
    _doc_seq = _doc_version

    _study_result = await db.execute(select(Study).where(Study.id == study_id))
    _study_obj = _study_result.scalar_one_or_none()
    _study_name = _study_obj.name if _study_obj else str(study_id)
    _site_name = site.name or site.site_id

    # Clone template DOCX file and replace placeholders
    user_id = current_user.get("user_id") if current_user else None

    # --- Resolve the source DOCX, honouring Clause Builder insertions ---------
    # Two cases:
    #  1) Template has an uploaded DOCX → clone it (full fidelity) and splice the
    #     Clause Builder insertions into the clone at their anchor positions. The
    #     original document's tables/colors/fonts are never touched.
    #  2) Template has NO DOCX (clause-only) → generate the document from the
    #     builder's TipTap content (template_content).
    template_docx_path, _cleanup_source = await _build_source_docx_for_agreement(template, db)
    _temp_template_file = SimpleNamespace(name=str(template_docx_path)) if _cleanup_source else None
    # ------------------------------------------------------------------------

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

        # Pre-resolve placeholder values (template field_mappings + shared
        # DEFAULT_TOKEN_MAP) across ALL data sources (site_profile/agreement/study/irb),
        # case-insensitively. This is what makes the configured mappings AND well-known
        # placeholders actually fill in the generated document.
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
                study_name=_study_name,
                site_name=_site_name,
                agreement_title=agreement.title,
                seq=_doc_seq,
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
            # Local / dev: persist under upload_dir (same layout as reset cleanup uses).
            agreement_docs_dir = Path(settings.upload_dir) / "agreements" / str(agreement.id)
            agreement_docs_dir.mkdir(parents=True, exist_ok=True)
            dest_path = agreement_docs_dir / f"agreement_v{_doc_seq:03d}.docx"
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
        version_number=_doc_version,
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

    # Create system comment for agreement creation with template
    await create_agreement_system_comment(
        db,
        agreement.id,
        None,
        f"Agreement draft created from template '{template.template_name}'"
    )

    # Public Notice Board entry: Agreement created
    # Use central helper so it goes to the pinned Public Notice Board conversation.
    try:
        await create_agreement_notice(
            db=db,
            agreement=agreement,
            event_type="agreement_created",
            message=(
                f"Agreement '{agreement.title}' for Site '{site.site_id if hasattr(site, 'site_id') else agreement.site_id}' "
                f"has been created."
            ),
            metadata={
                "agreement_id": str(agreement.id),
                "agreement_status": agreement.status.value,
                "agreement_title": agreement.title,
            },
        )
    except Exception as e:
        logger.error(
            "Failed to create Notice Board entry for agreement %s (created): %s",
            agreement.id,
            str(e),
            exc_info=True,
        )

    # (The legacy per-type "start a workflow instance on create" hook — gated on the
    # removed WORKFLOW_DRIVES_CDA/_CTA flags — was deleted. The unified template-driven
    # page owns workflow-instance creation via its own ensure call.)

    await db.commit()
    
    # Reload with relationships
    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement.id)
        .options(
            selectinload(Agreement.comments),
            selectinload(Agreement.documents),
            selectinload(Agreement.signed_documents),
        )
    )
    agreement = agreement_result.scalar_one()
    
    # Determine if user is internal
    user_id = current_user.get("user_id") if current_user else None
    is_internal = is_user_internal(user_id, db) if user_id else True
    
    return await build_agreement_response(db, agreement, is_internal, user_id)


@router.post("/agreements/{agreement_id}/versions", response_model=schemas.AgreementDocumentResponse)
async def upload_agreement_version(
    agreement_id: UUID,
    file: Optional[UploadFile] = File(None),
    document_html: Optional[str] = Form(None),
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """
    Legacy endpoint preserved for backward compatibility.
    Runtime legacy file-based version uploads are no longer supported; callers should use DOCX-based flows.
    """
    raise HTTPException(
        status_code=400,
        detail="Legacy file-based versions are no longer supported. Use template-based agreements and document editor."
    )


@router.get("/agreements/{agreement_id}", response_model=schemas.AgreementResponse)
async def get_agreement_detail(
    agreement_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get agreement detail including documents, comments, and permissions.
    """
    # Get agreement with all relationships
    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement_id)
        .options(
            selectinload(Agreement.comments),
            selectinload(Agreement.documents).joinedload(AgreementDocument.inline_comments),
            selectinload(Agreement.signed_documents)
        )
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    # Determine if user is internal
    user_id = current_user.get("user_id") if current_user else None
    is_internal = is_user_internal(user_id, db) if user_id else True
    
    return await build_agreement_response(db, agreement, is_internal, user_id)


@router.get("/agreements/{agreement_id}/next-status")
async def get_next_allowed_status(
    agreement_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the next allowed status for an agreement.
    Returns null if no transitions are allowed (e.g., CLOSED).
    """
    agreement_result = await db.execute(
        select(Agreement).where(Agreement.id == agreement_id)
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    next_status = get_next_allowed_status_service(agreement.status)
    
    return {
        "current_status": agreement.status.value,
        "next_status": next_status.value if next_status else None,
        "can_transition": next_status is not None
    }


@router.patch("/agreements/{agreement_id}/status", response_model=schemas.AgreementResponse)
async def change_agreement_status(
    agreement_id: UUID,
    status_update: schemas.AgreementStatusUpdate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    CRM linear workflow — "Complete Review" advances REVIEW → SIGNATURE by setting
    status to READY_FOR_SIGNATURE (when allowed by agreement_service.ALLOWED_TRANSITIONS).

    Change agreement status using centralized workflow service.

    Enforces strict workflow rules:
    - Only allowed transitions are permitted
    - No backward transitions
    - No skipping states
    - Locking rules enforced
    
    Creates a system comment automatically with audit information.
    
    Enforces:
    - can_move_status permission check
    - Status transition validation
    """
    # Get agreement first to check permissions
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

    # Cross-study guard: the caller must be entitled to the agreement's study
    # (owner or grant — same gate as GET /studies). Closes the cross-study write
    # leak where a non-entitled caller could drive another study's agreement
    # through its workflow. The lock / state-machine checks below are unchanged.
    from app.integrations.iam.membership import user_can_act_in_study
    _study_ref = agreement.study_id
    if _study_ref is None and agreement.study_site_id:
        _ss = await db.execute(
            select(StudySite.study_id).where(StudySite.id == agreement.study_site_id)
        )
        _study_ref = _ss.scalar_one_or_none()
    if not (user_id and _study_ref and await user_can_act_in_study(user_id, str(_study_ref))):
        raise HTTPException(status_code=403, detail="You are not entitled to this study.")

    is_internal = is_user_internal(user_id, db) if user_id else True
    
    # Check permissions
    permissions = get_agreement_permissions(agreement, is_internal)
    
    if not permissions["can_move_status"]:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot change status. Agreement is locked or status '{agreement.status.value}' does not allow status transitions."
        )
    
    # Validate new status enum
    try:
        new_status_enum = AgreementStatusEnum(status_update.status.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status_update.status}")
    
    # Use centralized service function for status change
    try:
        agreement = await change_agreement_status_service(
            db,
            str(agreement_id),
            new_status_enum,
            user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── Token deactivation ────────────────────────────────────────────────────
    # When the agreement advances to READY_FOR_SIGNATURE or beyond, all active
    # external review tokens must be revoked.  External reviewers should no
    # longer be able to submit changes once the document is locked for
    # signature.
    _lock_statuses = {
        AgreementStatusEnum.REVIEWED_AND_SIGNED,
        AgreementStatusEnum.READY_FOR_SIGNATURE,
        AgreementStatusEnum.SENT_FOR_SIGNATURE,
        AgreementStatusEnum.EXECUTED,
        AgreementStatusEnum.CLOSED,
    }
    if new_status_enum in _lock_statuses:
        try:
            from sqlalchemy import update as sa_update
            await db.execute(
                sa_update(AgreementReviewToken)
                .where(AgreementReviewToken.agreement_id == agreement_id)
                .where(AgreementReviewToken.is_active == 'true')
                .values(is_active='false')
            )
            await db.commit()
            logger.info(
                "Deactivated all active review tokens for agreement %s "
                "(status advanced to %s)",
                agreement_id,
                new_status_enum.value,
            )
        except Exception as token_err:
            logger.warning(
                "Failed to deactivate review tokens for agreement %s: %s",
                agreement_id,
                str(token_err),
            )
    # ── end token deactivation ────────────────────────────────────────────────

    # Reload with relationships for response
    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement.id)
        .options(
            selectinload(Agreement.comments),
            selectinload(Agreement.documents),
            selectinload(Agreement.signed_documents)
        )
    )
    agreement = agreement_result.scalar_one()
    
    # Determine if user is internal
    user_id = current_user.get("user_id") if current_user else None
    is_internal = is_user_internal(user_id, db) if user_id else True
    
    return await build_agreement_response(db, agreement, is_internal, user_id)


# ---------------------------------------------------------------------------
# Agreement Workflow Reset Endpoint (for testing)
# ---------------------------------------------------------------------------

@router.delete("/agreements/{agreement_id}/reset")
async def reset_agreement_workflow(
    agreement_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Reset agreement workflow for testing purposes.
    This will completely reset the agreement:
    - Reset status to DRAFT
    - Delete all comments
    - Clear signature fields (zoho_request_id, signature_status)
    - Delete signed documents
    - Delete ALL document versions (AgreementDocument)
    - Delete ALL legacy file-based versions (historical only; table has been dropped in schema migration)
    - Reset current_version_id to None
    - This allows starting fresh with template selection
    """
    # Get agreement with all relationships
    agreement_result = await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement_id)
        .options(
            selectinload(Agreement.comments),
            selectinload(Agreement.documents),
            selectinload(Agreement.signed_documents),
        )
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found")
    
    try:
        # Delete all comments
        await db.execute(
            delete(AgreementComment).where(AgreementComment.agreement_id == agreement_id)
        )
        logger.info(f"Deleted all comments for agreement {agreement_id}")
        
        # Delete signed documents
        await db.execute(
            delete(AgreementSignedDocument).where(AgreementSignedDocument.agreement_id == agreement_id)
        )
        logger.info(f"Deleted all signed documents for agreement {agreement_id}")
        
        # Delete ALL document versions (AgreementDocument)
        await db.execute(
            delete(AgreementDocument).where(AgreementDocument.agreement_id == agreement_id)
        )
        logger.info(f"Deleted all document versions for agreement {agreement_id}")

        # ── CTA-specific cleanup ─────────────────────────────────────────
        # Reset wipes any active negotiation rounds, signer config, review
        # working copies, and signing tokens / OTPs so the agreement starts
        # truly fresh. No-op for CDA-style agreements that have no rows in
        # these tables.
        from app.models import (
            AgreementNegotiationRound, AgreementSigner,
            AgreementReviewDocument, AgreementReviewToken,
            AgreementReviewOtp, AgreementReviewerSignature,
            AgreementInternalSignature, AgreementSigningOtp,
            AgreementSigningToken,
            CTAAssignment, CTAPlaceholderMapping,
        )
        for model in (
            AgreementNegotiationRound, AgreementSigner,
            AgreementReviewDocument, AgreementReviewToken,
            AgreementReviewOtp, AgreementReviewerSignature,
            AgreementInternalSignature, AgreementSigningOtp,
            AgreementSigningToken,
            CTAAssignment, CTAPlaceholderMapping,
        ):
            await db.execute(delete(model).where(model.agreement_id == agreement_id))
        logger.info(f"Cleared CTA workflow tables (rounds, signers, review tokens/docs, signing tokens/otps, cta_assignments, cta_placeholder_mappings) for agreement {agreement_id}")
        
        # Also delete any DOCX/PDF files on disk for this agreement to avoid
        # stale/cached files being reused after reset.
        try:
            from pathlib import Path
            from app.config import settings as _settings
            import shutil

            agreement_dir = Path(_settings.upload_dir) / "agreements" / str(agreement_id)
            if agreement_dir.exists():
                shutil.rmtree(agreement_dir)
                logger.info(f"Deleted agreement files directory {agreement_dir} during reset for agreement {agreement_id}")
        except Exception as file_cleanup_error:
            logger.warning(
                "Failed to delete agreement files directory during reset for %s: %s",
                agreement_id,
                file_cleanup_error,
            )

        # Reset agreement fields
        agreement.status = AgreementStatusEnum.DRAFT
        agreement.zoho_request_id = None
        agreement.signature_status = None
        
        await db.commit()
        logger.info(f"Reset agreement {agreement_id} workflow to DRAFT - all versions deleted")
        
        # Reload agreement for response
        agreement_result = await db.execute(
            select(Agreement)
            .where(Agreement.id == agreement_id)
            .options(
                selectinload(Agreement.comments),
                selectinload(Agreement.documents),
                selectinload(Agreement.signed_documents)
            )
        )
        agreement = agreement_result.scalar_one()
        
        user_id = current_user.get("user_id") if current_user else None
        is_internal = is_user_internal(user_id, db) if user_id else True
        
        return {
            "status": "success",
            "message": "Agreement workflow reset successfully. All versions deleted. You can now select a template to start fresh.",
            "agreement": await build_agreement_response(db, agreement, is_internal, user_id)
        }
    
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to reset agreement workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reset workflow: {str(e)}")



