from __future__ import annotations

import json
import logging
from functools import wraps
from typing import Any, Awaitable, Callable, Optional, TypeVar, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_optional
from app.config import settings
from app.db import get_db

from . import notification_templates, services
from .schemas import (
    PresignRequest,
    ProtocolMetadataExtractRequest,
    SitePackageCreateRequest,
    SitePackageListQuery,
    SitePackageUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["site-packages"])

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def _handle_route_errors(operation: str) -> Callable[[F], F]:
    """Wrap route handlers and return consistent JSON error payloads."""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error("[SitePackages] %s error: %s", operation, e, exc_info=True)
                status_code = 500
                detail: Any = str(e)
                if isinstance(e, HTTPException):
                    status_code = int(e.status_code)
                    detail = e.detail
                elif hasattr(e, "status_code") and hasattr(e, "detail"):
                    status_code = int(getattr(e, "status_code"))
                    detail = getattr(e, "detail")
                return JSONResponse(status_code=status_code, content={"success": False, "error": detail})

        return cast(F, wrapper)

    return decorator


@router.get("/notification-templates")
@_handle_route_errors("get_notification_templates")
async def get_notification_templates():
    """Notification wizard registry: categories, types (fields + documents + due days), field library.

    Backed by MongoDB (auto-seeded from defaults on first call) so templates can
    be edited without a code deploy.
    """
    data = await notification_templates.get_notification_registry()
    return {"success": True, "data": data}


@router.post("/site-packages", status_code=201)
@_handle_route_errors("create_site_package")
async def create_site_package(
    payload: SitePackageCreateRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    logger.info("[SitePackages] POST /site-packages received")
    created = await services.create_site_package(payload=payload, db=db, current_user=current_user)
    return {
        "success": True,
        "data": {"sitePackage": created},
        "message": "Site package created successfully",
    }


@router.get("/site-packages")
@_handle_route_errors("list_site_packages")
async def list_site_packages(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    study: str = Query(..., description="Study id — required; list is scoped to study + site"),
    site: str = Query(..., description="Site id — required; list is scoped to study + site"),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = SitePackageListQuery(page=page, limit=limit, study=study, site=site, status=status)
    logger.info("[SitePackages] GET /site-packages page=%s limit=%s", page, limit)
    return await services.list_site_packages(query=query, db=db)


# Static paths must be registered before `/site-packages/{id}` so `id` never captures e.g. `fetch-document`.
@router.post("/site-packages/presign")
@_handle_route_errors("presign_read")
async def presign_read(file_request: PresignRequest):
    sas_url = services.presign_read(file_url=file_request.fileUrl)
    return {"success": True, "presignedUrl": sas_url}


@router.post("/site-packages/fetch-document")
@_handle_route_errors("fetch_document_bytes")
async def fetch_document_bytes(
    file_request: PresignRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """
    Server-side download of a blob SAS URL so the SPA can bundle ISF / remote files into a ZIP
    without browser CORS blocking Azure Blob GET requests.
    """
    data, media_type = await services.fetch_remote_blob_bytes_for_client(file_url=file_request.fileUrl)
    return Response(content=data, media_type=media_type)


@router.post("/site-packages/extract-protocol-metadata")
@_handle_route_errors("extract_protocol_metadata")
async def extract_protocol_metadata(
    payload: ProtocolMetadataExtractRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    _ = current_user
    data = await services.extract_protocol_metadata_from_isf_import(
        file_url=payload.fileUrl,
        max_pages=int(payload.maxPages or 5),
    )
    return {"success": True, "data": data}


@router.get("/site-packages/{id}")
@_handle_route_errors("get_site_package_by_id")
async def get_site_package_by_id(
    id: str,
    study: str = Query(..., description="Study id (UUID or external study_id) — required for access control"),
    site: str = Query(..., description="Site id (UUID or external site_id) — required for access control"),
    db: AsyncSession = Depends(get_db),
):
    pkg = await services.get_site_package_by_id(pkg_id=id, db=db, study_value=study, site_value=site)
    if not pkg:
        return JSONResponse(status_code=404, content={"success": False, "error": "Package not found"})
    return {"success": True, "data": pkg}


@router.delete("/site-packages/{id}")
@_handle_route_errors("delete_site_package")
async def delete_site_package(
    id: str,
    study: str = Query(..., description="Study id — required for access control"),
    site: str = Query(..., description="Site id — required for access control"),
    db: AsyncSession = Depends(get_db),
):
    ok = await services.delete_site_package(pkg_id=id, db=db, study_value=study, site_value=site)
    if not ok:
        return JSONResponse(status_code=404, content={"success": False, "error": "Package not found"})
    return {"success": True, "data": {"message": "Deleted"}}


@router.patch("/site-packages/{id}")
@_handle_route_errors("update_site_package")
async def update_site_package(
    id: str,
    updates: SitePackageUpdateRequest,
    study: str = Query(..., description="Study id — required for access control"),
    site: str = Query(..., description="Site id — required for access control"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    pkg = await services.update_site_package(
        pkg_id=id,
        updates=updates,
        db=db,
        current_user=current_user,
        study_value=study,
        site_value=site,
    )
    return {"success": True, "data": pkg}


@router.post("/site-packages/upload", status_code=201)
@_handle_route_errors("upload_document")
async def upload_document(
    file: UploadFile = File(...),
    study_id: str = Form(...),
    site_id: str = Form(...),
    document_type: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await services.upload_site_packages_document(
        file=file,
        study_id=study_id,
        site_id=site_id,
        document_type=document_type,
        db=db,
    )
    return {"success": True, "data": result}


@router.post("/site-packages/{id}/documents")
@_handle_route_errors("upload_site_package_document")
async def upload_site_package_document(
    id: str,
    file: UploadFile = File(...),
    study_id: str = Form(..., description="Study id — must match the package"),
    site_id: str = Form(..., description="Site id — must match the package"),
    documentName: Optional[str] = Form(None),
    documentType: Optional[str] = Form(None),
    tmfDocumentId: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    return await services.upload_site_package_document_to_package(
        pkg_id=id,
        file=file,
        document_name=documentName,
        document_type=documentType,
        tmf_document_id=tmfDocumentId,
        source=source,
        db=db,
        current_user=current_user,
        study_value=study_id,
        site_value=site_id,
    )


@router.post("/site-packages/generate-document")
@_handle_route_errors("generate_site_package_document")
async def generate_site_package_document(
    study_id: str = Form(...),
    site_id: str = Form(...),
    document_type: str = Form(...),
    document_name: Optional[str] = Form(None),
    output_format: str = Form("docx"),
    required_document_names: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    parsed_required_names: Optional[list[str]] = None
    if required_document_names:
        try:
            raw = json.loads(required_document_names)
            if isinstance(raw, list):
                parsed_required_names = [str(x).strip() for x in raw if str(x).strip()]
        except Exception:
            parsed_required_names = None

    result = await services.generate_site_package_document(
        study_id=study_id,
        site_id=site_id,
        document_type=document_type,
        document_name=document_name,
        output_format=output_format,
        required_document_names=parsed_required_names,
        db=db,
    )
    headers = {
        "Content-Disposition": f"attachment; filename=\"{result['filename']}\"",
        "X-Generated-Filename": result["filename"],
        "X-Required-Docs-Count": str(result.get("required_docs_count", "")),
        "X-Required-Docs-Source": str(result.get("required_docs_source", "")),
    }
    return Response(content=result["content"], media_type=result["mime_type"], headers=headers)


@router.post("/site-packages/generate-cover-letter-assets")
@_handle_route_errors("generate_cover_letter_assets")
async def generate_cover_letter_assets(
    study_id: str = Form(...),
    site_id: str = Form(...),
    document_type: str = Form(...),
    document_name: Optional[str] = Form(None),
    required_document_names: Optional[str] = Form(None),
    protocol_metadata: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    parsed_required_names: Optional[list[str]] = None
    parsed_protocol_metadata: Optional[dict[str, Any]] = None
    if required_document_names:
        try:
            raw = json.loads(required_document_names)
            if isinstance(raw, list):
                parsed_required_names = [str(x).strip() for x in raw if str(x).strip()]
        except Exception:
            parsed_required_names = None
    if protocol_metadata:
        try:
            raw_meta = json.loads(protocol_metadata)
            if isinstance(raw_meta, dict):
                parsed_protocol_metadata = raw_meta
        except Exception:
            parsed_protocol_metadata = None

    data = await services.generate_cover_letter_assets(
        study_id=study_id,
        site_id=site_id,
        document_type=document_type,
        document_name=document_name,
        required_document_names=parsed_required_names,
        protocol_metadata=parsed_protocol_metadata,
        db=db,
    )
    return {"success": True, "data": data}


@router.get("/site-packages/{id}/cover-letter-onlyoffice-document")
@_handle_route_errors("cover_letter_onlyoffice_document")
async def cover_letter_onlyoffice_document(
    id: str,
    study: str = Query(..., description="Study id — required for access control"),
    site: str = Query(..., description="Site id — required for access control"),
    document_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    data, media_type, filename = await services.get_cover_letter_onlyoffice_document(
        pkg_id=id,
        study_value=study,
        site_value=site,
        document_name=document_name,
        db=db,
    )
    headers = {
        "Content-Disposition": f'inline; filename="{filename}.docx"',
        "X-Content-Type-Options": "nosniff",
    }
    return Response(content=data, media_type=media_type, headers=headers)


@router.get("/site-packages/{id}/cover-letter-onlyoffice-config")
@_handle_route_errors("cover_letter_onlyoffice_config")
async def cover_letter_onlyoffice_config(
    id: str,
    request: Request,
    study: str = Query(..., description="Study id — required for access control"),
    site: str = Query(..., description="Site id — required for access control"),
    document_name: Optional[str] = Query(None),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    from app.utils.onlyoffice_utils import get_onlyoffice_editor_url

    payload = await services.get_cover_letter_onlyoffice_config(
        pkg_id=id,
        study_value=study,
        site_value=site,
        document_name=document_name,
        current_user=current_user,
        db=db,
    )
    return {
        "success": True,
        "editorUrl": get_onlyoffice_editor_url(request),
        "config": payload["config"],
        "data": payload.get("document") or {},
    }


@router.get("/site-packages/{id}/cover-letter-onlyoffice-status")
@_handle_route_errors("cover_letter_onlyoffice_status")
async def cover_letter_onlyoffice_status(
    id: str,
    study: str = Query(..., description="Study id — required for access control"),
    site: str = Query(..., description="Site id — required for access control"),
    document_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    data = await services.get_cover_letter_onlyoffice_status(
        pkg_id=id,
        study_value=study,
        site_value=site,
        document_name=document_name,
        db=db,
    )
    return {"success": True, "data": data}


@router.options("/site-packages/{id}/cover-letter-onlyoffice-callback")
async def cover_letter_onlyoffice_callback_options(id: str):
    return {"error": 0}


@router.post("/site-packages/{id}/cover-letter-onlyoffice-callback")
async def cover_letter_onlyoffice_callback(
    id: str,
    request: Request,
    study: str = Query(..., description="Study id — required for access control"),
    site: str = Query(..., description="Site id — required for access control"),
    document_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from app.utils.onlyoffice_utils import verify_jwt_token

    try:
        callback_data = await request.json()
    except Exception:
        callback_data = {}

    try:
        # ONLYOFFICE sends JWT in callback body payload, not auth header.
        if settings.onlyoffice_jwt_enabled and settings.onlyoffice_jwt_secret:
            token = callback_data.get("token")
            if token:
                decoded = verify_jwt_token(token)
                if not decoded:
                    logger.warning("Invalid JWT token in site-package ONLYOFFICE callback")
                    return {"error": 1}

        result = await services.handle_cover_letter_onlyoffice_callback(
            pkg_id=id,
            study_value=study,
            site_value=site,
            document_name=document_name,
            callback_payload=callback_data,
            db=db,
        )
        return result
    except Exception as e:
        logger.error("Site-package ONLYOFFICE callback error: %s", e, exc_info=True)
        return {"error": 1}

