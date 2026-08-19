"""
HTTP client for the Data Platform facilities API.

Sole source for facilities data (GET {DATA_PLATFORM_BASE_URL}/api/v1/facilities):
the /api/facilities list route and the site-creation facility lookups in
site_budgeting/site_creation/sites_pg.py. Replaced the former direct asyncpg
access to the Azure facilities DB (FACILITIES_DB_DSN), removed after this
migration was verified.

Upstream contract (observed against the local Data Platform, 2026-07):
  - requires an X-App-Id header (400 without it); "study_operations" is allowed
  - query params: search, status, facilityType, country/state/city, page,
    pageSize (1..100 — smaller than the 200 our route allows, so we clamp)
  - response: {"items": [...], "total": n, "page": n, "pageSize": n} with
    camelCase item fields matching the frontend shape, but nullable where the
    legacy route returned "" — the mapper normalizes that.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import UUID

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

FACILITIES_PATH = "/api/v1/facilities"

# The upstream API rejects pageSize > 100; our route historically allowed
# limit up to 200.
_UPSTREAM_MAX_PAGE_SIZE = 100

# Fields the frontend expects as "" rather than null (contract inherited from
# the old DB implementation's row mapping).
_EMPTY_STRING_FIELDS = (
    "campusName",
    "street",
    "addressLine2",
    "city",
    "state",
    "country",
    "postalCode",
    "deptName",
    "deptAddress",
    "deptPhone",
    "deptEmail",
)


class DataPlatformError(Exception):
    """Raised when the Data Platform facilities API cannot serve the request."""


def is_configured() -> bool:
    return bool(settings.data_platform_base_url)


def _map_item(item: dict) -> dict:
    """Normalize an upstream facility item onto the legacy frontend shape."""
    mapped = {
        "id": str(item.get("id", "")),
        "facilityCode": item.get("facilityCode"),
        "name": item.get("name"),
        "facilityType": item.get("facilityType"),
        "status": item.get("status"),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }
    for field in _EMPTY_STRING_FIELDS:
        mapped[field] = item.get(field) or ""
    return mapped


def _to_db_row(item: dict) -> dict:
    """
    Map an upstream camelCase facility item onto the snake_case row shape the
    legacy asyncpg queries returned, so sites_pg.py consumers work unchanged.
    `id` is a UUID object like asyncpg returned — it is assigned directly to
    the Site.facility_external_id UUID column.
    """
    try:
        row_id = UUID(str(item.get("id")))
    except (ValueError, TypeError):
        row_id = item.get("id")
    return {
        "id": row_id,
        "iam_facility_id": item.get("iamFacilityId"),
        "facility_code": item.get("facilityCode"),
        "name": item.get("name"),
        "facility_type": item.get("facilityType"),
        "campus_name": item.get("campusName"),
        "street": item.get("street"),
        "address_line2": item.get("addressLine2"),
        "city": item.get("city"),
        "state": item.get("state"),
        "country": item.get("country"),
        "postal_code": item.get("postalCode"),
        "dept_name": item.get("deptName"),
        "dept_address": item.get("deptAddress"),
        "dept_phone": item.get("deptPhone"),
        "dept_email": item.get("deptEmail"),
        "status": item.get("status"),
        "created_at": item.get("createdAt"),
        "updated_at": item.get("updatedAt"),
    }


def _headers() -> dict:
    return {"X-App-Id": settings.data_platform_facilities_app_id}


async def _get_one(client: httpx.AsyncClient, url: str) -> Optional[dict]:
    """GET a single-facility endpoint. 404 → None; other failures raise."""
    try:
        resp = await client.get(url, headers=_headers())
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("facilities API unreachable (%s): %s", url, exc)
        raise DataPlatformError(f"Data Platform unreachable: {exc}") from exc
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        logger.warning("facilities API returned HTTP %s for %s: %s", resp.status_code, url, resp.text[:500])
        raise DataPlatformError(f"Data Platform returned HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("facilities API returned non-JSON body for %s", url)
        raise DataPlatformError("Data Platform returned a non-JSON response") from exc
    if not isinstance(payload, dict) or not payload.get("id"):
        logger.warning("facilities API returned unexpected payload for %s: %r", url, payload)
        raise DataPlatformError("Data Platform returned an unexpected facility payload")
    return payload


async def fetch_facility_row(ref: str) -> Optional[dict]:
    """
    Resolve one facility and return it in the legacy DB-row (snake_case)
    shape, or None when it does not exist.

    Accepts any of the identifiers callers historically passed:
      - Data Platform facility id (UUID)         → GET /facilities/{id}
      - legacy Azure/IAM facility id (UUID) — the ids stored on existing
        Site.facility_external_id rows           → GET /facilities/by-iam-id/{id}
      - facility code (non-UUID string)          → GET /facilities/by-code/{code}
    """
    if not ref:
        return None
    base_url = (settings.data_platform_base_url or "").rstrip("/")
    if not base_url:
        raise DataPlatformError("DATA_PLATFORM_BASE_URL is not configured on the server.")

    async with httpx.AsyncClient(timeout=settings.facilities_api_timeout_seconds) as client:
        try:
            UUID(str(ref))
        except (ValueError, TypeError):
            item = await _get_one(client, f"{base_url}{FACILITIES_PATH}/by-code/{ref}")
        else:
            item = await _get_one(client, f"{base_url}{FACILITIES_PATH}/{ref}")
            if item is None:
                # Legacy sites stored the old Azure/IAM facility id.
                item = await _get_one(client, f"{base_url}{FACILITIES_PATH}/by-iam-id/{ref}")
    return _to_db_row(item) if item else None


async def fetch_facility_rows_map(refs: list) -> dict:
    """
    Best-effort batch hydration: resolve each ref concurrently and return
    {original ref: db-row dict} for the ones that resolved. Refs may be UUID
    objects (Site.facility_external_id values) or strings; keys are returned
    untouched so callers can .get() with what they passed in.
    """
    unique = list(dict.fromkeys(refs))
    results = await asyncio.gather(
        *(fetch_facility_row(str(r)) for r in unique), return_exceptions=True
    )
    out: dict = {}
    for ref, row in zip(unique, results):
        if isinstance(row, dict):
            out[ref] = row
        elif isinstance(row, Exception):
            logger.warning("facilities API hydration failed for %s: %s", ref, row)
    return out


async def fetch_facilities(
    *,
    page: int,
    limit: int,
    search: Optional[str] = None,
    status: Optional[str] = None,
    facility_type: Optional[str] = None,
) -> dict:
    """
    Fetch one page of facilities from the Data Platform API and return it in
    the exact envelope the frontend already consumes:
      {"success", "data", "total", "page", "limit", "pages"}

    Raises DataPlatformError on any transport, HTTP, or payload problem so the
    route can decide how to degrade.
    """
    base_url = (settings.data_platform_base_url or "").rstrip("/")
    if not base_url:
        raise DataPlatformError("DATA_PLATFORM_BASE_URL is not configured on the server.")

    page_size = min(limit, _UPSTREAM_MAX_PAGE_SIZE)
    if page_size < limit:
        logger.info(
            "facilities API: clamping requested limit %s to upstream max %s",
            limit,
            _UPSTREAM_MAX_PAGE_SIZE,
        )

    params: dict = {"page": page, "pageSize": page_size}
    if search:
        params["search"] = search
    if status:
        params["status"] = status
    if facility_type:
        params["facilityType"] = facility_type

    url = f"{base_url}{FACILITIES_PATH}"
    headers = {"X-App-Id": settings.data_platform_facilities_app_id}

    try:
        async with httpx.AsyncClient(timeout=settings.facilities_api_timeout_seconds) as client:
            resp = await client.get(url, params=params, headers=headers)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("facilities API unreachable (%s): %s", url, exc)
        raise DataPlatformError(f"Data Platform unreachable: {exc}") from exc

    if resp.status_code != 200:
        body = resp.text[:500]
        logger.warning("facilities API returned HTTP %s: %s", resp.status_code, body)
        raise DataPlatformError(f"Data Platform returned HTTP {resp.status_code}")

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("facilities API returned non-JSON body: %s", resp.text[:500])
        raise DataPlatformError("Data Platform returned a non-JSON response") from exc

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        logger.warning("facilities API payload missing 'items' list: %r", payload)
        raise DataPlatformError("Data Platform response missing 'items' list")

    try:
        total = int(payload.get("total", len(items)))
    except (TypeError, ValueError):
        logger.warning("facilities API returned non-numeric total: %r", payload.get("total"))
        total = len(items)

    pages = (total + page_size - 1) // page_size if total else 0
    return {
        "success": True,
        "data": [_map_item(i) for i in items if isinstance(i, dict)],
        "total": total,
        "page": page,
        "limit": page_size,
        "pages": pages,
    }
