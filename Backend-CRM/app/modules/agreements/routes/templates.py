"""REST API: study template CRUD (DOCX upload, field-mapping, placeholder config, deactivate).

Extracted from app/api/v1/endpoints/legal_docs.py during Phase 2.1. All URL paths
preserved: /api/v1/studies/{study_id}/templates/* and /api/v1/templates/*.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.auth import get_current_user_optional
from app.config import settings
from app.db import get_db
from app.models import Site, Study, StudyTemplate, TemplateType
from app.models.agreement import CompositionMode
from app.utils.log_sanitize import sfmt
from app.utils.placeholder_detection import (
    create_default_placeholder_config,
    detect_placeholders_in_docx_bytes,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Legal Documents"])


def _make_named_tempfile(suffix: str, data: Optional[bytes] = None):
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


def _serialize_template_response(template) -> dict:
    """Shape a StudyTemplate ORM row into the StudyTemplateResponse dict."""
    return {
        "id": template.id,
        "study_id": template.study_id,
        "template_name": template.template_name,
        "template_type": template.template_type.value,
        "template_content": getattr(template, "template_content", None),
        "template_file_path": getattr(template, "template_file_path", None),
        "template_file_url": getattr(template, "template_file_url", None),
        "placeholder_config": getattr(template, "placeholder_config", None),
        "field_mappings": getattr(template, "field_mappings", None),
        "clause_insertions": getattr(template, "clause_insertions", None) or [],
        "created_by": template.created_by,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
        "is_active": template.is_active,
        "composition_mode": template.composition_mode.value if template.composition_mode else "DOCX_UPLOAD",
    }


def _resolve_onlyoffice_internal_base(raw_base: str) -> str:
    """Lazy re-import: helper currently lives in app.modules.agreements.aggregator."""
    from app.modules.agreements.aggregator import _resolve_onlyoffice_internal_base as _inner
    return _inner(raw_base)


async def _load_template_docx_bytes(template: StudyTemplate) -> Optional[bytes]:
    """Fetch the raw DOCX bytes for a template from Azure (if uploaded there) or local disk."""
    file_ref = getattr(template, "template_file_path", None)
    if not file_ref:
        return None

    # Azure first when a blob URL was recorded at upload time.
    if getattr(template, "template_file_url", None):
        try:
            from app.utils.azure_storage import get_template_storage
            storage = get_template_storage()
            if storage:
                blob_bytes = await storage.download_file(file_ref)
                if blob_bytes:
                    return blob_bytes
        except Exception as e:
            logger.warning("Azure download failed during placeholder re-detect (%s): %s", file_ref, e)

    # Local-disk fallback.
    try:
        local_path = Path(file_ref)
        if local_path.exists():
            return local_path.read_bytes()
    except Exception as e:
        logger.warning("Local read failed during placeholder re-detect (%s): %s", file_ref, e)

    return None


async def _ensure_placeholder_config(template: StudyTemplate, db: AsyncSession) -> dict:
    """
    Auto-heal placeholder_config for templates uploaded before liberal-regex detection.

    If a template has an empty placeholder_config but a DOCX on file, re-extract
    placeholders, persist them, and return the fresh config. Otherwise return what
    is already stored (possibly empty).
    """
    existing = getattr(template, "placeholder_config", None) or {}
    if existing:
        return existing

    docx_bytes = await _load_template_docx_bytes(template)
    if not docx_bytes:
        return {}

    detected = detect_placeholders_in_docx_bytes(docx_bytes)
    if not detected:
        return {}

    config = create_default_placeholder_config(detected)
    template.placeholder_config = config
    try:
        await db.commit()
        await db.refresh(template)
    except Exception as e:
        await db.rollback()
        logger.warning("Failed to persist re-detected placeholder_config for %s: %s", template.id, e)
        # Still return what we detected so the current request has data.
    return config


@router.post("/studies/{study_id}/templates", response_model=schemas.StudyTemplateResponse)
async def create_study_template(
    study_id: UUID,
    template_name: str = Form(...),
    template_type: str = Form(...),
    template_file: UploadFile = File(...),
    site_id: Optional[str] = Form(None),
    field_mappings: Optional[str] = Form(None),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new study template from DOCX upload.
    Uploads to Azure Blob Storage with naming format:
    templates/{study_name}_{site_name}_{template_type}_{template_name}.docx
    Falls back to local storage if Azure is not configured.
    """
    # Validate study exists
    study_result = await db.execute(
        select(Study).where(Study.id == study_id)
    )
    study = study_result.scalar_one_or_none()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    # Resolve site name for Azure blob naming
    site_name = "Global"
    if site_id:
        # Try lookup by UUID first, then by string site_id code
        site = None
        try:
            site_uuid = UUID(site_id)
            site_result = await db.execute(select(Site).where(Site.id == site_uuid))
            site = site_result.scalar_one_or_none()
        except (ValueError, AttributeError):
            pass
        if not site:
            site_result = await db.execute(
                select(Site).where(Site.site_id == site_id)
            )
            site = site_result.scalar_one_or_none()
        if site:
            site_name = site.name or site.site_id
        else:
            logger.warning(f"Site not found for site_id={sfmt(site_id)}, using 'Global'")

    # Validate template type enum
    try:
        template_type_enum = TemplateType(template_type.upper())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid template type: {template_type}"
        )

    # Validate file type
    if not template_file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    file_extension = Path(template_file.filename).suffix.lower()
    if file_extension not in ['.docx', '.doc']:
        raise HTTPException(
            status_code=400,
            detail="Only DOCX files are supported. Please upload a .docx file."
        )

    # Save uploaded DOCX to a local temp file first (needed for placeholder detection)
    upload_dir = Path(settings.upload_dir) / "templates"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4()
    local_file_name = f"template_{file_id}.docx"
    local_file_path = upload_dir / local_file_name

    template_file_path_value = str(local_file_path)
    template_file_url_value = None

    try:
        async with aiofiles.open(local_file_path, "wb") as buffer:
            while True:
                chunk = await template_file.read(64 * 1024)
                if not chunk:
                    break
                await buffer.write(chunk)
        logger.info(f"Saved template DOCX file locally: {local_file_path}")

        # Detect placeholders from DOCX content (case-insensitive, allows spaces/dashes;
        # names are normalized to UPPER_SNAKE_CASE by the shared helper).
        async with aiofiles.open(local_file_path, "rb") as fh:
            docx_bytes = await fh.read()
        detected_placeholders = detect_placeholders_in_docx_bytes(docx_bytes)
        placeholder_config = create_default_placeholder_config(detected_placeholders)
        logger.info(
            "Detected %d placeholder(s) in uploaded template '%s': %s",
            len(detected_placeholders),
            sfmt(template_name),
            sfmt(sorted(detected_placeholders)),
        )

        # Parse field_mappings if provided
        parsed_field_mappings = None
        if field_mappings:
            try:
                import json
                parsed_field_mappings = json.loads(field_mappings)
                if not isinstance(parsed_field_mappings, dict):
                    raise ValueError("field_mappings must be a JSON object")
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"Invalid JSON in field_mappings: {e}")

        # ---- Upload to Azure Blob Storage ----
        from app.utils.azure_storage import get_template_storage, build_template_blob_name
        storage = get_template_storage()
        if storage:
            study_display = study.name
            blob_name = build_template_blob_name(
                study_name=study_display,
                site_name=site_name,
                template_type=template_type_enum.value,
                template_name=template_name,
            )
            try:
                async with aiofiles.open(local_file_path, "rb") as fh:
                    file_bytes = await fh.read()
                blob_url = await storage.upload_file(
                    file_content=file_bytes,
                    blob_name=blob_name,
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
                template_file_path_value = blob_name
                template_file_url_value = blob_url
                logger.info(f"Uploaded template to Azure: {blob_name} -> {blob_url}")

                # Remove local temp file after successful Azure upload
                if local_file_path.exists():
                    local_file_path.unlink()
            except Exception as e:
                logger.error(f"Azure upload failed for template blob={blob_name}: {e}", exc_info=True)
                if local_file_path.exists():
                    local_file_path.unlink()
                raise HTTPException(
                    status_code=500,
                    detail=f"Template upload to Azure failed: {e}. The template was NOT saved. Please retry.",
                )
        else:
            logger.info("Azure storage not configured; template stored locally")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to process DOCX template: {e}")
        if local_file_path.exists():
            local_file_path.unlink()
        raise HTTPException(status_code=400, detail=f"Failed to process DOCX file: {e}")

    template = StudyTemplate(
        study_id=study.id,
        template_name=template_name,
        template_type=template_type_enum,
        template_content=None,
        template_file_path=template_file_path_value,
        template_file_url=template_file_url_value,
        document_html='',
        placeholder_config=placeholder_config,
        field_mappings=parsed_field_mappings,
        created_by=current_user.get("user_id") if current_user else None,
        is_active='true',
    )
    db.add(template)
    await db.flush()
    await db.commit()
    await db.refresh(template)

    return {
        "id": template.id,
        "study_id": template.study_id,
        "template_name": template.template_name,
        "template_type": template.template_type.value,
        "template_content": template.template_content if template.template_content else {"type": "doc", "content": []},
        "template_file_path": template.template_file_path,
        "template_file_url": template.template_file_url,
        "placeholder_config": template.placeholder_config or {},
        "field_mappings": template.field_mappings,
        "created_by": template.created_by,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
        "is_active": template.is_active,
        "composition_mode": template.composition_mode.value if template.composition_mode else "DOCX_UPLOAD",
    }


@router.get("/studies/{study_id}/templates", response_model=List[schemas.StudyTemplateResponse])
async def list_study_templates(
    study_id: UUID,
    active_only: bool = Query(True, description="Return only active templates"),
    db: AsyncSession = Depends(get_db),
):
    """
    List all templates for a study.
    """
    # Validate study exists
    study_result = await db.execute(
        select(Study).where(Study.id == study_id)
    )
    study = study_result.scalar_one_or_none()
    
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    
    # Query templates
    query = select(StudyTemplate).where(StudyTemplate.study_id == study_id)
    if active_only:
        query = query.where(StudyTemplate.is_active == 'true')
    query = query.order_by(StudyTemplate.created_at.desc())
    
    templates_result = await db.execute(query)
    templates = templates_result.scalars().all()

    response = []
    for template in templates:
        placeholder_config = await _ensure_placeholder_config(template, db)
        response.append({
            "id": template.id,
            "study_id": template.study_id,
            "template_name": template.template_name,
            "template_type": template.template_type.value,
            "template_content": template.template_content if hasattr(template, 'template_content') and template.template_content else {"type": "doc", "content": []},
            "template_file_path": template.template_file_path if hasattr(template, 'template_file_path') else None,
            "template_file_url": template.template_file_url if hasattr(template, 'template_file_url') else None,
            "placeholder_config": placeholder_config,
            "field_mappings": template.field_mappings if hasattr(template, 'field_mappings') and template.field_mappings else None,
            "created_by": template.created_by,
            "created_at": template.created_at,
            "updated_at": template.updated_at,
            "is_active": template.is_active,
            "composition_mode": template.composition_mode.value if template.composition_mode else "DOCX_UPLOAD",
        })
    return response


from pydantic import BaseModel as _PydanticBase

class _ClauseTemplateCreate(_PydanticBase):
    template_name: str
    template_type: str = "CDA"


@router.post("/studies/{study_id}/templates/clause-template", response_model=schemas.StudyTemplateResponse)
async def create_clause_template(
    study_id: UUID,
    body: _ClauseTemplateCreate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a blank CLAUSE_COMPOSED template (no DOCX upload required).
    Opens directly in the Clause Builder.
    """
    study_result = await db.execute(select(Study).where(Study.id == study_id))
    study = study_result.scalar_one_or_none()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    try:
        template_type_enum = TemplateType(body.template_type.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid template type: {body.template_type}")

    template = StudyTemplate(
        id=uuid.uuid4(),
        study_id=study_id,
        template_name=body.template_name,
        template_type=template_type_enum,
        composition_mode=CompositionMode.CLAUSE_COMPOSED,
        template_content={"type": "doc", "content": []},
        is_active="true",
        created_by=current_user.get("email") if current_user else None,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return {
        "id": template.id,
        "study_id": template.study_id,
        "template_name": template.template_name,
        "template_type": template.template_type.value,
        "template_content": template.template_content,
        "template_file_path": None,
        "template_file_url": None,
        "placeholder_config": None,
        "field_mappings": None,
        "created_by": template.created_by,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
        "is_active": template.is_active,
        "composition_mode": CompositionMode.CLAUSE_COMPOSED.value,
    }


@router.get("/templates/{template_id}/document-blocks")
async def get_template_document_blocks(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return the original DOCX's ordered body blocks (paragraphs + tables).

    The Clause Builder uses these as anchor points: the user drops clauses
    between blocks, and each drop is stored as an `after_block` index.
    Returns {blocks: [...], clause_insertions: [...]}.
    """
    result = await db.execute(select(StudyTemplate).where(StudyTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    blocks: list = []
    if getattr(template, "template_file_path", None):
        try:
            original_path, temp_handle = await _resolve_template_docx_for_blocks(template)
            from app.utils.docx_clause_splice import extract_blocks
            blocks = extract_blocks(original_path)
            if temp_handle:
                import os
                try:
                    os.unlink(temp_handle.name)
                except OSError:
                    pass
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to extract document blocks for %s: %s", template_id, exc)
            blocks = []

    return {
        "blocks": blocks,
        "clause_insertions": getattr(template, "clause_insertions", None) or [],
        "has_docx": bool(getattr(template, "template_file_path", None)),
    }


async def _resolve_template_docx_for_blocks(template):
    """Local copy of DOCX resolution for block extraction (read-only)."""
    from pathlib import Path as _Path

    file_url = getattr(template, "template_file_url", None)
    if file_url:
        from app.utils.azure_storage import get_template_storage
        storage = get_template_storage()
        if storage:
            blob = await storage.download_file(template.template_file_path)
            if blob:
                tmp = await asyncio.to_thread(_make_named_tempfile, ".docx", blob)
                return _Path(tmp.name), tmp
            raise HTTPException(status_code=404, detail="Template file not found in Azure")
        local = _Path(template.template_file_path)
        if local.is_file():
            return local, None
        raise HTTPException(status_code=503, detail="Template stored in Azure but blob storage not configured")
    local = _Path(template.template_file_path)
    if not local.exists():
        raise HTTPException(status_code=404, detail="Template DOCX file not found")
    return local, None


@router.patch("/templates/{template_id}/clause-insertions", response_model=schemas.StudyTemplateResponse)
async def save_clause_insertions(
    template_id: UUID,
    body: dict,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Save the ordered clause insertions for a template.

    body = {"clause_insertions": [{"after_block": int, "clause_id": str,
            "clause_version_id": str|null, "clause_title": str|null}, ...]}
    """
    result = await db.execute(select(StudyTemplate).where(StudyTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    template.clause_insertions = body.get("clause_insertions") or []
    await db.commit()
    await db.refresh(template)
    return _serialize_template_response(template)


@router.patch("/templates/{template_id}/content", response_model=schemas.StudyTemplateResponse)
async def save_template_content(
    template_id: UUID,
    body: dict,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Save the Tiptap JSON content of a template (clause builder output)."""
    result = await db.execute(select(StudyTemplate).where(StudyTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    template.template_content = body.get("content_json")
    await db.commit()
    await db.refresh(template)
    return {
        "id": template.id,
        "study_id": template.study_id,
        "template_name": template.template_name,
        "template_type": template.template_type.value,
        "template_content": template.template_content,
        "template_file_path": getattr(template, "template_file_path", None),
        "template_file_url": getattr(template, "template_file_url", None),
        "placeholder_config": getattr(template, "placeholder_config", None),
        "field_mappings": getattr(template, "field_mappings", None),
        "created_by": template.created_by,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
        "is_active": template.is_active,
        "composition_mode": template.composition_mode.value if template.composition_mode else "DOCX_UPLOAD",
    }


@router.get("/templates/field-mapping-options")
async def get_template_field_mapping_options():
    """
    Get available data source fields for dynamic field mappings.

    Returns a static list of Site Profile and Agreement fields that can be
    mapped to placeholders in templates.
    """
    return {
        "site_profile": [
            {"field": "site_name", "label": "Site Name"},
            {"field": "hospital_name", "label": "Hospital Name"},
            {"field": "pi_name", "label": "PI Name"},
            {"field": "pi_email", "label": "PI Email"},
            {"field": "pi_phone", "label": "PI Phone"},
            {"field": "primary_contracting_entity", "label": "Primary Contracting Entity"},
            {"field": "authorized_signatory_name", "label": "Authorized Signatory Name"},
            {"field": "authorized_signatory_email", "label": "Authorized Signatory Email"},
            {"field": "authorized_signatory_title", "label": "Authorized Signatory Title"},
            {"field": "address_line_1", "label": "Address Line 1"},
            {"field": "city", "label": "City"},
            {"field": "state", "label": "State"},
            {"field": "country", "label": "Country"},
            {"field": "postal_code", "label": "Postal Code"},
            {"field": "site_coordinator_name", "label": "Site Coordinator Name"},
            {"field": "site_coordinator_email", "label": "Site Coordinator Email"},
        ],
        "agreement": [
            {"field": "title", "label": "Agreement Title"},
            {"field": "status", "label": "Agreement Status"},
            {"field": "created_by", "label": "Created By"},
        ],
    }


@router.get("/templates/{template_id}", response_model=schemas.StudyTemplateResponse)
async def get_template_detail(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get template detail by ID.
    """
    template_result = await db.execute(
        select(StudyTemplate).where(StudyTemplate.id == template_id)
    )
    template = template_result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    placeholder_config = await _ensure_placeholder_config(template, db)
    return {
        "id": template.id,
        "study_id": template.study_id,
        "template_name": template.template_name,
        "template_type": template.template_type.value,
        "template_content": template.template_content if hasattr(template, 'template_content') and template.template_content else {"type": "doc", "content": []},
        "template_file_path": template.template_file_path if hasattr(template, 'template_file_path') else None,
        "template_file_url": template.template_file_url if hasattr(template, 'template_file_url') else None,
        "placeholder_config": placeholder_config,
        "field_mappings": template.field_mappings if hasattr(template, 'field_mappings') and template.field_mappings else None,
        "created_by": template.created_by,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
        "is_active": template.is_active,
    }


@router.get("/templates/{template_id}/ai-suggestions")
async def get_template_ai_suggestions(
    template_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Return AI-suggested field mappings for placeholders not yet mapped in a template.

    Reads the template DOCX from storage, calls
    ai_detect_additional_placeholders with the template's already-configured
    field_mappings keys as the known set, and returns AI suggestions for
    remaining free-form or un-tagged placeholders.

    Used by the Template Library "Field Mappings" modal to surface AI hints
    inline. Always returns HTTP 200 — on AI failure returns an empty list.
    """
    template_result = await db.execute(
        select(StudyTemplate).where(StudyTemplate.id == template_id)
    )
    template = template_result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Load DOCX bytes (Azure first, local fallback — mirrors _load_template_docx_bytes)
    docx_bytes = await _load_template_docx_bytes(template)
    if not docx_bytes:
        return {"suggestions": []}

    # Write to a temp file because ai_detect_additional_placeholders expects a path
    import os

    tmp_path: Optional[str] = None
    try:
        tmp = await asyncio.to_thread(_make_named_tempfile, ".docx", docx_bytes)
        tmp_path = tmp.name

        known_tokens = list((template.field_mappings or {}).keys())

        from app.modules.agreements.services.placeholder_fill import (
            DEFAULT_TOKEN_MAP,
            ai_detect_additional_placeholders,
            scan_placeholders_in_docx,
        )

        # Suggestions MUST target REAL {{placeholders}} that exist in the document —
        # otherwise the saved mapping key never matches and the value never fills (the
        # AI used to invent token names like `sponsor_name_label` that don't exist).
        real_tokens = await scan_placeholders_in_docx(tmp_path)
        real_upper = {t.strip().upper(): t for t in real_tokens}
        mapped_upper = {str(k).upper() for k in (template.field_mappings or {})}
        # Signature anchors are filled at signing time, not mapped here.
        unmapped = {
            up: orig for up, orig in real_upper.items()
            if up not in mapped_upper and not up.startswith("SIGNATURE_")
            and up not in ("SITE_SIGNATURE_BLOCK", "SPONSOR_SIGNATURE_BLOCK")
        }

        suggestions: list = []
        suggested_upper: set = set()

        # 1) Deterministic suggestions from the shared DEFAULT_TOKEN_MAP (no AI guesswork).
        for up, orig in unmapped.items():
            src = DEFAULT_TOKEN_MAP.get(orig.strip().lower()) or DEFAULT_TOKEN_MAP.get(up.lower())
            if src:
                suggestions.append({
                    "placeholder": orig, "suggested_source": src,
                    "confidence": 0.95, "reasoning": "Standard field auto-mapped",
                })
                suggested_upper.add(up)

        # 2) AI for the remaining unmapped REAL placeholders — but DROP anything whose
        #    token isn't an actual document placeholder (kills invented `_label` tokens).
        ai_raw = await ai_detect_additional_placeholders(tmp_path, known_tokens=known_tokens)
        for item in ai_raw:
            tok = str(item.get("token", "")).strip()
            up = tok.upper()
            if not tok or up in suggested_upper or up not in unmapped:
                continue  # not a real, still-unmapped placeholder → ignore
            suggestions.append({
                "placeholder": unmapped[up],  # use the document's exact token spelling
                "suggested_source": item.get("suggested_field", ""),
                "confidence": float(item.get("confidence", 0.0)),
                "reasoning": item.get("reasoning", ""),
            })
            suggested_upper.add(up)
    except Exception as exc:
        logger.exception("get_template_ai_suggestions: failed for template %s: %s", template_id, exc)
        return {"suggestions": []}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return {"suggestions": suggestions}


@router.get("/templates/{template_id}/template-file")
async def get_template_file(
    template_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get template DOCX file for ONLYOFFICE viewing.
    Downloads from Azure Blob Storage if stored there, otherwise serves local file.
    """
    from fastapi.responses import FileResponse, StreamingResponse
    import io

    template_result = await db.execute(
        select(StudyTemplate).where(StudyTemplate.id == template_id)
    )
    template = template_result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if not template.template_file_path:
        raise HTTPException(status_code=404, detail="Template file not found")

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }
    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    download_name = f"template_{template_id}_{template.template_name}.docx"

    # If stored in Azure, stream from blob storage
    template_file_url = getattr(template, 'template_file_url', None)
    if template_file_url:
        from app.utils.azure_storage import get_template_storage
        storage = get_template_storage()
        if storage:
            blob_bytes = await storage.download_file(template.template_file_path)
            if blob_bytes:
                return StreamingResponse(
                    io.BytesIO(blob_bytes),
                    media_type=content_type,
                    headers={
                        **headers,
                        "Content-Disposition": f'attachment; filename="{download_name}"',
                    },
                )
            logger.warning("Azure download failed for %s, trying local fallback",
                           template.template_file_path)

    # Local file fallback
    file_path = Path(template.template_file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Template file not found at: {template.template_file_path}"
        )

    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        filename=download_name,
        headers=headers,
    )


@router.get("/templates/{template_id}/onlyoffice-config")
async def get_template_onlyoffice_config(
    template_id: UUID,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get ONLYOFFICE editor configuration for viewing a template document.
    
    Returns:
        Configuration object for ONLYOFFICE editor initialization (read-only mode)
    """
    from app.utils.onlyoffice_utils import create_document_config, get_onlyoffice_editor_url
    from fastapi.responses import JSONResponse
    
    template_result = await db.execute(
        select(StudyTemplate).where(StudyTemplate.id == template_id)
    )
    template = template_result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Check if template has DOCX file
    if not hasattr(template, 'template_file_path') or not template.template_file_path:
        raise HTTPException(
            status_code=400,
            detail="Template does not have a DOCX file."
        )
    
    # Get user info
    user_id = current_user.get("user_id", "anonymous") if current_user else "anonymous"
    user_name = current_user.get("name", "User") if current_user else "User"
    
    # Create document URL using configured backend internal URL
    internal_base = _resolve_onlyoffice_internal_base(settings.backend_internal_url)
    document_url = f"{internal_base}/api/templates/{template_id}/template-file"
    
    # Generate document key (unique identifier for ONLYOFFICE)
    document_key = str(template.id)
    
    # Create configuration in view mode (read-only for templates)
    config = create_document_config(
        document_url=document_url,
        callback_url="",  # No callback needed for template viewing
        document_key=document_key,
        document_title=template.template_name,
        user_id=user_id,
        user_name=user_name,
        mode="view"  # Always view mode for templates
    )
    
    logger.info(f"ONLYOFFICE template config - document_url: {document_url}, template_id: {template_id}")
    
    return JSONResponse(content={
        "editorUrl": get_onlyoffice_editor_url(request),
        "config": config
    })


@router.patch("/templates/{template_id}/deactivate")
async def deactivate_template(
    template_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Deactivate a template (soft delete).
    Deactivated templates cannot be used for new agreements.
    """
    template_result = await db.execute(
        select(StudyTemplate).where(StudyTemplate.id == template_id)
    )
    template = template_result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    template.is_active = 'false'
    await db.flush()
    await db.commit()
    
    return {"message": "Template deactivated successfully"}


@router.put("/templates/{template_id}/placeholder-config", response_model=schemas.StudyTemplateResponse)
async def update_template_placeholder_config(
    template_id: UUID,
    config_data: schemas.PlaceholderConfigUpdate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Update placeholder configuration for a template.
    Allows setting which placeholders are editable in agreements created from this template.
    """
    template_result = await db.execute(
        select(StudyTemplate).where(StudyTemplate.id == template_id)
    )
    template = template_result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Update placeholder configuration
    template.placeholder_config = config_data.placeholder_config
    await db.flush()
    await db.commit()
    await db.refresh(template)
    
    return {
        "id": template.id,
        "study_id": template.study_id,
        "template_name": template.template_name,
        "template_type": template.template_type.value,
        "template_content": template.template_content if hasattr(template, 'template_content') and template.template_content else {"type": "doc", "content": []},
        "template_file_path": template.template_file_path if hasattr(template, 'template_file_path') else None,
        "placeholder_config": template.placeholder_config if hasattr(template, 'placeholder_config') and template.placeholder_config else {},
        "field_mappings": template.field_mappings if hasattr(template, 'field_mappings') and template.field_mappings else None,
        "created_by": template.created_by,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
        "is_active": template.is_active,
    }


@router.put("/templates/{template_id}/field-mappings", response_model=schemas.StudyTemplateResponse)
async def update_template_field_mappings(
    template_id: UUID,
    mappings_data: schemas.FieldMappingsUpdate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Update field mappings for a template.
    Allows configuring which data sources map to template placeholders.
    Format: {"PLACEHOLDER_NAME": "data_source.field_name"}
    Examples:
    - {"SITE_NAME": "site_profile.site_name"}
    - {"PI_NAME": "site_profile.pi_name"}
    - {"STUDY_TITLE": "agreement.title"}
    """
    template_result = await db.execute(
        select(StudyTemplate).where(StudyTemplate.id == template_id)
    )
    template = template_result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Allowed data sources for field mappings. Matches `resolve_field_value`
    # in app/modules/agreements/types/cta/service.py.
    ALLOWED_SOURCES = {"site_profile", "agreement", "study", "irb"}
    # Common plurals + variants we silently normalise to the canonical name.
    SOURCE_ALIASES = {
        "site_profiles": "site_profile",
        "sites": "site_profile",
        "site": "site_profile",
        "agreements": "agreement",
        "studies": "study",
        "irbs": "irb",
        "irb_admin": "irb",
        "irb_administrative_info": "irb",
    }

    normalised: Dict[str, str] = {}
    for placeholder_name, mapping_path in mappings_data.field_mappings.items():
        if not isinstance(placeholder_name, str) or not isinstance(mapping_path, str):
            raise HTTPException(
                status_code=400,
                detail="Invalid field_mappings format. All keys and values must be strings.",
            )
        parts = mapping_path.split(".", 1)
        if len(parts) != 2:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mapping path format for {placeholder_name}: {mapping_path}. Expected format: 'data_source.field_name'",
            )
        data_source = parts[0].strip().lower()
        field_name = parts[1].strip()
        data_source = SOURCE_ALIASES.get(data_source, data_source)
        if data_source not in ALLOWED_SOURCES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid data source for {placeholder_name}: {parts[0]}. "
                    f"Must be one of: {sorted(ALLOWED_SOURCES)}"
                ),
            )
        normalised[placeholder_name] = f"{data_source}.{field_name}"

    # Update field mappings (normalised form so resolver always sees canonical source)
    template.field_mappings = normalised
    logger.info(f"Updated field_mappings for template {template_id}: {mappings_data.field_mappings}")
    await db.flush()
    await db.commit()
    await db.refresh(template)
    
    return {
        "id": template.id,
        "study_id": template.study_id,
        "template_name": template.template_name,
        "template_type": template.template_type.value,
        "template_content": template.template_content if hasattr(template, 'template_content') and template.template_content else {"type": "doc", "content": []},
        "template_file_path": template.template_file_path if hasattr(template, 'template_file_path') else None,
        "placeholder_config": template.placeholder_config if hasattr(template, 'placeholder_config') and template.placeholder_config else {},
        "field_mappings": template.field_mappings if hasattr(template, 'field_mappings') and template.field_mappings else None,
        "created_by": template.created_by,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
        "is_active": template.is_active,
    }
