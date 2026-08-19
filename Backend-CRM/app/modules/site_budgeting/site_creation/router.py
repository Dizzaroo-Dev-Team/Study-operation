"""
FastAPI router for site creation module.
Mounted at /api/budgeting/site by main.py.

Endpoint mapping (Node → FastAPI):
  GET    /sites                        → GET    /api/budgeting/site/sites
  GET    /sites/study/:studyId         → GET    /api/budgeting/site/sites/study/{study_id}
  GET    /sites/facility/:facilityId   → GET    /api/budgeting/site/sites/facility/{facility_id}
  GET    /sites/investigator/:userId   → GET    /api/budgeting/site/sites/investigator/{user_id}
  GET    /sites/:id                    → GET    /api/budgeting/site/sites/{id}
  POST   /sites                        → POST   /api/budgeting/site/sites
  PATCH  /sites/:id                    → PATCH  /api/budgeting/site/sites/{id}
  DELETE /sites/:id                    → DELETE /api/budgeting/site/sites/{id}
  POST   /sites/:id/personnel          → POST   /api/budgeting/site/sites/{id}/personnel
  DELETE /sites/:id/personnel/:userId  → DELETE /api/budgeting/site/sites/{id}/personnel/{user_id}
  GET    /facilities                   → GET    /api/budgeting/site/facilities
  GET    /facilities/:id               → GET    /api/budgeting/site/facilities/{id}
  POST   /facilities                   → POST   /api/budgeting/site/facilities
  PATCH  /facilities/:id               → PATCH  /api/budgeting/site/facilities/{id}
  DELETE /facilities/:id               → DELETE /api/budgeting/site/facilities/{id}
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from app.auth import get_current_user
from app.db import get_db
from app.db.mongo import get_mongo_db
from app.modules.site_budgeting.site_creation import repository as repo
from app.modules.site_budgeting.site_creation import sites_pg
from app.modules.site_budgeting.site_creation.schemas import (
    AddPersonnelBody,
    FacilityCreate,
    FacilityUpdate,
    SiteCreate,
    SiteUpdate,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Site Creation"])


# ─── Facilities ───────────────────────────────────────────────────────────────

@router.get("/facilities")
async def get_all_facilities(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str = Query(default=''),
    siteType: str = Query(default=''),
    status: str = Query(default=''),
    country: str = Query(default=''),
    sortBy: str = Query(default='createdAt'),
    sortOrder: str = Query(default='desc'),
    _: dict[str, Any] = Depends(get_current_user),
    db=Depends(get_mongo_db),
):
    """Mirrors GET /facilities from facility.routes.js"""
    try:
        result = await repo.facility_get_all(
            db,
            page=page,
            limit=limit,
            search=search,
            site_type=siteType,
            status=status,
            country=country,
            sort_by=sortBy,
            sort_order=sortOrder,
        )
        return result
    except Exception as exc:
        logger.error(f"[site_creation] get_all_facilities error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching facilities")


@router.post("/facilities", status_code=status.HTTP_201_CREATED)
async def create_facility(
    body: FacilityCreate,
    _: dict[str, Any] = Depends(get_current_user),
    db=Depends(get_mongo_db),
):
    """Mirrors POST /facilities from facility.routes.js"""
    try:
        data = body.model_dump(exclude_none=False)
        # address is a nested model — convert to plain dict
        if data.get('address') and hasattr(data['address'], '__iter__'):
            pass  # already a dict from model_dump
        created = await repo.facility_create(db, data)
        return {'status': 'success', 'data': created}
    except Exception as exc:
        logger.error(f"[site_creation] create_facility error: {exc}", exc_info=True)
        if 'duplicate' in str(exc).lower() or '11000' in str(exc):
            raise HTTPException(status_code=400, detail="A facility with this code already exists")
        raise HTTPException(status_code=500, detail=f"Error creating facility: {exc}")


@router.get("/facilities/{facility_id}")
async def get_facility(
    facility_id: str,
    _: dict[str, Any] = Depends(get_current_user),
    db=Depends(get_mongo_db),
):
    """Mirrors GET /facilities/:id from facility.routes.js"""
    try:
        doc = await repo.facility_get_one(db, facility_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Facility not found")
        return {'status': 'success', 'data': doc}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[site_creation] get_facility error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching facility")


@router.patch("/facilities/{facility_id}")
async def update_facility(
    facility_id: str,
    body: FacilityUpdate,
    _: dict[str, Any] = Depends(get_current_user),
    db=Depends(get_mongo_db),
):
    """Mirrors PATCH /facilities/:id from facility.routes.js"""
    try:
        data = {k: v for k, v in body.model_dump().items() if v is not None}
        doc = await repo.facility_update(db, facility_id, data)
        if doc is None:
            raise HTTPException(status_code=404, detail="Facility not found")
        return {'status': 'success', 'data': doc}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[site_creation] update_facility error: {exc}", exc_info=True)
        if 'duplicate' in str(exc).lower():
            raise HTTPException(status_code=400, detail="A facility with this code already exists")
        raise HTTPException(status_code=500, detail="Error updating facility")


@router.delete("/facilities/{facility_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_facility(
    facility_id: str,
    _: dict[str, Any] = Depends(get_current_user),
    db=Depends(get_mongo_db),
):
    """Mirrors DELETE /facilities/:id from facility.routes.js"""
    try:
        deleted = await repo.facility_delete(db, facility_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Facility not found")
        return None
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[site_creation] delete_facility error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error deleting facility")


# ─── Sites ────────────────────────────────────────────────────────────────────
# NOTE: specific sub-paths (/study/, /facility/, /investigator/) MUST be
# registered BEFORE the generic /{id} route to avoid path conflicts.

@router.get("/sites/study/{study_id}")
async def get_sites_by_study(
    study_id: str,
    _: dict[str, Any] = Depends(get_current_user),
    db=Depends(get_mongo_db),
):
    """Mirrors GET /sites/study/:studyId from site.routes.js"""
    try:
        if not study_id:
            raise HTTPException(status_code=400, detail="studyId is required")
        sites = await repo.sites_by_study(db, study_id)
        if sites is None:
            raise HTTPException(status_code=404, detail="Study not found")
        return {'success': True, 'data': sites}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[site_creation] get_sites_by_study error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/sites/facility/{facility_id}")
async def get_sites_by_facility(
    facility_id: str,
    _: dict[str, Any] = Depends(get_current_user),
    db=Depends(get_mongo_db),
):
    """Mirrors GET /sites/facility/:facilityId from site.routes.js"""
    try:
        sites = await repo.sites_by_facility(db, facility_id)
        return {'success': True, 'data': sites}
    except Exception as exc:
        logger.error(f"[site_creation] get_sites_by_facility error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/sites/investigator/{user_id}")
async def get_sites_by_investigator(
    user_id: str,
    _: dict[str, Any] = Depends(get_current_user),
    db=Depends(get_mongo_db),
):
    """Mirrors GET /sites/investigator/:userId from site.routes.js"""
    try:
        sites = await repo.sites_by_investigator(db, user_id)
        return {'success': True, 'data': sites}
    except Exception as exc:
        logger.error(f"[site_creation] get_sites_by_investigator error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/sites")
async def get_all_sites(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    search: str = Query(default=''),
    study: str = Query(default=''),
    facility: str = Query(default=''),
    status: str = Query(default=''),
    principalInvestigator: str = Query(default=''),
    _: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List sites from Postgres (the same `sites` table that /api/sites reads)."""
    try:
        return await sites_pg.list_sites(
            db,
            page=page,
            limit=limit,
            search=search,
            study=study,
            facility=facility,
            status_q=status,
            principal_investigator=principalInvestigator,
        )
    except Exception as exc:
        logger.error(f"[site_creation] get_all_sites error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/sites/{site_id}")
async def get_site(
    site_id: str,
    _: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a single site (Postgres)."""
    try:
        doc = await sites_pg.get_site(db, site_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Site not found")
        return {'success': True, 'data': doc}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[site_creation] get_site error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/sites", status_code=status.HTTP_201_CREATED)
async def create_site(
    body: SiteCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a site in Postgres + map it to the chosen study + grant creator visibility."""
    try:
        data = body.model_dump()
        created = await sites_pg.create_site(
            db,
            data,
            current_user_id=current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "user_id", ""),
        )
        return {'success': True, 'data': created}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"[site_creation] create_site error: {exc}", exc_info=True)
        if 'duplicate' in str(exc).lower() or 'unique' in str(exc).lower():
            raise HTTPException(status_code=400, detail="Site with this code already exists")
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/sites/{site_id}")
async def update_site(
    site_id: str,
    body: SiteUpdate,
    _: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a site in Postgres."""
    try:
        data = {k: v for k, v in body.model_dump().items() if v is not None}
        updated = await sites_pg.update_site(db, site_id, data)
        if updated is None:
            raise HTTPException(status_code=404, detail="Site not found")
        return {'success': True, 'data': updated}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"[site_creation] update_site error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/sites/{site_id}")
async def delete_site(
    site_id: str,
    _: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a site (and its StudySite + UserRoleAssignment links) in Postgres."""
    try:
        deleted = await sites_pg.delete_site(db, site_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Site not found")
        return {'success': True, 'data': {'message': 'Site deleted successfully'}}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[site_creation] delete_site error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sites/{site_id}/personnel")
async def add_personnel(
    site_id: str,
    body: AddPersonnelBody,
    _: dict[str, Any] = Depends(get_current_user),
    db=Depends(get_mongo_db),
):
    """Mirrors POST /sites/:id/personnel from site.routes.js"""
    try:
        site = await repo.site_get_one(db, site_id)
        if site is None:
            raise HTTPException(status_code=404, detail="Site not found")
        updated = await repo.site_add_personnel(db, site_id, body.userId, body.role)
        return {'success': True, 'data': updated}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[site_creation] add_personnel error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.delete("/sites/{site_id}/personnel/{user_id}")
async def remove_personnel(
    site_id: str,
    user_id: str,
    _: dict[str, Any] = Depends(get_current_user),
    db=Depends(get_mongo_db),
):
    """Mirrors DELETE /sites/:id/personnel/:userId from site.routes.js"""
    try:
        site = await repo.site_get_one(db, site_id)
        if site is None:
            raise HTTPException(status_code=404, detail="Site not found")
        updated = await repo.site_remove_personnel(db, site_id, user_id)
        return {'success': True, 'data': updated}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[site_creation] remove_personnel error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")
