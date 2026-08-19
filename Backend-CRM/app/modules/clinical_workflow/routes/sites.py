"""REST API: site-level study-id lookup."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_optional
from app.db import get_db
from app.models import Site, Study, StudySite

router = APIRouter(tags=["Clinical Workflow"])


@router.get("/sites/{site_id}/study-id")
async def get_site_study_id(
    site_id: str,
    study_id: Optional[str] = Query(
        None,
        description=(
            "Selected study identifier (UUID or external study_id string). "
            "If provided, this will be used instead of the site's stored study_id. "
            "This allows a single site (e.g. site01) to be used for multiple studies."
        ),
    ),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get study ID (UUID) for a site.

    NOTE:
    - Originally this always returned the study attached to the Site row.
    - For your setup, a single site (site01) is used for many studies.
    - The frontend sends the selected study when fetching feasibility questions.
    - So if a study_id is provided, we resolve and return THAT study's UUID,
      ignoring the site's stored study_id.
    """
    # If the caller provides an explicit study_id (selected in UI), prefer that.
    if study_id:
        # Resolve study by UUID or external study_id string
        try:
            study_uuid = UUID(str(study_id))
            study_result = await db.execute(select(Study).where(Study.id == study_uuid))
            study = study_result.scalar_one_or_none()
        except (ValueError, TypeError):
            study_result = await db.execute(select(Study).where(Study.study_id == study_id))
            study = study_result.scalar_one_or_none()

        if study:
            # Return the canonical UUID that the feasibility endpoint expects
            return {"study_id": str(study.id)}

    # Fallback: behave like before, but resolve study via StudySite mapping instead of sites.study_id
    try:
        site_uuid = UUID(str(site_id))
        site_result = await db.execute(select(Site).where(Site.id == site_uuid))
        site = site_result.scalar_one_or_none()
    except (ValueError, TypeError):
        site_result = await db.execute(select(Site).where(Site.site_id == site_id))
        site = site_result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Capture the DB UUID for this site once so we don't trigger any lazy loads later.
    # Accessing ORM attributes like site.id after the object is expired can cause
    # async IO in unexpected places (MissingGreenlet). Using this local value avoids that.
    site_db_id = site.id

    study_site_result = await db.execute(
        select(StudySite)
        .where(StudySite.site_id == site.id)
        .order_by(StudySite.created_at)
    )
    study_site = study_site_result.scalars().first()

    if not study_site:
        raise HTTPException(status_code=404, detail="Study mapping not found for site")

    # Return the canonical UUID that downstream endpoints expect
    return {"study_id": str(study_site.study_id)}

