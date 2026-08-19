"""Hub-and-Spoke SSO routes (login / callback / logout / me).

Flow:
  1. GET /api/auth/login   — spoke generates PKCE + state, stashes in session,
                              redirects browser to hub /api/oauth/authorize.
  2. GET /api/auth/callback— hub redirects back here with code + state. Spoke
                              verifies state, exchanges code with hub backend,
                              and stores returned user in the session cookie.
  3. GET /api/auth/logout  — spoke clears local session and bounces to the hub
                              frontend /logout so the global session dies too.
  4. GET /api/auth/me      — small JSON endpoint the SPA polls on load.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth import get_current_user_optional
from app.config import settings
from app.utils.log_sanitize import sfmt

from ..oauth_flow import generate_pkce, generate_state, get_hub_authorize_url

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Auth (SSO)"])


def _frontend_root() -> str:
    return (settings.frontend_base_url or "/").rstrip("/") or "/"


def _redirect_with_error(code: str) -> RedirectResponse:
    target = f"{_frontend_root()}/?{urlencode({'oauth_error': code})}"
    return RedirectResponse(url=target)


def _bypass_active() -> bool:
    """Dev bypass fires only when explicitly enabled AND env is not production.

    The main.py startup guard already refuses to boot the dev_auth_bypass=true +
    environment=production combination, so this check is a defence-in-depth.
    """
    if not settings.dev_auth_bypass:
        return False
    return (settings.environment or "").lower() != "production"


def _dev_fake_user() -> dict:
    return {
        "user_id": settings.dev_auth_user_id,
        "email": settings.dev_auth_user_email,
        "name": settings.dev_auth_user_name,
        "role": settings.dev_auth_user_role,
        "is_privileged": True,
        "dev_bypass": True,
    }


def _normalize_hub_user(raw: dict) -> dict:
    """Map the hub's user shape to the canonical app shape.

    The hub returns `{ id, email, firstName, lastName, profile.*, role|hub_roles, applications, ... }`.
    Every authed route in the app reads `current_user["user_id"]` (see
    e.g. modules/sites/routes/sites.py line 47), `email`, `name`, `role`,
    `is_privileged`. Without this mapping, hub-sourced sessions have `id`
    where downstream code looks for `user_id` → endpoints silently return
    empty results (no exception, no log — just no data).

    Anything we don't recognise gets passed through verbatim so callers
    that DO want hub-native fields can still find them.
    """
    if not isinstance(raw, dict):
        return {}

    # Identity — hub may publish under any of these keys.
    user_id = (
        raw.get("user_id")
        or raw.get("userId")
        or raw.get("id")
        or raw.get("sub")
        or ""
    )

    # Display name — hub stores first/last in profile, sometimes flat.
    profile = raw.get("profile") if isinstance(raw.get("profile"), dict) else {}
    first = raw.get("firstName") or profile.get("firstName") or ""
    last = raw.get("lastName") or profile.get("lastName") or ""
    name = (
        raw.get("name")
        or raw.get("displayName")
        or (f"{first} {last}".strip() if (first or last) else "")
        or raw.get("email")
        or user_id
    )

    # Role — single string or first element of hub_roles array.
    role_raw = raw.get("role")
    if not role_raw:
        hub_roles = raw.get("hub_roles") or raw.get("roles") or []
        if isinstance(hub_roles, list) and hub_roles:
            role_raw = hub_roles[0]
        elif isinstance(hub_roles, str):
            role_raw = hub_roles
    role = str(role_raw or "participant")

    # is_privileged — may arrive as bool, "true"/"false" string, or missing.
    priv_raw = raw.get("is_privileged")
    if isinstance(priv_raw, bool):
        is_privileged = priv_raw
    else:
        is_privileged = str(priv_raw or "false").strip().lower() == "true"

    normalized = {
        "user_id": str(user_id),
        "email": raw.get("email") or "",
        "name": name,
        "role": role,
        "is_privileged": is_privileged,
    }

    # Pass-through extras (applications, etc.) — useful for entitlement checks
    # downstream without forcing every caller to re-fetch from the hub.
    for k in ("applications", "hub_roles", "profile"):
        if k in raw and k not in normalized:
            normalized[k] = raw[k]

    return normalized


@router.get("/auth/login")
async def login(request: Request):
    """Kick off the OAuth2 + PKCE handshake by redirecting to the hub.

    When DEV_AUTH_BYPASS is on (local/staging only — production refuses to
    boot with the flag) this short-circuits and writes a fake user straight
    into the session, mimicking a successful hub callback.
    """
    if _bypass_active():
        request.session["user"] = _dev_fake_user()
        logger.warning(
            "DEV bypass login: stamped fake user %s into session",
            settings.dev_auth_user_id,
        )
        return RedirectResponse(url=_frontend_root() or "/")

    verifier, challenge = generate_pkce()
    state = generate_state()

    request.session["oauth_verifier"] = verifier
    request.session["oauth_state"] = state

    # DIAGNOSTIC — confirm the session was written. Compare these values to
    # what /auth/callback sees on the return trip. If callback sees None/empty,
    # the cookie was dropped by the browser between the two hops.
    logger.info(
        "[sso/login] stamped session: state=%s verifier_len=%s session_keys=%s "
        "incoming_cookies=%s host=%s scheme=%s",
        state,
        len(verifier),
        list(request.session.keys()),
        list(request.cookies.keys()),
        request.headers.get("host"),
        request.url.scheme,
    )

    try:
        auth_url = get_hub_authorize_url(challenge, state)
    except RuntimeError as e:
        logger.exception("SSO login misconfigured: %s", e)
        return _redirect_with_error("sso_misconfigured")

    return RedirectResponse(url=auth_url)


@router.get("/auth/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Receive the hub redirect, exchange the code for tokens, fetch the user,
    and persist them in the session cookie.

    Two server-to-server hops:
      1. POST <hub>/api/oauth/token   (RFC 6749 §4.1.3 token endpoint) →
         returns access_token, refresh_token, id_token, expires_in. NO user.
      2. POST <hub>/api/auth/verify   (with Bearer access_token) →
         returns the user profile from the hub.

    Hub team contract (confirmed verbatim):
      * Method: POST.
      * URL: <hub>/api/oauth/token.
      * Body: application/json (NOT form-encoded — hub explicitly require JSON).
      * Required JSON fields: grant_type=authorization_code, client_id,
        client_secret (plaintext), code, redirect_uri (byte-identical to the
        one sent at /authorize), code_verifier.
      * Response: { access_token, refresh_token, token_type, expires_in }.
        NO user payload — user data come from a separate POST /api/auth/verify
        call with the Bearer access_token.
    """
    if error:
        return _redirect_with_error(error)

    # DIAGNOSTIC — log what we see BEFORE popping anything so we can tell
    # apart "cookie never arrived" from "wrong state value".
    logger.info(
        "[sso/callback] incoming: url_state=%s session_keys=%s "
        "expected_state=%s verifier_present=%s incoming_cookies=%s host=%s scheme=%s",
        sfmt(state),
        list(request.session.keys()),
        sfmt(request.session.get("oauth_state")),
        bool(request.session.get("oauth_verifier")),
        sfmt(list(request.cookies.keys())),
        sfmt(request.headers.get("host")),
        request.url.scheme,
    )

    expected_state = request.session.pop("oauth_state", None)
    verifier = request.session.pop("oauth_verifier", None)

    if not code or not state or not expected_state or state != expected_state:
        # Detailed mismatch reason — narrows root cause without round-tripping.
        reason = (
            "no_code" if not code
            else "no_url_state" if not state
            else "session_empty" if not expected_state
            else "value_diff"
        )
        logger.warning(
            "[sso/callback] state_mismatch reason=%s url_state=%s expected_state=%s",
            reason, state, expected_state,
        )
        return _redirect_with_error("state_mismatch")

    hub_url = (settings.hub_oauth_api_url or "").rstrip("/")
    if not hub_url:
        return _redirect_with_error("sso_misconfigured")

    # redirect_uri MUST be byte-identical to the one passed at /authorize.
    # Both code paths read the same env var to guarantee that.
    redirect_uri = settings.oauth_redirect_uri or ""
    if not redirect_uri:
        return _redirect_with_error("sso_misconfigured")

    # ── Step 1: exchange the code for tokens via the hub token endpoint ──
    # Hub requires application/json — httpx's `json=` kwarg sets the body and
    # Content-Type for us. Do NOT switch back to `data=` (form-encoded) — hub
    # rejects that with invalid_request.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                f"{hub_url}/api/oauth/token",
                json={
                    "grant_type": "authorization_code",
                    "client_id": settings.oauth_client_id or "",
                    "client_secret": settings.oauth_client_secret or "",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": verifier or "",
                },
            )
    except httpx.HTTPError as e:
        logger.exception("SSO token exchange failed (network): %s", e)
        return _redirect_with_error("exchange_failed")

    if token_resp.status_code != 200:
        # Surface the hub's actual error so failed deployments can be debugged
        # (invalid_grant / invalid_client / unsupported_grant_type / …).
        logger.warning(
            "SSO token exchange returned %s: %s",
            token_resp.status_code,
            token_resp.text[:500],
        )
        return _redirect_with_error("exchange_failed")

    tokens = token_resp.json()
    access_token = tokens.get("access_token")
    if not access_token:
        logger.warning(
            "SSO token response missing access_token: %s", str(tokens)[:300]
        )
        return _redirect_with_error("exchange_failed")

    # ── Step 2: fetch the user profile via /api/auth/verify ──
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            verify_resp = await client.post(
                f"{hub_url}/api/auth/verify",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError as e:
        logger.exception("SSO verify call failed (network): %s", e)
        return _redirect_with_error("verify_failed")

    if verify_resp.status_code != 200:
        logger.warning(
            "SSO verify returned %s: %s",
            verify_resp.status_code,
            verify_resp.text[:500],
        )
        return _redirect_with_error("verify_failed")

    verify_payload = verify_resp.json() or {}
    # Hub shape per the reference: { "data": { "user": {...} } }. Fall back
    # to a top-level "user" key for hub variants that flatten the envelope.
    raw_user = (
        verify_payload.get("data", {}).get("user")
        if isinstance(verify_payload.get("data"), dict)
        else None
    ) or verify_payload.get("user")
    if not raw_user:
        logger.warning(
            "SSO verify response had no user payload: %s",
            str(verify_payload)[:300],
        )
        return _redirect_with_error("verify_failed")

    # CRITICAL: normalize the hub user shape ({id, firstName, lastName, …})
    # to the app's canonical shape ({user_id, name, role, is_privileged}).
    # Every authed endpoint reads `current_user["user_id"]`; without this
    # the hub's `id` field stays unread and endpoints silently return empty.
    user_data = _normalize_hub_user(raw_user)
    if not user_data.get("user_id"):
        logger.warning(
            "SSO verify response missing user identity: raw=%s", str(raw_user)[:300]
        )
        return _redirect_with_error("verify_failed")

    request.session["user"] = user_data
    request.session["access_token"] = access_token
    refresh_token = tokens.get("refresh_token")
    if refresh_token:
        request.session["refresh_token"] = refresh_token

    logger.info(
        "SSO login complete: user_id=%s email=%s",
        user_data.get("user_id"),
        user_data.get("email"),
    )

    return RedirectResponse(url=_frontend_root() or "/")


@router.get("/auth/logout")
async def logout(request: Request):
    """Clear the spoke session and bounce to the hub for global logout.

    Under DEV bypass, the hub was never involved — just clear local session
    and drop the user back at the spoke frontend root.
    """
    request.session.clear()

    if _bypass_active():
        return RedirectResponse(url=_frontend_root() or "/")

    hub_frontend = (settings.hub_frontend_url or "").rstrip("/")
    if not hub_frontend:
        return RedirectResponse(url=_frontend_root() or "/")
    return RedirectResponse(url=f"{hub_frontend}/logout")


@router.get("/auth/me")
async def me(
    request: Request,
    bearer_user: Optional[dict] = Depends(get_current_user_optional),
):
    """Return the current user — works under both auth modes.

    Resolution order:
      1. Starlette session cookie (set by the SSO callback or DEV bypass).
      2. Bearer JWT in the Authorization header (legacy local-mode tokens
         minted by POST /api/auth/login, or hub-issued tokens when
         IAM_AUTH_MODE=hub|both).

    This dual-mode behavior is what lets `VITE_IAM_AUTH_MODE=local` keep
    using the password flow unchanged while `=hub` uses cookie sessions.
    """
    session_user = (
        request.session.get("user") if hasattr(request, "session") else None
    )
    if session_user:
        return JSONResponse(session_user)
    if bearer_user:
        return JSONResponse(bearer_user)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )
