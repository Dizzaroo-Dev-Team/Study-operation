"""
IAM hub SSO helpers — companion to the IAM Kafka sync at
`app/integrations/kafka/` (collection contracts in `models/sync_models.py`,
user upsert in `events/user_event.py`).

What this module does:
  1. `verify_hub_token` — slow-path token verification against the hub's
     `/api/auth/verify` endpoint. Cached in-process for `iam_auth_cache_ttl_seconds`
     (default 60s) keyed by token, so each browser session typically costs one
     hub round-trip per minute regardless of CRM API call rate.
  2. `entitlement_ok` — checks that the verified user has an active entry for
     this CRM in their `applications` array (key = `IAM_APPLICATION_ID`).
  3. `map_hub_role_to_user_role` — coerces hub role strings into the local
     `UserRole` enum. Identity match by `.value` since the enum values already
     match the hub's lowercase strings; unknown / null falls back to PARTICIPANT.

The cache MUST evict on 401 so a revoked / expired token cannot keep
authenticating from a stale entry.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import httpx

from app.config import settings
from app.models import UserRole

logger = logging.getLogger(__name__)


# ─── In-process TTL cache keyed by raw token ────────────────────────────────

_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = asyncio.Lock()


def _cache_get(token: str) -> Optional[dict]:
    entry = _cache.get(token)
    if entry is None:
        return None
    expires_at, payload = entry
    if expires_at <= time.monotonic():
        _cache.pop(token, None)
        return None
    return payload


def _cache_set(token: str, payload: dict) -> None:
    ttl = max(int(settings.iam_auth_cache_ttl_seconds or 60), 1)
    _cache[token] = (time.monotonic() + ttl, payload)


def _cache_evict(token: str) -> None:
    _cache.pop(token, None)


# ─── Hub verify ─────────────────────────────────────────────────────────────


class HubAuthError(Exception):
    """Raised when the hub rejects a token (401) or is unreachable."""


async def verify_hub_token(token: str) -> dict:
    """
    Verify a hub-issued bearer token. Returns the parsed JSON response from the
    hub's `/api/auth/verify` endpoint. Raises HubAuthError on 401, hub
    unreachable, or invalid response shape.

    Cached for `iam_auth_cache_ttl_seconds` to amortise the hub round-trip.
    """
    if not token:
        raise HubAuthError("empty token")

    cached = _cache_get(token)
    if cached is not None:
        return cached

    base = (settings.iam_hub_base_url or "").rstrip("/")
    if not base:
        raise HubAuthError("IAM_HUB_BASE_URL is not configured")

    path = settings.iam_hub_verify_path or "/api/auth/verify"
    url = f"{base}{path}"

    headers = {
        "Authorization": f"Bearer {token}",
        # Harmless against non-ngrok hosts; required against the dev ngrok host
        # so we don't get the HTML interstitial page instead of JSON.
        "ngrok-skip-browser-warning": "1",
        "Accept": "application/json",
    }

    async with _cache_lock:
        # Re-check cache inside the lock to avoid duplicate hub calls under burst.
        cached = _cache_get(token)
        if cached is not None:
            return cached
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers)
        except (httpx.HTTPError, OSError) as exc:
            logger.exception("[iam-auth] hub verify network error: %s", exc)
            raise HubAuthError(f"hub unreachable: {exc}") from exc

        if resp.status_code == 401 or resp.status_code == 403:
            _cache_evict(token)
            raise HubAuthError(f"hub rejected token (status={resp.status_code})")
        if resp.status_code >= 400:
            logger.error(
                "[iam-auth] hub verify returned %d: %s", resp.status_code, resp.text[:200]
            )
            raise HubAuthError(f"hub error (status={resp.status_code})")

        try:
            payload = resp.json()
        except ValueError as exc:
            logger.exception("[iam-auth] hub verify returned non-JSON: %s", resp.text[:200])
            raise HubAuthError("hub returned non-JSON") from exc

        if not isinstance(payload, dict):
            raise HubAuthError("hub verify response was not an object")

        _cache_set(token, payload)
        return payload


# ─── Entitlement check ──────────────────────────────────────────────────────


def _normalise_application_entry(entry: Any) -> dict:
    """The hub may serialise applications as an array of objects or strings."""
    if isinstance(entry, dict):
        return entry
    if isinstance(entry, str):
        return {"key": entry, "isActive": True}
    return {}


def entitlement_ok(verify_response: dict, app_id: str) -> bool:
    """
    Return True iff the verify response carries an entitlement for `app_id`
    that is marked active. If hub doesn't ship `applications` (older
    integrations), accept the user (no app gating).
    """
    if not app_id:
        # No allowlist configured → don't gate.
        return True

    apps = (
        verify_response.get("applications")
        or verify_response.get("user", {}).get("applications")
        or []
    )
    if not isinstance(apps, list):
        return False

    target = app_id.strip().lower()
    for raw in apps:
        entry = _normalise_application_entry(raw)
        # Hub may identify our app via `key`, `code`, or `application_key`.
        candidates = (
            entry.get("key"),
            entry.get("code"),
            entry.get("application_key"),
            entry.get("appKey"),
            entry.get("applicationKey"),
        )
        identifiers = {str(c).strip().lower() for c in candidates if c}
        if target not in identifiers:
            continue
        # If `isActive` is missing, treat as active (some hubs omit the flag
        # on apps the user currently has access to).
        is_active = entry.get("isActive")
        if is_active is False:
            return False
        return True
    return False


# ─── Role mapping ───────────────────────────────────────────────────────────


def map_hub_role_to_user_role(role: Any) -> UserRole:
    """
    Coerce a hub role string (or list of roles) into the local `UserRole`
    enum. Unknown / null falls back to PARTICIPANT.
    """
    if isinstance(role, list):
        # Pick the first role that maps cleanly.
        for item in role:
            try:
                return UserRole(str(item).strip().lower())
            except Exception:
                continue
        return UserRole.PARTICIPANT

    if role is None:
        return UserRole.PARTICIPANT
    try:
        return UserRole(str(role).strip().lower())
    except Exception:
        return UserRole.PARTICIPANT


__all__ = [
    "HubAuthError",
    "verify_hub_token",
    "entitlement_ok",
    "map_hub_role_to_user_role",
]
