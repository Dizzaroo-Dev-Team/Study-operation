"""REST API: site status dashboard endpoints (study summary, country rollup, site list, site detail)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.auth import get_current_user_optional
from app.db import get_db
from app.models import PrimarySiteStatus
from app.modules.sites.services.site_status_service import (
    get_country_site_counts,
    get_site_status_detail,
    get_sites_by_status,
    get_study_status_summary,
)

router = APIRouter(tags=["Clinical Workflow"])


@router.get("/site-status/summary", response_model=schemas.StudyStatusSummary)
async def get_site_status_summary(
    study_id: str = Query(..., description="Study UUID or external study_id string"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Study-level Site Status dashboard summary.

    - Site status is the source of truth
    - Country and Study statuses are derived automatically
    - READ-ONLY - no status changes are exposed here
    """
    result = await get_study_status_summary(db, study_id)
    if not result:
        raise HTTPException(status_code=404, detail="Study not found or no sites")

    _study, summary = result
    return summary


@router.get("/site-status/countries", response_model=List[schemas.CountryStatusSummary])
async def get_site_status_countries(
    study_id: str = Query(..., description="Study UUID or external study_id string"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Country-wise site counts and derived status for a given study."""
    return await get_country_site_counts(db, study_id)


@router.get("/site-status/sites")
async def get_site_status_sites(
    study_id: str = Query(..., description="Study UUID or external study_id string"),
    status: Optional[PrimarySiteStatus] = Query(
        None,
        description="Filter by primary site status (optional)",
    ),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """List sites for a given study, optionally filtered by primary status."""
    return await get_sites_by_status(db, study_id, status=status)


@router.get("/site-status/sites/{site_id}", response_model=schemas.SiteStatusDetail)
async def get_site_status_site_detail(
    site_id: str,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Detailed site status view with full audit trail.

    - Current primary status (highlighted in UI)
    - Chronological status history
    - Secondary status details (CDA, SFQ, SQV, EC, SIV etc.) via metadata
    """
    detail = await get_site_status_detail(db, site_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Site not found")
    return detail
