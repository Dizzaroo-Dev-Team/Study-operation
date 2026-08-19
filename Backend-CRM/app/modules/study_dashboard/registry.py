"""
Data Platform Study Registry client.

The Data Platform exposes the studies it hosts (one Postgres database per
study) at:

    GET {DATA_PLATFORM_BASE_URL}/api/v1/study-registry
    GET {DATA_PLATFORM_BASE_URL}/api/v1/study-registry/{study_id}

Each item carries the study's database coordinates:

    {
      "studyId": "10011",
      "studyName": "Destiny B04",
      "databaseName": "study_10011",
      "connectionString": "postgresql://user:pass@host:5432/study_10011",
      "activeFlag": true
    }

This module follows the conventions of
``app.modules.facilities.services.data_platform_client``: httpx.AsyncClient,
``settings.data_platform_base_url`` as the base, and a module-local error type
so routes can decide how to degrade.

Connection strings are considered SECRETS — they are resolved here (with a
short TTL cache so per-widget dashboard requests don't stampede the registry)
and never leave the backend. The routes only ever expose studyId / studyName /
databaseName to the browser.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

STUDY_REGISTRY_PATH = "/api/v1/study-registry"

# Resolved registry items, keyed by studyId. Entries expire after
# _CACHE_TTL_SECONDS so a study whose connection details change on the Data
# Platform is picked up without a backend restart.
_CACHE_TTL_SECONDS = 60.0
_study_cache: dict[str, tuple[float, dict]] = {}


class StudyRegistryError(Exception):
    """Raised when the Study Registry API cannot serve the request."""


def is_configured() -> bool:
    return bool(settings.data_platform_base_url)


def _base_url() -> str:
    base_url = (settings.data_platform_base_url or "").rstrip("/")
    if not base_url:
        raise StudyRegistryError("DATA_PLATFORM_BASE_URL is not configured on the server.")
    return base_url


def _normalize_item(item: dict) -> Optional[dict]:
    """Coerce an upstream registry item into the shape the rest of the module
    relies on. Returns None for malformed entries (logged, not fatal)."""
    if not isinstance(item, dict):
        return None
    study_id = item.get("studyId")
    if study_id is None or str(study_id).strip() == "":
        logger.warning("study registry item missing studyId: %r", item)
        return None
    return {
        "studyId": str(study_id),
        "studyName": str(item.get("studyName") or f"Study {study_id}"),
        "databaseName": item.get("databaseName"),
        "connectionString": item.get("connectionString"),
        "activeFlag": bool(item.get("activeFlag", False)),
    }


async def _get_json(url: str) -> dict | list:
    headers = {"X-App-Id": settings.data_platform_facilities_app_id}
    try:
        async with httpx.AsyncClient(timeout=settings.facilities_api_timeout_seconds) as client:
            resp = await client.get(url, headers=headers)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("study registry unreachable (%s): %s", url, exc)
        raise StudyRegistryError(f"Study Registry unreachable: {exc}") from exc

    if resp.status_code == 404:
        raise StudyRegistryError("Study not found in registry")
    if resp.status_code != 200:
        logger.warning("study registry returned HTTP %s: %s", resp.status_code, resp.text[:500])
        raise StudyRegistryError(f"Study Registry returned HTTP {resp.status_code}")

    try:
        return resp.json()
    except ValueError as exc:
        logger.warning("study registry returned non-JSON body: %s", resp.text[:500])
        raise StudyRegistryError("Study Registry returned a non-JSON response") from exc


async def fetch_registry_studies() -> list[dict]:
    """All studies from the registry (normalized, including inactive ones —
    callers filter on activeFlag). Refreshes the resolver cache as a side
    effect so a list call warms subsequent per-study lookups."""
    payload = await _get_json(f"{_base_url()}{STUDY_REGISTRY_PATH}")
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        logger.warning("study registry payload missing 'items' list: %r", payload)
        raise StudyRegistryError("Study Registry response missing 'items' list")

    now = time.monotonic()
    studies: list[dict] = []
    for raw in items:
        normalized = _normalize_item(raw)
        if normalized is None:
            continue
        studies.append(normalized)
        _study_cache[normalized["studyId"]] = (now, normalized)
    return studies


async def fetch_registry_study(study_id: str) -> Optional[dict]:
    """One study by registry id, honouring the TTL cache. Returns None when
    the registry has no such study."""
    cached = _study_cache.get(study_id)
    if cached is not None:
        stored_at, item = cached
        if time.monotonic() - stored_at < _CACHE_TTL_SECONDS:
            return item

    try:
        payload = await _get_json(f"{_base_url()}{STUDY_REGISTRY_PATH}/{study_id}")
    except StudyRegistryError as exc:
        if "not found" in str(exc).lower():
            return None
        # If the registry is momentarily down but we hold a stale entry, keep
        # serving it — dashboards degrade better on stale coordinates than 503s.
        if cached is not None:
            logger.warning("study registry lookup failed for %s, serving stale cache: %s", study_id, exc)
            return cached[1]
        raise

    item = payload.get("item") if isinstance(payload, dict) and "item" in payload else payload
    normalized = _normalize_item(item if isinstance(item, dict) else {})
    if normalized is not None:
        _study_cache[normalized["studyId"]] = (time.monotonic(), normalized)
    return normalized


async def resolve_connection_string(study_id: str) -> str:
    """Connection string for a registry study, for backend use only.

    Raises StudyRegistryError when the study is unknown, inactive, or has no
    connection details.
    """
    study = await fetch_registry_study(study_id)
    if study is None:
        raise StudyRegistryError(f"Study '{study_id}' not found in registry")
    if not study.get("activeFlag"):
        raise StudyRegistryError(f"Study '{study_id}' is not active")
    conn = study.get("connectionString")
    if not conn:
        raise StudyRegistryError(f"Study '{study_id}' has no connection string in registry")
    return str(conn)
