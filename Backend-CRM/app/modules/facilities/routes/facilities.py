"""
Read-only facilities feed served from the Data Platform HTTP API
(GET {DATA_PLATFORM_BASE_URL}/api/v1/facilities).

Replaces the previous direct asyncpg connection to the Azure facilities
Postgres (FACILITIES_DB_DSN), which was removed after the API migration was
verified. Frontend hits /api/facilities through the normal app-auth flow; the
HTTP details (X-App-Id header, pageSize clamp, shape mapping) live in
app/modules/facilities/services/data_platform_client.py.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_user
from app.modules.facilities.services import data_platform_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/facilities")
async def list_facilities(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    siteType: Optional[str] = Query(None, alias="siteType"),
    facilityType: Optional[str] = Query(None),
    _user=Depends(get_current_user),
):
    """List facilities from the Data Platform API."""
    try:
        return await data_platform_client.fetch_facilities(
            page=page,
            limit=limit,
            search=search,
            status=status,
            facility_type=facilityType or siteType,
        )
    except data_platform_client.DataPlatformError as exc:
        # Same graceful degradation the old DB path used: the UI shows an
        # empty list with a notice instead of a hard error.
        logger.warning("facilities source unavailable: %s", exc)
        return {
            "success": True,
            "data": [],
            "total": 0,
            "page": page,
            "limit": limit,
            "pages": 0,
            "sourceUnavailable": True,
            "detail": f"Facilities source unavailable: {exc}",
        }
